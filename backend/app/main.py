"""Phoenix API.

    PHOENIX_SOURCE=real uv run uvicorn backend.app.main:app --reload --port 8000

Endpoints:
    GET  /health
    POST /recommendations        five onboarding inputs -> jobs, housing_areas, services
    POST /housing-comparison     selected job pay + area rent -> hypothetical rent-burden scenario

PHOENIX_SOURCE selects data/processed/<real|synthetic>/. Default: real if built, else synthetic.

Jobs and housing use separate data adapters (docs/api_contract.md):
    src.recommend.jobs.rank_jobs(request: dict, sort: str, *, area_city: str | None) -> JobsSection
    src.recommend.housing.housing_areas(location: str, services: pd.DataFrame) -> dict matching HousingSection
"""

from __future__ import annotations

import importlib
import json
import os
from functools import lru_cache
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.schemas import (
    HousingComparisonRequest,
    HousingComparisonResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from src.common import ROOT, normalize_location_input
from src.recommend import housing_math
from src.recommend.jobs import rank_jobs
from src.recommend.services import rank_services

OPEN_TAB = {"work": "jobs", "housing": "housing"}
DISCLAIMER = ("Phoenix shows information from datasets that may be out of date. It does not guarantee a job, "
              "housing approval, or service eligibility. Always confirm details with the employer, landlord, or provider.")

app = FastAPI(title="Phoenix API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("PHOENIX_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def data_source() -> str:
    env = os.environ.get("PHOENIX_SOURCE")
    if env:
        return env
    return "real" if (ROOT / "data/processed/real/service_candidates.parquet").exists() else "synthetic"


@lru_cache(maxsize=2)
def load_data(source: str) -> dict[str, Any]:
    d = ROOT / "data" / "processed" / source
    path = d / "service_candidates.parquet"
    if not path.exists():
        raise RuntimeError(f"{path} missing. Run `make services SOURCE={source}` first.")
    stats = {}
    for name in ("places_stats", "reviews_stats", "index_stats"):
        p = d / f"{name}.json"
        if p.exists():
            stats[name] = json.loads(p.read_text())
    return {
        "candidates": pd.read_parquet(path),
        "refs": pd.read_parquet(d / "area_reference_points.parquet"),
        "stats": stats,
    }


def _optional(module: str, attr: str):
    try:
        return getattr(importlib.import_module(module), attr)
    except (ImportError, AttributeError):
        return None


def jobs_section(req: RecommendationRequest, refs: pd.DataFrame) -> dict:
    kind, key = normalize_location_input(req.location)
    city = None
    if kind == "zip":
        cities = refs.loc[(refs["area_type"] == "zip") & (refs["area_key"] == key), "city_for_zip"].dropna()
        if not cities.empty:
            city = str(cities.iloc[0])
    return rank_jobs(req.model_dump(), req.job_sort, area_city=city)


def housing_section(req: RecommendationRequest, candidates: pd.DataFrame) -> dict:
    fn = _optional("src.recommend.housing", "housing_areas")
    if fn is None:
        return {"status": "not_integrated", "areas": [],
                "notes": ["Neighborhood rental summaries are not connected yet."]}
    return fn(req.location, candidates)


def next_steps(need: str) -> list[dict]:
    """Deterministic templates (no generative plan)."""
    steps = {
        "work": [("confirm_requirements", "Open a job you like and confirm its requirements in the original posting.", "jobs")],
        "housing": [("explore_rent", "Compare rent ranges in nearby ZIP codes.", "housing")],
    }.get(need, [])
    steps += [
        ("contact_provider", "Call one service provider to confirm hours, cost, and what to bring.", "services"),
        ("check_eligibility", "Check published eligibility rules before you visit.", "services"),
    ]
    if need != "housing":
        steps.append(("explore_rent", "Look at rent ranges near the services you need.", "housing"))
    if need != "work":
        steps.append(("browse_jobs", "Browse jobs that match your experience.", "jobs"))
    return [{"id": i, "text": t, "tab": tab} for i, t, tab in steps]


def coverage(source: str, stats: dict, jobs: dict, housing: dict) -> dict:
    p = stats.get("places_stats", {})
    r = stats.get("reviews_stats", {})
    i = stats.get("index_stats", {})
    notes = [
        f"Service candidates: {i.get('candidates', 'unknown')} places in {len(p.get('target_cities', []))} East Bay cities.",
        f"Sampled reviews are available for {r.get('target_places_with_sampled_reviews', 'unknown')} of "
        f"{r.get('target_places_total', 'unknown')} places; most ratings come from Google's overall rating only.",
        "Verified public/community providers: "
        f"{i.get('verification_status', {}).get('verified_public_community', 0)}.",
    ]
    if source == "synthetic":
        notes.insert(0, "SYNTHETIC SERVICE DATA: fictional places for development only.")
    return {
        "mode": source,
        "sources": {
            "places": {"rows_in_target": p.get("target_rows_after_dedupe"), "rows_read": p.get("rows_read")},
            "reviews": {"rows_in_target": r.get("target_rows_after_dedupe"),
                        "place_coverage_rate": r.get("target_place_coverage_rate")},
            "jobs": {"status": jobs["status"], "source": "Indeed snapshot" if jobs["status"] == "ok" else None},
            "housing": {"status": housing["status"]},
        },
        "notes": notes,
    }


@app.get("/", include_in_schema=False)
def root() -> dict:
    """This is the data API, not the website. Point people at the right addresses."""
    return {
        "name": "Phoenix API",
        "app": "The website runs separately: cd frontend && npm run dev, then open http://localhost:3000",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict:
    source = data_source()
    try:
        d = load_data(source)
        return {"status": "ok", "source": source, "service_candidates": int(len(d["candidates"]))}
    except RuntimeError as e:
        return {"status": "degraded", "source": source, "detail": str(e)}


@app.post("/recommendations", response_model=RecommendationResponse)
def recommendations(req: RecommendationRequest) -> dict:
    source = data_source()
    try:
        d = load_data(source)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    services = rank_services(d["candidates"], d["refs"], need=req.priority_need, location=req.location,
                             age=req.age, sort=req.service_sort)
    jobs = jobs_section(req, d["refs"])
    housing = housing_section(req, d["candidates"])
    return {
        "open_tab": OPEN_TAB.get(req.priority_need, "services"),
        "jobs": jobs,
        "housing_areas": housing,
        "services": services,
        "data_coverage": coverage(source, d["stats"], jobs, housing),
        "next_steps": next_steps(req.priority_need),
        "disclaimer": DISCLAIMER,
    }


@app.post("/housing-comparison", response_model=HousingComparisonResponse)
def housing_comparison(req: HousingComparisonRequest) -> dict:
    return housing_math.compare(req.pay_min, req.pay_max, req.pay_period, req.hours_per_week, req.monthly_rent)

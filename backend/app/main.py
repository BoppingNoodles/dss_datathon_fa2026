"""Phoenix API.

    PHOENIX_SOURCE=real uv run uvicorn backend.app.main:app --reload --port 8000

Endpoints:
    GET  /health
    POST /recommendations        five onboarding inputs -> jobs, housing_areas, services
    POST /housing-comparison     selected job pay + area rent -> hypothetical rent-burden scenario

PHOENIX_SOURCE selects data/processed/<real|synthetic>/. Default: real if any real runtime input exists, else synthetic.

Jobs and housing use separate data adapters (docs/api_contract.md):
    src.recommend.jobs.rank_jobs(request: dict, sort: str, *, source: str, area_city: str | None) -> JobsSection
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
from src.recommend import housing_math, person1_data
from src.recommend.jobs import rank_jobs
from src.recommend.data_readiness import has_real_data, readiness
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
    return "real" if person1_data.indeed_jobs_ready() or has_real_data(ROOT) else "synthetic"


@lru_cache(maxsize=2)
def load_data(source: str) -> dict[str, Any]:
    d = ROOT / "data" / "processed" / source
    path = d / "service_candidates.parquet"
    if source not in {"real", "synthetic"}:
        raise RuntimeError(f"PHOENIX_SOURCE must be real or synthetic, got {source!r}")
    if not path.is_file() or not (d / "area_reference_points.parquet").is_file():
        state = readiness(source, ROOT, indeed_directory=person1_data.INDEED_DIR)
        if any(state["sections"][name]["status"] == "ready" for name in ("jobs", "housing")):
            return {"candidates": pd.DataFrame(), "refs": pd.DataFrame(columns=["area_type", "area_key", "city_for_zip"]),
                    "stats": {}, "services_unavailable": True}
        raise RuntimeError(f"Runtime data is incomplete in {d}. See docs/teammate_setup.md: install the processed bundle, or run make fixtures and make api SOURCE=synthetic.")
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
    return rank_jobs(req.model_dump(), req.job_sort, area_city=city, source=data_source())


def housing_section(req: RecommendationRequest, candidates: pd.DataFrame) -> dict:
    fn = _optional("src.recommend.housing", "housing_areas")
    if fn is None:
        return {"status": "not_integrated", "areas": [],
                "notes": ["Neighborhood rental summaries are not connected yet."]}
    return fn(req.location, candidates, source=data_source())


def selection_section(req: RecommendationRequest) -> dict:
    if req.selected_job_id is None:
        return {}
    fn = _optional("src.recommend.jobs", "selected_job_plan")
    if fn is None:
        raise HTTPException(status_code=503, detail="Job selection is not connected yet.")
    from src.recommend.person1_data import Person1DataUnavailable
    try:
        return fn(req.model_dump(), source=data_source())
    except Person1DataUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


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
        notes.insert(0, "SYNTHETIC FIXTURE DATA: fictional places for development only.")
    person1_coverage = _optional("src.recommend.person1_data", "coverage_summary")
    extra = person1_coverage(source) if person1_coverage is not None else {}
    return {
        "mode": source,
        "sources": {
            "places": {"rows_in_target": p.get("target_rows_after_dedupe"), "rows_read": p.get("rows_read")},
            "reviews": {"rows_in_target": r.get("target_rows_after_dedupe"),
                        "place_coverage_rate": r.get("target_place_coverage_rate")},
            "jobs": {"status": jobs["status"], "source": ("Indeed snapshot" if source == "real" else "synthetic fixture") if jobs["status"] == "ok" else None, **extra.get("jobs", {})},
            "housing": {"status": housing["status"], **extra.get("housing", {})},
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
        result = readiness(source, ROOT, indeed_directory=person1_data.INDEED_DIR)
        d = load_data(source)
        result["service_candidates"] = int(len(d["candidates"]))
        if d.get("services_unavailable"):
            result["status"] = "degraded"
    except (RuntimeError, ValueError, OSError) as error:
        result = {"status": "degraded", "source": source, "project_root": str(ROOT), "detail": str(error)}
        if source in {"real", "synthetic"}:
            result.update(readiness(source, ROOT, indeed_directory=person1_data.INDEED_DIR))
            result["status"] = "degraded"
            result["detail"] = str(error)
    return result


@app.post("/recommendations", response_model=RecommendationResponse)
def recommendations(req: RecommendationRequest) -> dict:
    source = data_source()
    try:
        d = load_data(source)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    if d.get("services_unavailable"):
        services = {"status": "no_results", "priority_need": req.priority_need, "need_label": "Services",
                    "sort": req.service_sort, "reference_point": {}, "search_area": req.location,
                    "families_considered": [], "ranking_settings": {}, "groups": [],
                    "notes": ["Service data has not been prepared in this checkout."]}
    else:
        services = rank_services(d["candidates"], d["refs"], need=req.priority_need, location=req.location,
                                 age=req.age, sort=req.service_sort)
    jobs = jobs_section(req, d["refs"])
    housing = housing_section(req, d["candidates"])
    map_points = _optional("src.recommend.housing", "service_map_points")
    selection = selection_section(req)
    return {
        "open_tab": OPEN_TAB.get(req.priority_need, "services"),
        "jobs": jobs,
        "housing_areas": housing,
        "service_map_points": map_points(housing.get("areas", []), d["candidates"]) if map_points else [],
        "services": services,
        "data_coverage": coverage(source, d["stats"], jobs, housing),
        "next_steps": next_steps(req.priority_need),
        "disclaimer": DISCLAIMER,
        **selection,
    }


@app.get("/job-certificates")
def job_certificates() -> dict:
    from src.recommend.certificates import certificate_catalog
    return certificate_catalog(data_source())


@app.post("/housing-comparison", response_model=HousingComparisonResponse)
def housing_comparison(req: HousingComparisonRequest) -> dict:
    return housing_math.compare(req.pay_min, req.pay_max, req.pay_period, req.hours_per_week, req.monthly_rent)

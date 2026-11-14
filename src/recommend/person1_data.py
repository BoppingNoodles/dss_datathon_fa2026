"""Shared boundary between the existing API and Person 1's normalized data.

Real and synthetic inputs are always separate. Only datasets, never user profiles,
are cached. No request can fall back from synthetic fixtures to real records.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from src.common import normalize_location_input, processed_dir
from src.phoenix.ingest import load_records
from src.phoenix.models import Education, Experience, Job, Point, Rental, UserProfile
from src.recommend.services import resolve_location


class Person1DataUnavailable(RuntimeError):
    pass


def _token(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=4)
def _load(directory: str, tokens: tuple) -> tuple[list[Job], list[Rental], dict]:
    root = Path(directory)
    coverage = json.loads((root / "person1_coverage.json").read_text())
    expected = "full" if root.name == "real" else "synthetic"
    if coverage.get("data_mode") != expected:
        raise Person1DataUnavailable(f"{root.name} Person 1 data has the wrong data-mode label")
    return (load_records(root / "jobs.jsonl", Job),
            load_records(root / "rentals.jsonl", Rental), coverage)


def load_person1(source: str) -> tuple[list[Job], list[Rental], dict]:
    root = processed_dir(source)
    files = [root / name for name in ("jobs.jsonl", "rentals.jsonl", "person1_coverage.json")]
    if not all(p.exists() for p in files):
        raise Person1DataUnavailable(f"Person 1 normalized inputs are missing for {source}; run make person1 SOURCE={source} after preparing inputs.")
    return _load(str(root), tuple(_token(p) for p in files))


@lru_cache(maxsize=4)
def _refs(directory: str, tokens: tuple) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(directory)
    return (pd.read_parquet(root / "area_reference_points.parquet"),
            pd.read_parquet(root / "service_candidates.parquet", columns=["place_id", "city", "zipcode"]))


def native_profile(request: dict, source: str) -> UserProfile:
    exp = request.get("experience") or {}
    edu = request.get("education") or {}
    levels = {None: "unknown", "not_sure": "unknown", "no_diploma": "none",
              "high_school_or_ged": "high_school", "some_college": "some_college",
              "associate": "associate", "bachelor": "bachelor", "graduate": "unknown"}
    profile = UserProfile(age=request.get("age"), location=request["location"],
        priority_need="health" if request["priority_need"] == "health_care" else request["priority_need"],
        experience=Experience(skills=exp.get("skills") or [], text=exp.get("text") or "",
                              years=0 if exp.get("no_experience_yet") else exp.get("years")),
        education=Education(level=levels[edu.get("level")], certifications=edu.get("credentials") or []),
        sort=request.get("job_sort", "highest_pay"))
    root = processed_dir(source)
    paths = [root / "area_reference_points.parquet", root / "service_candidates.parquet"]
    if all(p.exists() for p in paths):
        refs, candidates = _refs(str(root), tuple(_token(p) for p in paths))
        # Preserve city names ending in 'ca' (e.g. Pacifica): provide an explicit
        # state suffix to the backend's permissive location normalizer.
        lookup = profile.location.strip()
        if not re.fullmatch(r"\d{5}(?:-\d{4})?", lookup):
            lookup = re.sub(r"(?:,\s*|\s+)(?:CA|California)\.?$", "", lookup, flags=re.I) + ", CA"
        ref = resolve_location(lookup, refs, candidates)
        updates = {}
        if ref.city:
            updates["search_cities"] = [ref.city]
        if ref.lat is not None and ref.lon is not None:
            updates["reference_point"] = Point(latitude=ref.lat, longitude=ref.lon,
                precision=ref.precision, label=ref.label, source="Places-derived area reference point, not a home address")
        profile = profile.model_copy(update=updates)
    if not profile.search_cities and normalize_location_input(profile.location)[0] == "zip":
        _, rentals, _ = load_person1(source)
        cities = {r.city for r in rentals if r.zipcode == profile.location.strip()}
        if len(cities) == 1:
            profile = profile.model_copy(update={"search_cities":sorted(cities)})
    return profile


def coverage_summary(source: str) -> dict:
    try:
        _, _, coverage = load_person1(source)
    except Person1DataUnavailable:
        return {}
    return {
        "jobs": {"rows_read":sum(s["counts"]["input_rows"] for s in coverage.get("sources", []) if s["kind"] == "jobs"),
                 "retained_records":coverage.get("retained", {}).get("jobs"),
                 "not_marked_expired":coverage.get("retained", {}).get("jobs_not_marked_expired")},
        "housing": {"rows_read":sum(s["counts"]["input_rows"] for s in coverage.get("sources", []) if s["kind"] == "rentals"),
                    "retained_rental_candidates":coverage.get("retained", {}).get("rentals")},
    }

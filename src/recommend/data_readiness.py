"""Cheap, explicit runtime diagnostics; readiness is not geographic coverage."""

import json
from pathlib import Path

from src.common import ROOT

SERVICE_FILES = ("service_candidates.parquet", "area_reference_points.parquet")
PERSON1_FILES = ("jobs.jsonl", "rentals.jsonl", "person1_coverage.json")


def has_real_data(root: Path = ROOT) -> bool:
    processed = root / "data/processed"
    return any((processed / "real" / name).is_file() for name in (*SERVICE_FILES, *PERSON1_FILES)) or any(
        (processed / "indeed" / name).is_file() for name in ("jobs.jsonl", "coverage.json"))


def readiness(source: str, root: Path = ROOT, *, indeed_directory: Path | None = None) -> dict:
    if source not in {"real", "synthetic"}:
        raise ValueError(f"PHOENIX_SOURCE must be real or synthetic, got {source!r}")
    directory = root / "data/processed" / source

    def check(folder, names, manifest=None, kind=None):
        missing = [str((folder / name).relative_to(root)) if (folder / name).is_relative_to(root) else str(folder / name) for name in names if not (folder / name).is_file()]
        result = {"status": "missing" if missing else "ready", "missing_files": missing}
        if not missing and manifest:
            try:
                coverage = json.loads((folder / manifest).read_text(encoding="utf-8"))
                expected = "full" if source == "real" else "synthetic"
                if coverage.get("data_mode") != expected:
                    raise ValueError(f"{manifest} must have data_mode={expected}")
                if kind and not any(s.get("kind") == kind for s in coverage.get("sources", [])):
                    raise ValueError(f"{manifest} must describe {kind} inputs")
            except (OSError, ValueError, AttributeError, TypeError) as error:
                result.update(status="invalid", detail=str(error))
        return result

    services = check(directory, SERVICE_FILES)
    person1 = check(directory, PERSON1_FILES, "person1_coverage.json")
    jobs = {**person1, "adapter": "normalized"}
    if source == "real" and person1["status"] != "ready":
        indeed = check(indeed_directory if indeed_directory is not None else root / "data/processed/indeed", ("jobs.jsonl", "coverage.json"), "coverage.json", "jobs")
        if indeed["status"] == "ready":
            jobs = {**indeed, "adapter": "indeed_jobs_only"}
        elif (root / "data/jobs/oakland_jobs.json").is_file():
            jobs = {"status": "ready", "missing_files": [], "adapter": "oakland_only"}
    sections = {"jobs": jobs, "housing": dict(person1), "services": services}
    return {
        "status": "ok" if all(s["status"] == "ready" for s in sections.values()) else "degraded",
        "source": source,
        "project_root": str(root),
        "data_directory": str(directory),
        "sections": sections,
        "setup": "See docs/teammate_setup.md; install the real runtime bundle, or make fixtures for fictional data. Restart the API after replacing data.",
    }

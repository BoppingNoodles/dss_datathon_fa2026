"""Local-only commands for data owners; backend can call build_recommendations directly."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ingest import load_records, prepare_data
from .integration import build_recommendations
from .models import Job, RecommendationRequest, RecommendationResponse, Rental, Requirement, ServiceLocation, UserProfile


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def attach_enrichment(jobs: list[Job], path: Path) -> list[Job]:
    """Optional extractor/model handoff. Unknown IDs are an error, never a positional join."""
    by_id = {j.job_id: j for j in jobs}
    seen = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        job_id = record.pop("job_id")
        if job_id not in by_id or job_id in seen:
            raise ValueError(f"Unknown or duplicate enrichment job_id: {job_id}")
        if set(record) - {"requirements", "hours_per_week", "weeks_per_year", "point"}:
            raise ValueError("Enrichment can only attach requirements, stated hours/weeks, and sourced worksite point")
        if "requirements" in record:
            record["requirements"] = [Requirement.model_validate(r).model_dump() for r in record["requirements"]]
        by_id[job_id] = Job.model_validate({**by_id[job_id].model_dump(), **record})
        seen.add(job_id)
    return [by_id[j.job_id] for j in jobs]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Stream local CSVs; deduplicate and report coverage")
    prepare.add_argument("--indeed", type=Path, action="append", default=[])
    prepare.add_argument("--zillow", type=Path, action="append", default=[])
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--city", action="append", default=[])
    prepare.add_argument("--data-mode", choices=["sample", "full"], required=True)
    prepare.add_argument("--allow-unverified-rent", action="store_true",
                         help="Include FOR_RENT price without a matching base_rent; output is explicitly unverified")
    recommend = sub.add_parser("recommend", help="Build API-compatible JSON from normalized records")
    recommend.add_argument("--data-dir", type=Path, required=True)
    recommend.add_argument("--profile", type=Path, required=True)
    recommend.add_argument("--output", type=Path, required=True)
    recommend.add_argument("--enrichment", type=Path)
    recommend.add_argument("--selected-job-id")
    recommend.add_argument("--selected-interim-job-id")
    recommend.add_argument("--scenario-hours-per-week", type=float)
    recommend.add_argument("--scenario-weeks-per-year", type=float)
    recommend.add_argument("--include-expired", action="store_true",
                           help="Historical demo only; returned cards retain expired_snapshot status")
    schema = sub.add_parser("schemas", help="Export JSON Schemas for frontend/backend/extractor handoffs")
    schema.add_argument("--output", type=Path, required=True)
    demo = sub.add_parser("demo", help="Run the synthetic, data-independent integration fixture")
    demo.add_argument("--fixtures", type=Path, default=Path("examples"))
    demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            if not args.indeed and not args.zillow:
                parser.error("Provide at least one --indeed or --zillow CSV")
            report = prepare_data(indeed_paths=args.indeed, zillow_paths=args.zillow, output_dir=args.output,
                cities=args.city, allow_unverified_rent=args.allow_unverified_rent, data_mode=args.data_mode)
            print(json.dumps({"retained": report["retained"], "coverage": str(args.output / 'coverage.json')}))
        elif args.command == "recommend":
            jobs = load_records(args.data_dir / "jobs.jsonl", Job)
            if args.enrichment:
                jobs = attach_enrichment(jobs, args.enrichment)
            rentals = load_records(args.data_dir / "rentals.jsonl", Rental)
            profile = UserProfile.model_validate_json(args.profile.read_text())
            mode = json.loads((args.data_dir / "coverage.json").read_text())["data_mode"]
            response = build_recommendations(profile, jobs, rentals, data_mode=mode,
                selected_job_id=args.selected_job_id, scenario_hours_per_week=args.scenario_hours_per_week,
                selected_interim_job_id=args.selected_interim_job_id,
                scenario_weeks_per_year=args.scenario_weeks_per_year, include_expired=args.include_expired)
            write_json(args.output, response.model_dump(mode="json"))
            print(f"Wrote {len(response.jobs)} job cards and {len(response.housing_areas)} housing areas to {args.output}")
        elif args.command == "schemas":
            for name, model in [("user-profile", UserProfile), ("recommendation-request", RecommendationRequest), ("job-input", Job), ("service-location", ServiceLocation), ("recommendation-response", RecommendationResponse)]:
                write_json(args.output / f"{name}.schema.json", model.model_json_schema())
            print(f"Wrote five JSON Schemas to {args.output}")
        else:
            profile = UserProfile.model_validate_json((args.fixtures / "profile.synthetic.json").read_text())
            jobs = load_records(args.fixtures / "jobs.synthetic.jsonl", Job)
            rentals = load_records(args.fixtures / "rentals.synthetic.jsonl", Rental)
            response = build_recommendations(profile, jobs, rentals, data_mode="synthetic",
                selected_job_id="example-b", scenario_hours_per_week=40, scenario_weeks_per_year=52)
            write_json(args.output, response.model_dump(mode="json"))
            print(f"Synthetic demo passed through response builder; output: {args.output}")
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    return 0

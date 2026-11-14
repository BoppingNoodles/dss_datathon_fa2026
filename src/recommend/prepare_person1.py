"""Export Person 1 normalized inputs to the API/audit layout without touching services.

    python -m src.recommend.prepare_person1 --source real
    python -m src.recommend.prepare_person1 --source synthetic

For real mode, prepare/copy jobs.jsonl and rentals.jsonl first. Raw exports and all
intermediate/processed files stay ignored by Git.
"""

from __future__ import annotations

import argparse
import json
import shutil

import pandas as pd

from src.common import ROOT, processed_dir, write_json
from src.phoenix.ingest import load_records
from src.phoenix.models import Job, Rental
from src.recommend.housing import housing_areas
from src.recommend.person1_data import _load


def run(source: str) -> dict:
    root = processed_dir(source)
    if source == "synthetic":
        for fixture, output in [("jobs.synthetic.jsonl", "jobs.jsonl"), ("rentals.synthetic.jsonl", "rentals.jsonl")]:
            shutil.copy2(ROOT / "examples" / fixture, root / output)
        coverage = {"data_mode":"synthetic", "sources":[],
                    "retained":{"jobs":3, "rentals":6, "jobs_not_marked_expired":2, "jobs_unknown_expiry":1},
                    "notes":["Fictional Person 1 fixture records; no real input fallback."]}
        write_json(root / "person1_coverage.json", coverage)
    elif (root / "coverage.json").exists():
        coverage = json.loads((root / "coverage.json").read_text())
        if coverage.get("data_mode") != "full":
            raise ValueError("Real mode requires a full-input coverage manifest")
        write_json(root / "person1_coverage.json", coverage)
    for name in ["jobs.jsonl", "rentals.jsonl", "person1_coverage.json"]:
        if not (root / name).exists():
            raise FileNotFoundError(f"Missing {root/name}; prepare normalized Person 1 inputs first")
    _load.cache_clear()
    jobs = load_records(root / "jobs.jsonl", Job)
    rentals = load_records(root / "rentals.jsonl", Rental)
    pd.DataFrame([{"jobid":j.job_id, "job_title":j.title, "company_name":j.company,
        "location":j.location_text, "city":j.city, "salary_text":j.pay.raw,
        "pay_min":j.pay.minimum, "pay_max":j.pay.maximum,
        "pay_period":None if j.pay.period == "unknown" else j.pay.period,
        "duplicate_group":j.duplicate_group, "is_expired":j.is_expired,
        "source_file":j.source_file, "source_row":j.source_row} for j in jobs]).to_parquet(root / "jobs_clean.parquet", index=False)
    pd.DataFrame([{"zpid":r.property_id, "city":r.city, "zipcode":r.zipcode,
        "price":r.monthly_rent, "monthly_rent":r.monthly_rent,
        "homeStatus":"FOR_RENT", "is_rental":True, "rent_basis":r.rent_basis,
        "area_id":f"{r.city.casefold()}:{r.zipcode or 'city'}", "bedrooms":r.bedrooms,
        "home_type":r.home_type, "latitude":r.latitude, "longitude":r.longitude,
        "source_file":r.source_file, "source_row":r.source_row} for r in rentals]).to_parquet(root / "zillow_rentals_clean.parquet", index=False)
    path = root / "service_candidates.parquet"
    services = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    areas = []
    for city in sorted({r.city for r in rentals}):
        areas.extend(housing_areas(city, services, source=source)["areas"])
    frame = pd.DataFrame(areas)
    frame.to_parquet(root / "housing_areas.parquet", index=False)
    result = {"source":source, "jobs":len(jobs), "rental_candidates":len(rentals), "public_housing_areas":len(areas),
              "notes":["Rental audit price is the retained listed price; use source_file/source_row to cross-check the raw source.",
                       "Counts are snapshots and do not establish current availability."]}
    write_json(root / "person1_export_stats.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["real", "synthetic"], default="real")
    print(json.dumps(run(parser.parse_args().source), indent=2))

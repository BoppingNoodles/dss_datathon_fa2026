"""Adapt the local Oakland export to the Jobs tab's API contract."""

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from src.common import ROOT, normalize_location_input
from src.data.scrape_indeed import PAY
from src.phoenix.qualifications import redact_contacts


JOBS_PATH = ROOT / "data/jobs/oakland_jobs.json"
LIMIT_PER_GROUP = 12
REQUIREMENT_STATUS = {"detected": "required", "not_detected": "not_found", "unknown": "unknown"}
PAY_GROUPS = {
    "hour": "Oakland jobs with advertised hourly pay",
    "year": "Oakland jobs with advertised annual pay",
    None: "Oakland jobs with pay to confirm",
}


@lru_cache(maxsize=1)
def load_jobs(path: Path, modified_ns: int, size: int) -> dict:
    # File metadata invalidates the cache when the exporter replaces the file.
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def job_pay(row: dict, hourly_assumptions: dict) -> dict:
    raw = row["salary_text"]
    low, high = row["annual_pay_low"], row["annual_pay_high"]
    match = PAY.fullmatch(raw or "")
    if match is None or (low is None and high is None):
        return {"raw_text": raw, "currency": None}
    hourly = match["unit"].lower().startswith("h")
    factor = hourly_assumptions["hours_per_week"] * hourly_assumptions["weeks_per_year"] if hourly else 1
    return {
        "raw_text": raw,
        "min": None if low is None else round(low / factor, 2),
        "max": None if high is None else round(high / factor, 2),
        "period": "hour" if hourly else "year",
    }


def job_card(row: dict, pay: dict, explanation: str) -> dict:
    return {
        "job_id": row["job_id"],
        "title": row["title"],
        "description": redact_contacts(row.get("description_text") or row.get("description") or "") or None,
        "employer": row["employer"],
        "posted_date": row["posted_date"],
        "url": row["source_url"],
        "suitability_tier": "possible_match",
        "requirements": [
            {"label": label, "status": REQUIREMENT_STATUS[result["status"]],
             "evidence": result["evidence"], "source": "rule_extraction"}
            for label, result in row["requirements"].items()
        ],
        "pay": pay,
        "location": {"text": "Oakland, CA", "city": "Oakland", "precision": "city", "source": "Indeed"},
        "rank_explanation": explanation,
        "source": {"dataset": "Indeed", "availability_verified": False},
    }


def rank_jobs(request: dict, sort: str, *, area_city: str | None = None) -> dict:
    section = {"sort": sort, "groups": []}
    location_type, location = normalize_location_input(request["location"])
    city = (area_city or "") if location_type == "zip" else location
    if city.casefold() != "oakland":
        return {**section, "status": "no_results", "notes": ["Jobs coverage currently includes Oakland. Search for Oakland to browse listings."]}

    try:
        revision = JOBS_PATH.stat()
        dataset = load_jobs(JOBS_PATH, revision.st_mtime_ns, revision.st_size)
    except (OSError, ValueError):
        return {**section, "status": "not_integrated", "notes": ["The Oakland jobs dataset is unavailable. Run the Oakland jobs export to load it."]}

    buckets = defaultdict(list)
    assumptions = dataset["metadata"]["hourly_pay_assumptions"]
    for row in dataset["jobs"]:
        pay = job_pay(row, assumptions)
        buckets[pay.get("period")].append((row, pay))

    groups = []
    for period, label in PAY_GROUPS.items():
        items = buckets[period]
        if not items:
            continue
        if sort == "highest_pay" and period is not None:
            # Stable sort preserves the export's newest-first order for ties.
            items.sort(key=lambda item: (item[1]["min"] is None, -(item[1]["min"] or 0)))
            explanation = "Ordered by the lower advertised pay bound within this pay period. Jobs without a lower bound come last."
        else:
            explanation = "Ordered by posting date, newest first."
        groups.append({"key": period or "unconfirmed_pay", "label": label, "total": len(items),
                       "items": [job_card(row, pay, explanation) for row, pay in items[:LIMIT_PER_GROUP]]})
    notes = ["Listings come from an Indeed dataset snapshot. Confirm availability and requirements with the employer.",
             "Results use Oakland city coverage. Qualifications and exact distances still need confirmation."]
    if sort == "nearest":
        notes.append("Worksite distances are unavailable. Listings are ordered by posting date within each group.")
    return {**section, "status": "ok" if groups else "no_results", "groups": groups, "notes": notes}

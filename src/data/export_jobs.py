"""Export Oakland Indeed listings for the Phoenix Jobs frontend."""

import argparse
import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

from scrape_indeed import LABEL_PATTERNS, annual_pay, suggest_labels
from split_indeed import normalize


OAKLAND = re.compile(r"\bOakland,\s*CA(?:\b|$)", re.IGNORECASE)
FIELDS = (
    "jobid", "job_title", "company_name", "location", "description_text",
    "date_posted_parsed", "is_expired", "url", "salary_formatted",
)
STATUSES = {"1": "detected", "0": "not_detected", "review": "unknown"}


def posting_date(text):
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def read_oakland(source):
    counts = dict.fromkeys(("source_rows", "oakland_rows", "expired_rows", "incomplete_rows", "eligible_rows"), 0)
    # Resolve repeated IDs before grouping reposts so each exported ID is unique.
    by_id = {}
    csv.field_size_limit(16 * 1024 * 1024)
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        missing = set(FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing Indeed columns: {', '.join(sorted(missing))}")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"Unexpected column count at CSV line {reader.line_num}")
            counts["source_rows"] += 1
            if not OAKLAND.search(row["location"]):
                continue
            counts["oakland_rows"] += 1
            if row["is_expired"].strip().casefold() in {"true", "1", "yes"}:
                counts["expired_rows"] += 1
                continue
            if not all(row[key].strip() for key in ("jobid", "job_title", "description_text")):
                counts["incomplete_rows"] += 1
                continue
            counts["eligible_rows"] += 1
            record = {key: row[key].strip() for key in FIELDS}
            record["posted_date"] = posting_date(record["date_posted_parsed"])
            job_id = record["jobid"]
            previous = by_id.get(job_id)
            if previous is None or newest_first(record) < newest_first(previous):
                by_id[job_id] = record

    unique = {}
    for row in sorted(by_id.values(), key=newest_first):
        employer = normalize(row["company_name"])
        group = (normalize(row["job_title"]), employer, "Oakland") if employer else (row["jobid"],)
        unique.setdefault(group, row)
    counts["duplicates_removed"] = counts["eligible_rows"] - len(unique)
    counts["exported_rows"] = len(unique)
    return unique.values(), counts


def newest_first(row):
    posted = row["posted_date"]
    return (-(posted.toordinal() if posted else 0), row["jobid"])


def frontend_job(row):
    suggestions = suggest_labels(row["description_text"])
    low, high = annual_pay(row["salary_formatted"])
    source_url = urlsplit(row["url"])
    return {
        "job_id": row["jobid"],
        "title": row["job_title"],
        "employer": row["company_name"] or None,
        "city": "Oakland",
        "state": "CA",
        "posted_date": row["posted_date"].isoformat() if row["posted_date"] else None,
        "source_url": row["url"] if source_url.scheme in {"http", "https"} and source_url.netloc else None,
        "salary_text": row["salary_formatted"] or None,
        "annual_pay_low": low or None,
        "annual_pay_high": high or None,
        "requirements": {
            label: {
                "status": STATUSES[suggestions[f"{label}_suggested"]],
                "evidence": suggestions[f"{label}_evidence"] or None,
            }
            for label in LABEL_PATTERNS
        },
    }


def export_jobs(source, output):
    if source.resolve() == output.resolve():
        raise ValueError("Choose an output path different from the source CSV.")
    selected, counts = read_oakland(source)
    if not selected:
        raise ValueError(f"No usable Oakland postings. Filter counts: {counts}")
    jobs = [frontend_job(row) for row in selected]
    counts["with_annual_pay"] = sum(
        job["annual_pay_low"] is not None or job["annual_pay_high"] is not None for job in jobs
    )
    review_counts = Counter(label for job in jobs for label, result in job["requirements"].items()
                            if result["status"] == "unknown")
    metadata = {
        "source": "Indeed dataset export",
        "availability_verified": False,
        "hourly_pay_assumptions": {"hours_per_week": 40, "weeks_per_year": 52},
        "counts": counts,
        "review_counts": {label: review_counts[label] for label in LABEL_PATTERNS},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as stream:
            staged = Path(stream.name)
            json.dump({"metadata": metadata, "jobs": jobs}, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        staged.replace(output)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=Path.home() / "Downloads" / "indeed_job_listings.csv")
    parser.add_argument("--output", type=Path, default=Path("data/jobs/oakland_jobs.json"))
    args = parser.parse_args()
    try:
        metadata = export_jobs(args.source, args.output)
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, f"Error: {error}\n")
    print(f"Wrote {args.output}")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()

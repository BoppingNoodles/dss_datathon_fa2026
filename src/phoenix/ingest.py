"""Stream raw exports into a deduplicated local SQLite store and a count audit."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from .models import Job, Rental
from .normalization import (BAY_COUNTIES, city_key, clean_text, display_city, number,
                            optional_bool, parse_job_city, valid_coordinate)
from .pay import parse_pay

csv.field_size_limit(sys.maxsize)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso_date(value: str) -> str | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def normalize_job(row: dict, source_file: str, row_number: int) -> tuple[Job | None, str]:
    city = parse_job_city(row.get("location", ""), row.get("region", ""))
    if not city or clean_text(row.get("country")).upper() not in {"", "US", "USA"}:
        return None, "outside_or_unresolved_geography"
    title, company = clean_text(row.get("job_title")), clean_text(row.get("company_name"))
    description = clean_text(row.get("description_text"))
    if not title or not description:
        return None, "missing_title_or_description"
    group = digest("|".join([title.casefold(), company.casefold(), city_key(city)]))
    job_id = clean_text(row.get("jobid")) or "derived-" + digest(group + description)[:24]
    posted = _iso_date(clean_text(row.get("date_posted_parsed"))) or _iso_date(clean_text(row.get("date_posted")))
    return Job(job_id=job_id, title=title, company=company, city=city, state="CA",
        location_text=clean_text(row.get("location")), description=description,
        job_type=clean_text(row.get("job_type")) or None,
        pay=parse_pay(row.get("salary_formatted")), is_expired=optional_bool(row.get("is_expired")),
        source_url=clean_text(row.get("url")) or None, posted_at=posted,
        duplicate_group=group, source_file=source_file, source_row=row_number), "retained_candidate"


def normalize_rental(row: dict, source_file: str, row_number: int,
                     *, allow_unverified_rent: bool = False) -> tuple[Rental | None, str]:
    county = re.sub(r"\s+county$", "", clean_text(row.get("county")).casefold())
    if clean_text(row.get("state")).upper() != "CA" or county not in BAY_COUNTIES:
        return None, "outside_or_unresolved_geography"
    if clean_text(row.get("homeStatus")).upper() != "FOR_RENT":
        return None, "not_for_rent"
    if any(optional_bool(row.get(k)) is True for k in ["isRentalListingOffMarket", "isOffMarket"]):
        return None, "marked_off_market"
    if clean_text(row.get("currency")).upper() != "USD":
        return None, "missing_or_unsupported_currency"
    price, base = number(row.get("price")), number(row.get("base_rent"))
    if price is None or price <= 0:
        return None, "invalid_price"
    if base is not None and base > 0 and abs(price - base) <= 0.01:
        basis = "base_rent_cross_checked"
    elif allow_unverified_rent:
        basis = "listed_price_unverified"
    else:
        return None, "rent_unit_needs_confirmation"
    city, property_id = clean_text(row.get("city")), clean_text(row.get("zpid"))
    if not city or not property_id:
        return None, "missing_city_or_property_id"
    latitude, longitude = valid_coordinate(row.get("latitude"), row.get("longitude"))
    bedrooms = number(row.get("bedrooms"))
    zipcode = clean_text(row.get("zipcode"))
    zipcode = zipcode[:5] if re.fullmatch(r"\d{5}(?:-\d{4})?", zipcode) else None
    return Rental(property_id=property_id, city=display_city(city), zipcode=zipcode,
        monthly_rent=price, currency="USD", bedrooms=bedrooms if bedrooms is not None and bedrooms >= 0 else None,
        home_type=clean_text(row.get("homeType")) or None, latitude=latitude, longitude=longitude,
        rent_basis=basis, source_file=source_file, source_row=row_number), "retained_candidate"


def _rows(path: Path, required: set[str]):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name}: required columns missing: {sorted(missing)}")
        for row in reader:
            if None in row:
                raise ValueError(f"{path.name}: malformed CSV near physical line {reader.line_num}")
            yield reader.line_num, row


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT, record_id TEXT, duplicate_key TEXT, preference TEXT, payload TEXT, PRIMARY KEY(kind, record_id), UNIQUE(kind, duplicate_key))")
    return db


def prepare_data(*, indeed_paths: list[Path], zillow_paths: list[Path], output_dir: Path,
                 cities: list[str] | None = None, allow_unverified_rent: bool = False,
                 data_mode: str = "sample") -> dict:
    """Rebuild only this output store; input files are opened read-only, one row at a time."""
    output_dir.mkdir(parents=True, exist_ok=True)
    db = connect(output_dir / "phoenix.sqlite")
    db.execute("DELETE FROM records")
    selected_cities = {city_key(c) for c in cities or []}
    report = {"data_mode": data_mode, "scope_cities": sorted(selected_cities), "sources": [],
              "notes": ["Counts reflect only the provided input files, not the README population.",
                        "Not marked expired in a snapshot is not confirmation of a live vacancy.",
                        "No requirement model or scraper is run by this pipeline."]}
    try:
        for kind, paths in [("jobs", indeed_paths), ("rentals", zillow_paths)]:
            for path in paths:
                counts: Counter = Counter()
                pay_states: Counter = Counter()
                dates: list[str] = []
                required = {"job_title", "description_text", "location"} if kind == "jobs" else {"zpid", "city", "county", "state", "homeStatus", "price"}
                for row_number, row in _rows(path, required):
                    counts["input_rows"] += 1
                    if kind == "jobs":
                        counts["marked_expired_in_input"] += optional_bool(row.get("is_expired")) is True
                        record, reason = normalize_job(row, path.name, row_number)
                    else:
                        counts["for_rent_in_input"] += clean_text(row.get("homeStatus")).upper() == "FOR_RENT"
                        record, reason = normalize_rental(row, path.name, row_number, allow_unverified_rent=allow_unverified_rent)
                    if record is None:
                        counts[reason] += 1
                        continue
                    if selected_cities and city_key(record.city) not in selected_cities:
                        counts["outside_selected_cities"] += 1
                        continue
                    if kind == "jobs":
                        record_id = record.job_id
                        duplicate_key = digest((record.duplicate_group or "") + record.description)
                        # Prefer an explicitly unexpired snapshot, then a newer posted date.
                        preference = str(2 if record.is_expired is False else 1 if record.is_expired is None else 0) + (record.posted_at or "")
                        pay_states[record.pay.source + ":" + record.pay.period] += 1
                        if record.posted_at:
                            dates.append(record.posted_at)
                    else:
                        record_id, duplicate_key = record.property_id, record.property_id
                        preference = "1" if record.rent_basis == "base_rent_cross_checked" else "0"
                    existing = db.execute("SELECT record_id, preference FROM records WHERE kind=? AND (record_id=? OR duplicate_key=?)", (kind, record_id, duplicate_key)).fetchall()
                    if existing:
                        counts["duplicate_rows"] += 1
                        if any(pref >= preference for _, pref in existing):
                            continue
                        for old_id, _ in existing:
                            db.execute("DELETE FROM records WHERE kind=? AND record_id=?", (kind, old_id))
                    db.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?)",
                               (kind, record_id, duplicate_key, preference, record.model_dump_json()))
                    counts["candidate_rows_stored_or_updated"] += 1
                with path.open("rb") as handle:
                    checksum = hashlib.file_digest(handle, "sha256").hexdigest()
                report["sources"].append({"file": path.name, "sha256": checksum, "bytes": path.stat().st_size,
                    "kind": kind, "counts": dict(counts), "candidate_pay_states": dict(pay_states),
                    "posted_date_min": min(dates) if dates else None, "posted_date_max": max(dates) if dates else None})
        db.commit()
        report["retained"] = {}
        for kind in ["jobs", "rentals"]:
            count = db.execute("SELECT count(*) FROM records WHERE kind=?", (kind,)).fetchone()[0]
            report["retained"][kind] = count
            with (output_dir / f"{kind}.jsonl").open("w") as handle:
                for (payload,) in db.execute("SELECT payload FROM records WHERE kind=? ORDER BY record_id", (kind,)):
                    handle.write(payload + "\n")
        report["retained"]["jobs_not_marked_expired"] = db.execute("SELECT count(*) FROM records WHERE kind='jobs' AND json_extract(payload, '$.is_expired')=0").fetchone()[0]
        report["retained"]["jobs_unknown_expiry"] = db.execute("SELECT count(*) FROM records WHERE kind='jobs' AND json_extract(payload, '$.is_expired') IS NULL").fetchone()[0]
        (output_dir / "coverage.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        db.close()


def load_records(path: Path, model: type[Job] | type[Rental]) -> list:
    with path.open() as handle:
        return [model.model_validate_json(line) for line in handle if line.strip()]

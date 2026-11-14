"""Clean the Google Maps Places export and keep the target-area subset.

    uv run python -m src.data.places --source real

Outputs (data/processed/<source>/):
    places_target.parquet   cleaned, deduplicated places in the target cities
    places_all_ids.parquet  every place_id in the full export (for review join-rate stats)
    places_stats.json       counts used by the feasibility gate and docs/data_decisions.md
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from src.common import (
    load_config,
    normalize_city,
    parse_categories,
    parse_city,
    parse_zip,
    processed_dir,
    sha256_file,
    source_files,
    to_bool,
    to_float,
    write_json,
)

DAY_ABBR = {
    "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu",
    "friday": "Fri", "saturday": "Sat", "sunday": "Sun",
}


def parse_hours(value: Any) -> str | None:
    """open_hours JSON -> 'Mon 9 am–5 pm; Tue ...'. None when no day has hours listed."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        obj = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    parts = []
    for day in DAY_ABBR:
        for k, v in obj.items():
            if str(k).strip().lower() == day and v not in (None, "", []):
                text = str(v).replace(" ", " ").replace("\n", ", ").strip()
                if text:
                    parts.append(f"{DAY_ABBR[day]} {text}")
    return "; ".join(parts) or None


def parse_star_distribution(value: Any, reviews_count: int | None) -> list[int] | None:
    """review_distribution JSON -> [n1..n5] overall star counts, only when they sum to reviews_count."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        obj = json.loads(value)
    except json.JSONDecodeError:
        return None
    counts = []
    for s in range(1, 6):
        v = to_float(obj.get(f"{s}_star_reviews")) if isinstance(obj, dict) else None
        counts.append(int(v) if v is not None and v >= 0 else 0)
    total = sum(counts)
    if total == 0 or reviews_count is None or total != reviews_count:
        return None
    return counts


def clean_rating(rating_raw: Any, count_raw: Any) -> tuple[float | None, int | None, str | None]:
    """Return (rating, reviews_count, issue). A 0 rating with 0 reviews is 'unrated', not 0 stars."""
    r = to_float(rating_raw)
    c = to_float(count_raw)
    count = int(c) if c is not None and c >= 0 else None
    if r is None:
        return None, count, "rating_missing"
    if r == 0 and (count in (0, None)):
        return None, count, "unrated_zero_placeholder"
    if not 1.0 <= r <= 5.0:
        return None, count, "rating_out_of_range"
    if count == 0:
        return None, count, "rating_without_reviews"
    return r, count, None


def _read_chunks(source: str):
    cfg = load_config("columns")
    pcfg = cfg["places"]
    path = source_files(source)["places_file"]
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. See README 'Raw data'.")
    header = pd.read_csv(path, nrows=0).columns.tolist()
    mapping = {k: v for k, v in pcfg["columns"].items() if v}
    missing_required = [k for k in pcfg["required"] if mapping.get(k) not in header]
    if missing_required:
        raise KeyError(f"Places export lacks required fields {missing_required}; update configs/columns.yaml")
    present = {k: v for k, v in mapping.items() if v in header}
    absent = sorted(set(pcfg["columns"]) - set(present))
    reader = pd.read_csv(
        path, usecols=list(present.values()), dtype=str, chunksize=cfg["chunksize"],
        keep_default_na=True, encoding="utf-8", on_bad_lines="warn",
    )
    return path, present, absent, reader


def clean_chunk(raw: pd.DataFrame, present: dict[str, str]) -> pd.DataFrame:
    df = raw.rename(columns={v: k for k, v in present.items()})
    for col in ("city", "zipcode", "all_categories", "address", "phone", "website", "maps_url", "review_distribution",
                "hours", "permanently_closed", "temporarily_closed", "business_status"):
        if col not in df.columns:
            df[col] = None
    out = pd.DataFrame({"place_id": df["place_id"].str.strip(), "name": df["name"].str.strip()})
    out["category"] = df["category"].str.strip()
    out["categories"] = [
        "|".join(parse_categories(c, a)) for c, a in zip(df["category"], df["all_categories"])
    ]
    out["address"] = df["address"].str.strip()
    parsed_city = df["address"].map(parse_city)
    given_city = df["city"].map(normalize_city)
    out["city"] = given_city.where(given_city.notna(), parsed_city)
    out["city_source"] = np.where(given_city.notna(), "city_column",
                                  np.where(parsed_city.notna(), "parsed_from_address", "unknown"))
    given_zip = df["zipcode"].where(df["zipcode"].astype(str).str.fullmatch(r"\d{5}"), None)
    out["zipcode"] = given_zip.where(given_zip.notna(), df["address"].map(parse_zip))
    out["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    out["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    bad_coord = ~out["lat"].between(-90, 90) | ~out["lon"].between(-180, 180)
    out.loc[bad_coord, ["lat", "lon"]] = np.nan
    out["rating_raw"] = df["rating"]
    out["reviews_count_raw"] = df["reviews_count"]
    triples = [clean_rating(r, c) for r, c in zip(df["rating"], df["reviews_count"])]
    out["rating"] = pd.array([t[0] for t in triples], dtype="Float64")
    out["reviews_count"] = pd.array([t[1] for t in triples], dtype="Int64")
    out["rating_issue"] = [t[2] for t in triples]
    dist = [parse_star_distribution(v, t[1]) if t[0] is not None else None
            for v, t in zip(df["review_distribution"], triples)]
    for s in range(1, 6):
        out[f"overall_stars_{s}"] = pd.array([None if d is None else d[s - 1] for d in dist], dtype="Int64")
    out["hours_raw_present"] = df["hours"].notna()
    out["hours_text"] = df["hours"].map(parse_hours)
    out["phone"] = df["phone"].str.strip()
    out["website"] = df["website"].str.strip()
    out["maps_url"] = df["maps_url"].str.strip()
    out["permanently_closed_raw"] = df["permanently_closed"]
    out["temporarily_closed_raw"] = df["temporarily_closed"]
    perm = df["permanently_closed"].map(to_bool)
    temp = df["temporarily_closed"].map(to_bool)
    status = df["business_status"].astype(str).str.upper()
    perm = perm.where(~status.str.contains("CLOSED_PERMANENTLY", na=False), True)
    temp = temp.where(~status.str.contains("CLOSED_TEMPORARILY", na=False), True)
    out["permanently_closed"] = perm.astype("boolean")
    out["temporarily_closed"] = temp.astype("boolean")
    return out


def dedupe_places(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    df = df.copy()
    df["_filled"] = df.notna().sum(axis=1)
    df["_count"] = df["reviews_count"].fillna(-1)
    df = df.sort_values(["place_id", "_count", "_filled"], ascending=[True, False, False], kind="stable")
    before = len(df)
    df = df.drop_duplicates("place_id", keep="first").drop(columns=["_filled", "_count"])
    return df.reset_index(drop=True), before - len(df)


def run(source: str) -> dict[str, Any]:
    targets = {c.lower() for c in load_config("services")["target_area"]["cities"]}
    path, present, absent, reader = _read_chunks(source)
    kept, all_ids = [], []
    total = 0
    city_counts: Counter[str] = Counter()
    city_source_counts: Counter[str] = Counter()
    for raw in reader:
        total += len(raw)
        chunk = clean_chunk(raw, present)
        all_ids.append(chunk["place_id"])
        city_counts.update(chunk["city"].dropna())
        city_source_counts.update(chunk["city_source"])
        kept.append(chunk[chunk["city"].str.lower().isin(targets)])
    target = pd.concat(kept, ignore_index=True) if kept else pd.DataFrame()
    target, dupes = dedupe_places(target)
    ids = pd.Series(pd.concat(all_ids).dropna().unique(), name="place_id")

    out_dir = processed_dir(source)
    target.to_parquet(out_dir / "places_target.parquet", index=False)
    ids.to_frame().to_parquet(out_dir / "places_all_ids.parquet", index=False)

    def frac(mask: pd.Series) -> float:
        return round(float(mask.mean()), 4) if len(mask) else math.nan

    stats = {
        "source": source,
        "file": path,
        "sha256": sha256_file(path),
        "rows_read": total,
        "unique_place_ids_full_export": int(ids.size),
        "fields_present": present,
        "fields_absent_or_unmapped": absent,
        "city_source_counts": dict(city_source_counts),
        "top_cities_full_export": city_counts.most_common(40),
        "target_cities": sorted(targets),
        "target_rows_after_dedupe": int(len(target)),
        "target_duplicate_rows_removed": int(dupes),
        "target_by_city": target["city"].value_counts().to_dict(),
        "target_fill_rates": {
            "rating_usable": frac(target["rating"].notna()),
            "overall_star_distribution": frac(target["overall_stars_1"].notna()),
            "hours_listed": frac(target["hours_text"].notna()),
            "phone": frac(target["phone"].notna()),
            "website": frac(target["website"].notna()),
            "zipcode_parsed": frac(target["zipcode"].notna()),
            "coordinates": frac(target["lat"].notna() & target["lon"].notna()),
        },
        "target_rating_issues": target["rating_issue"].value_counts(dropna=True).to_dict(),
        "target_closure": {
            "permanently_closed_true": int(target["permanently_closed"].eq(True).sum()),
            "permanently_closed_unknown": int(target["permanently_closed"].isna().sum()),
            "temporarily_closed_true": int(target["temporarily_closed"].eq(True).sum()),
            "temporarily_closed_unknown": int(target["temporarily_closed"].isna().sum()),
        },
    }
    write_json(out_dir / "places_stats.json", stats)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["real", "synthetic"], default="real")
    args = ap.parse_args()
    stats = run(args.source)
    print(json.dumps({k: stats[k] for k in ("rows_read", "target_rows_after_dedupe", "target_by_city",
                                           "target_fill_rates", "target_rating_issues")}, indent=2, default=str))


if __name__ == "__main__":
    main()

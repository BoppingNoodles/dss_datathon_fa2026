"""Clean the sampled Google Maps Reviews export and aggregate it per place.

    uv run python -m src.data.reviews --source real

Only explicitly mapped columns are read (configs/columns.yaml). Reviewer names, profile
URLs, avatars, photos, and owner responses are never loaded into memory or written out.

Outputs (data/processed/<source>/):
    reviews_target.parquet     cleaned review rows for target-area places (no reviewer identity)
    review_aggregates.parquet  one row per place_id: sampled-review evidence
    reviews_stats.json         join-rate and cleaning counts

Sampled-review counts are evidence about the sample. They are never added to, or substituted
for, the Places overall `rating` / `reviews_count`.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

import numpy as np
import pandas as pd

from src.common import load_config, processed_dir, sha256_file, source_files, to_float, write_json

_EMPTY_TEXT = re.compile(r'^\s*(positive:\s*"?\s*"?\s*negative:\s*"?\s*"?)?\s*$', re.IGNORECASE)


def clean_review_text(value: Any) -> str | None:
    """Return review text, or None when it is absent or only an empty template."""
    if not isinstance(value, str):
        return None
    s = value.replace("\r", " ").strip()
    if not s or _EMPTY_TEXT.match(s):
        return None
    return re.sub(r"[ \t]+", " ", s)


def clean_star(value: Any) -> float | None:
    """Google review stars are 1-5. 0 or anything else is treated as missing, not as a score."""
    f = to_float(value)
    if f is None or not 1 <= f <= 5:
        return None
    return float(round(f))


def _guard_columns(mapping: dict[str, str], fragments: list[str]) -> None:
    for logical, col in mapping.items():
        if any(fr in col.lower() for fr in fragments):
            raise ValueError(f"Refusing to read column {col!r} (mapped as {logical}): it may hold reviewer identity")


def clean_chunk(raw: pd.DataFrame, present: dict[str, str]) -> pd.DataFrame:
    df = raw.rename(columns={v: k for k, v in present.items()})
    for col in ("review_id", "review", "review_date", "place_rating", "place_reviews_count"):
        if col not in df.columns:
            df[col] = None
    out = pd.DataFrame({"place_id": df["place_id"].astype(str).str.strip()})
    out["review_id"] = df["review_id"]
    out["review_rating_raw"] = df["review_rating"]
    out["review_rating"] = pd.array(df["review_rating"].map(clean_star), dtype="Float64")
    out["review_text"] = df["review"].map(clean_review_text)
    out["review_date"] = pd.to_datetime(df["review_date"], errors="coerce", utc=True)
    out["place_rating_on_review"] = pd.array(df["place_rating"].map(to_float), dtype="Float64")
    cnt = pd.to_numeric(df["place_reviews_count"].astype(str).str.replace(",", ""), errors="coerce")
    out["place_reviews_count_on_review"] = cnt.where(cnt >= 0).round().astype("Int64")
    return out


def dedupe_reviews(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    n0 = len(df)
    has_id = df["review_id"].notna()
    by_id = pd.concat([df[has_id].drop_duplicates(["place_id", "review_id"]), df[~has_id]])
    n1 = len(by_id)
    # Content duplicates: identical text, stars, and date at the same place. Rows with no text
    # are not content-deduplicated (two empty 5-star reviews can be distinct people).
    has_text = by_id["review_text"].notna()
    content = by_id[has_text].drop_duplicates(["place_id", "review_text", "review_rating", "review_date"])
    out = pd.concat([content, by_id[~has_text]]).sort_index()
    return out.reset_index(drop=True), {
        "duplicate_review_id_rows": n0 - n1,
        "duplicate_content_rows": n1 - len(out),
    }


def aggregate(reviews: pd.DataFrame) -> pd.DataFrame:
    """One row per place: sampled counts, date range, star distribution, overall fields seen on rows."""
    if reviews.empty:
        return pd.DataFrame(columns=["place_id"])
    g = reviews.groupby("place_id", sort=True)
    agg = pd.DataFrame({
        "sampled_review_count": g.size(),
        "sampled_rated_count": g["review_rating"].count(),
        "sampled_text_count": g["review_text"].count(),
        "sampled_date_min": g["review_date"].min(),
        "sampled_date_max": g["review_date"].max(),
        "sampled_mean_stars": g["review_rating"].mean().round(2),
    })
    stars = (reviews.dropna(subset=["review_rating"])
             .assign(star=lambda d: d["review_rating"].astype(int))
             .pivot_table(index="place_id", columns="star", values="review_text",
                          aggfunc="size", fill_value=0))
    for s in range(1, 6):
        agg[f"sampled_stars_{s}"] = stars[s] if s in stars.columns else 0
    agg[[f"sampled_stars_{s}" for s in range(1, 6)]] = (
        agg[[f"sampled_stars_{s}" for s in range(1, 6)]].fillna(0).astype(int))

    # Overall rating/count fields repeated on review rows: deduplicate, keep provenance,
    # and flag conflicts rather than averaging them.
    def distinct(series: pd.Series) -> list:
        return sorted({float(x) for x in series.dropna()})

    agg["overall_rating_values_on_reviews"] = g["place_rating_on_review"].apply(distinct)
    agg["overall_count_values_on_reviews"] = g["place_reviews_count_on_review"].apply(distinct)
    agg["overall_fields_conflict"] = (agg["overall_rating_values_on_reviews"].map(len) > 1) | (
        agg["overall_count_values_on_reviews"].map(len) > 1)
    agg["overall_rating_from_reviews"] = agg["overall_rating_values_on_reviews"].map(
        lambda v: v[-1] if len(v) == 1 else np.nan)
    agg["overall_count_from_reviews"] = agg["overall_count_values_on_reviews"].map(
        lambda v: v[-1] if len(v) == 1 else np.nan)
    agg["overall_rating_values_on_reviews"] = agg["overall_rating_values_on_reviews"].map(json.dumps)
    agg["overall_count_values_on_reviews"] = agg["overall_count_values_on_reviews"].map(json.dumps)
    return agg.reset_index()


def run(source: str) -> dict[str, Any]:
    cfg = load_config("columns")
    rcfg = cfg["reviews"]
    path = source_files(source)["reviews_file"]
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. See README 'Raw data'.")
    out_dir = processed_dir(source)
    target_ids = set(pd.read_parquet(out_dir / "places_target.parquet", columns=["place_id"])["place_id"])
    all_ids = set(pd.read_parquet(out_dir / "places_all_ids.parquet")["place_id"])

    header = pd.read_csv(path, nrows=0).columns.tolist()
    mapping = {k: v for k, v in rcfg["columns"].items() if v}
    _guard_columns(mapping, rcfg["never_read_fragments"])
    missing_required = [k for k in rcfg["required"] if mapping.get(k) not in header]
    if missing_required:
        raise KeyError(f"Reviews export lacks required fields {missing_required}; update configs/columns.yaml")
    present = {k: v for k, v in mapping.items() if v in header}

    total = in_places = zero_stars = 0
    unique_places_reviewed: set[str] = set()
    kept = []
    for raw in pd.read_csv(path, usecols=list(present.values()), dtype=str,
                           chunksize=cfg["chunksize"], encoding="utf-8", on_bad_lines="warn"):
        total += len(raw)
        pid = raw[present["place_id"]].astype(str).str.strip()
        unique_places_reviewed.update(pid)
        in_places += int(pid.isin(all_ids).sum())
        zero_stars += int(pd.to_numeric(raw[present["review_rating"]], errors="coerce").eq(0).sum())
        sub = raw[pid.isin(target_ids)]
        if len(sub):
            kept.append(clean_chunk(sub, present))
    reviews = pd.concat(kept, ignore_index=True) if kept else clean_chunk(
        pd.DataFrame(columns=list(present.values())), present)
    reviews, dupes = dedupe_reviews(reviews)
    agg = aggregate(reviews)

    reviews.drop(columns=["review_rating_raw"]).to_parquet(out_dir / "reviews_target.parquet", index=False)
    agg.to_parquet(out_dir / "review_aggregates.parquet", index=False)

    stats = {
        "source": source,
        "file": path,
        "sha256": sha256_file(path),
        "columns_read": present,
        "rows_read": total,
        "unique_place_ids_in_reviews": len(unique_places_reviewed),
        "rows_matching_any_places_id": in_places,
        "row_match_rate_full_places": round(in_places / total, 4) if total else None,
        "target_rows_before_dedupe": int(len(reviews) + sum(dupes.values())),
        **dupes,
        "target_rows_after_dedupe": int(len(reviews)),
        "target_rows_with_valid_stars": int(reviews["review_rating"].notna().sum()),
        "target_rows_with_text": int(reviews["review_text"].notna().sum()),
        "target_places_with_sampled_reviews": int(len(agg)),
        "target_places_total": len(target_ids),
        "target_place_coverage_rate": round(len(agg) / len(target_ids), 4) if target_ids else None,
        "rows_with_zero_stars_full_export": zero_stars,
        "target_top2_places_share_of_rows": round(float(reviews["place_id"].value_counts().head(2).sum() / len(reviews)), 4) if len(reviews) else None,
        "target_max_rows_single_place": int(reviews["place_id"].value_counts().max()) if len(reviews) else 0,
        "target_places_overall_fields_conflict": int(agg["overall_fields_conflict"].sum()) if len(agg) else 0,
        "date_min": reviews["review_date"].min(),
        "date_max": reviews["review_date"].max(),
    }
    write_json(out_dir / "reviews_stats.json", stats)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["real", "synthetic"], default="real")
    args = ap.parse_args()
    print(json.dumps(run(args.source), indent=2, default=str))


if __name__ == "__main__":
    main()

"""Sample records for the independent hand audit -> reports/data_audit.csv.

    uv run python -m src.audit.data_audit --source real

Each row is one check on one record: original value, transformed value, and an automated
flag. Columns reviewer / finding / correction / reviewed_on are left blank for the human
reviewer. Re-running preserves any rows already reviewed (matched on audit_id).
"""

from __future__ import annotations

import argparse
from typing import Any

import numpy as np
import pandas as pd

from src.common import REPORTS, haversine_miles, load_config, none_if_nan, processed_dir, resolve

COLUMNS = ["audit_id", "dataset", "record_key", "record_label", "check", "original_value",
           "transformed_value", "auto_flag", "reviewer", "finding", "correction", "reviewed_on"]


def _row(dataset: str, key: str, label: str, check: str, orig: Any, trans: Any, flag: str | None) -> dict:
    return {"audit_id": f"{dataset}:{key}:{check}", "dataset": dataset, "record_key": key,
            "record_label": label, "check": check, "original_value": none_if_nan(orig),
            "transformed_value": none_if_nan(trans), "auto_flag": flag}


def _stratified(df: pd.DataFrame, by: str, n: int, seed: int) -> pd.DataFrame:
    if len(df) <= n:
        return df
    groups = df[by].fillna("_none").unique()
    per = max(1, n // len(groups))
    parts = [g.sample(min(len(g), per), random_state=seed) for _, g in df.groupby(by, dropna=False)]
    out = pd.concat(parts)
    if len(out) < n:
        out = pd.concat([out, df.drop(out.index).sample(n - len(out), random_state=seed)])
    return out.sample(n, random_state=seed) if len(out) > n else out


def service_rows(cand: pd.DataFrame, n: int, seed: int) -> list[dict]:
    rows = []
    for _, r in _stratified(cand, "family", n, seed).iterrows():
        k, lab = r["place_id"], r["name"]
        rows += [
            _row("services", k, lab, "category_relevance", r["categories"], f"{r['family']} ({r['taxonomy_evidence']})",
                 "review: does this place provide the mapped service?"),
            _row("services", k, lab, "rating_units", f"rating={r['rating_raw']}; count={r['reviews_count_raw']}",
                 f"rating={none_if_nan(r['rating'])}; count={none_if_nan(r['reviews_count'])}", none_if_nan(r["rating_issue"])),
            _row("services", k, lab, "closure_flags",
                 f"perm={r['permanently_closed_raw']}; temp={r['temporarily_closed_raw']}",
                 f"perm={none_if_nan(r['permanently_closed'])}; temp={none_if_nan(r['temporarily_closed'])}",
                 "unknown_closure" if pd.isna(r["permanently_closed"]) else None),
            _row("services", k, lab, "address_parse", r["address"], f"city={r['city']}; zip={none_if_nan(r['zipcode'])}",
                 "zip_missing" if pd.isna(r["zipcode"]) else None),
            _row("services", k, lab, "public_community_claim", r["verification_status"],
                 none_if_nan(r.get("official_url")),
                 "assistance_family_unverified" if r["assistance"] and r["verification_status"] == "unverified" else None),
            _row("services", k, lab, "age_note", f"min={none_if_nan(r.get('min_age'))}; max={none_if_nan(r.get('max_age'))}",
                 none_if_nan(r.get("age_criteria_text")) or "eligibility_needs_confirmation", None),
        ]
    return rows


def review_rows(reviews: pd.DataFrame, places: pd.DataFrame, n: int, seed: int) -> list[dict]:
    if reviews.empty:
        return [_row("reviews", "-", "-", "pending", None, None, "no target-area review rows")]
    names = places.set_index("place_id")["name"]
    rows = []
    for _, r in reviews.sample(min(n, len(reviews)), random_state=seed).iterrows():
        k = str(none_if_nan(r["review_id"]) or f"{r['place_id']}@{r['review_date']}")
        attached = r["place_id"] in names.index
        rows += [
            _row("reviews", k, names.get(r["place_id"], "UNMATCHED"), "review_attachment", r["place_id"],
                 names.get(r["place_id"]), None if attached else "place_id_not_in_places"),
            _row("reviews", k, names.get(r["place_id"], ""), "review_stars",
                 none_if_nan(r["review_rating"]), none_if_nan(r["review_rating"]), None),
            _row("reviews", k, names.get(r["place_id"], ""), "overall_fields_on_review",
                 f"rating={none_if_nan(r['place_rating_on_review'])}; count={none_if_nan(r['place_reviews_count_on_review'])}",
                 "not added to Places reviews_count", None),
            _row("reviews", k, names.get(r["place_id"], ""), "reviewer_identity_absent",
                 "columns: " + ",".join(reviews.columns), "no reviewer fields",
                 "IDENTITY_COLUMN_PRESENT" if any(c.startswith("reviewer") for c in reviews.columns) else None),
        ]
    return rows


def geo_rows(cand: pd.DataFrame, refs: pd.DataFrame, n: int, seed: int) -> list[dict]:
    zips = refs[refs["area_type"] == "zip"].set_index("area_key")
    s = cand[cand["zipcode"].isin(zips.index)]
    rows = []
    for _, r in s.sample(min(n, len(s)), random_state=seed).iterrows():
        ref = zips.loc[r["zipcode"]]
        d = float(haversine_miles(ref["lat"], ref["lon"], r["lat"], r["lon"]))
        rows.append(_row("geo_pairs", r["place_id"], r["name"], "service_to_zip_center",
                         f"place=({r['lat']:.4f},{r['lon']:.4f}); zip {r['zipcode']} center=({ref['lat']:.4f},{ref['lon']:.4f})",
                         f"{d:.2f} mi straight-line", "far_from_own_zip_center" if d > 3 else None))
    return rows


def external_rows(name: str, spec: dict, n: int, seed: int, source: str = "real") -> list[dict]:
    spec = {**spec, "path":spec["path"].format(source=source)}
    path = resolve(spec["path"])
    if not path.exists():
        return [_row(name, "-", "-", "pending", None, None, f"{spec['path']} not produced yet (Person 1)")]
    df = pd.read_parquet(path)
    rows = []
    for _, r in df.sample(min(n, len(df)), random_state=seed).iterrows():
        k = str(r.get(spec["key"], r.name))
        for c in spec["checks"]:
            trans = "; ".join(f"{t}={none_if_nan(r.get(t))}" for t in c["transformed"])
            missing = [t for t in [c["original"], *c["transformed"]] if t not in df.columns]
            rows.append(_row(name, k, "", c["check"], r.get(c["original"]), trans,
                             f"missing columns {missing}" if missing else None))
    return rows


def housing_privacy_rows(spec: dict, source: str = "real") -> list[dict]:
    spec = {**spec, "path":spec["path"].format(source=source)}
    path = resolve(spec["path"])
    if not path.exists():
        return [_row("housing_public_output", "-", "-", "address_suppression", None, None,
                     f"{spec['path']} not produced yet (Person 1)")]
    cols = pd.read_parquet(path).columns
    bad = [c for c in cols if c in spec["forbidden_columns"]]
    return [_row("housing_public_output", path.name, "", "address_suppression", ",".join(cols),
                 "forbidden columns: " + (",".join(bad) or "none"), "PRIVACY_VIOLATION" if bad else None)]


def run(source: str) -> pd.DataFrame:
    cfg = load_config("audit")
    seed, n = cfg["seed"], cfg["samples"]
    d = processed_dir(source)
    cand = pd.read_parquet(d / "service_candidates.parquet")
    places = pd.read_parquet(d / "places_target.parquet", columns=["place_id", "name"])
    reviews = pd.read_parquet(d / "reviews_target.parquet")
    refs = pd.read_parquet(d / "area_reference_points.parquet")

    rows = (service_rows(cand, n["services"], seed) + review_rows(reviews, places, n["reviews"], seed)
            + geo_rows(cand, refs, n["geo_pairs"], seed)
            + external_rows("jobs", cfg["external"]["jobs"], n["jobs"], seed, source)
            + external_rows("housing", cfg["external"]["housing"], n["housing"], seed, source)
            + housing_privacy_rows(cfg["external"]["housing_public_output"], source))
    out = pd.DataFrame(rows).reindex(columns=COLUMNS)
    out.insert(1, "source", source)

    path = REPORTS / ("data_audit.csv" if source == "real" else f"data_audit_{source}.csv")
    if path.exists():  # keep human review work
        prev = pd.read_csv(path, dtype=str)
        done = prev[prev[["reviewer", "finding"]].notna().any(axis=1)]
        out = pd.concat([done, out[~out["audit_id"].isin(done["audit_id"])]], ignore_index=True)
    REPORTS.mkdir(exist_ok=True)
    out.to_csv(path, index=False)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["real", "synthetic"], default="real")
    out = run(ap.parse_args().source)
    print(out.groupby("dataset").agg(rows=("audit_id", "size"), auto_flags=("auto_flag", "count")).to_string())


if __name__ == "__main__":
    main()

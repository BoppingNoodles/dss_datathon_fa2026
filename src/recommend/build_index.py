"""Precompute the service candidate index the API ranks at request time.

    uv run python -m src.recommend.build_index --source real

Joins (all keyed by place_id, all LEFT joins from Places so a missing review sample or
missing verification never removes a service):
    places_target  +  taxonomy  +  review_aggregates  +  service_verification.csv  +  review_snippets.csv

Outputs (data/processed/<source>/):
    service_candidates.parquet   one row per place that maps to at least one service family
    area_reference_points.parquet  city / ZIP representative points derived from Places coordinates
    family_rating_priors.json    C (mean overall rating) per family, used in (n*r + m*C)/(n+m)
    index_stats.json
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import numpy as np
import pandas as pd

from src.common import load_config, processed_dir, source_files, write_json
from src.recommend.taxonomy import classify, family_by_key

VERIFICATION_COLUMNS = [
    "place_id", "provider_type", "relevant_service", "official_url", "min_age", "max_age",
    "age_criteria_text", "cost_eligibility_notes", "service_area", "checked_on", "checked_by", "notes",
]
SNIPPET_COLUMNS = ["place_id", "snippet", "topic", "review_date", "checked_by", "checked_on"]
PROVIDER_TYPES = {"public", "nonprofit_community", "private", "unknown"}


def bayes_score(r: pd.Series, n: pd.Series, c: pd.Series, m: float) -> pd.Series:
    """Count-aware rating (n*r + m*C)/(n+m). NaN when the place has no usable overall rating."""
    r = r.astype(float)
    n = n.astype(float)
    c = c.astype(float)
    out = (n * r + m * c) / (n + m)
    return out.where(r.notna() & n.notna() & (n > 0))


def load_verification(path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=VERIFICATION_COLUMNS)
    v = pd.read_csv(path, dtype=str).reindex(columns=VERIFICATION_COLUMNS)
    v = v[v["place_id"].notna() & v["place_id"].str.strip().ne("")]
    v["provider_type"] = v["provider_type"].str.strip().str.lower()
    bad = ~v["provider_type"].isin(PROVIDER_TYPES)
    if bad.any():
        raise ValueError(f"service_verification.csv has invalid provider_type rows: {v.loc[bad, 'place_id'].tolist()}")
    if v["place_id"].duplicated().any():
        raise ValueError("service_verification.csv must have one row per place_id")
    for col in ("min_age", "max_age"):
        v[col] = pd.to_numeric(v[col], errors="coerce").astype("Int64")
    # A row only counts as verified with an official source and a check date.
    complete = v["official_url"].notna() & v["checked_on"].notna()
    v["verification_status"] = np.select(
        [complete & v["provider_type"].isin(["public", "nonprofit_community"]),
         complete & v["provider_type"].eq("private"),
         complete],
        ["verified_public_community", "verified_private", "verified_type_unknown"],
        default="verification_incomplete",
    )
    return v


def load_snippets(path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=SNIPPET_COLUMNS)
    s = pd.read_csv(path, dtype=str).reindex(columns=SNIPPET_COLUMNS)
    # Only manually checked snippets are publishable.
    s = s[s["snippet"].notna() & s["checked_by"].notna() & s["checked_on"].notna()]
    return s


def reference_points(places: pd.DataFrame, min_records: int) -> pd.DataFrame:
    """Median coordinate of Places records per city and per ZIP (a documented, derived lookup).

    These are area centers, not anyone's home; distances from them are labeled as such.
    """
    rows = []
    for area_type, col in (("city", "city"), ("zip", "zipcode")):
        g = places.dropna(subset=[col, "lat", "lon"]).groupby(col)
        agg = g.agg(lat=("lat", "median"), lon=("lon", "median"), n_records=("place_id", "size")).reset_index()
        agg = agg[agg["n_records"] >= min_records]
        for r in agg.itertuples(index=False):
            rows.append({"area_type": area_type, "area_key": str(getattr(r, col)).lower(),
                         "area_label": str(getattr(r, col)), "lat": r.lat, "lon": r.lon,
                         "n_records": int(r.n_records),
                         "method": f"median Places coordinate ({area_type})"})
    zip_city = (places.dropna(subset=["zipcode", "city"]).groupby("zipcode")["city"]
                .agg(lambda s: s.value_counts().index[0]))
    out = pd.DataFrame(rows)
    out["city_for_zip"] = np.where(out["area_type"].eq("zip"), out["area_label"].map(zip_city), None)
    return out


def run(source: str) -> dict[str, Any]:
    out_dir = processed_dir(source)
    files = source_files(source)
    cfg = load_config("services")
    m = float(cfg["ranking"]["prior_weight_m"])

    places = pd.read_parquet(out_dir / "places_target.parquet")
    res = places["categories"].fillna("").map(lambda s: classify([t for t in s.split("|") if t]))
    places["families"] = res.map(lambda r: "|".join(r[0]))
    places["family"] = res.map(lambda r: r[0][0] if r[0] else None)
    places["taxonomy_evidence"] = res.map(lambda r: r[1])
    cand = places[places["family"].notna()].copy()

    fams = family_by_key()
    cand["family_label"] = cand["family"].map(lambda k: fams[k].label)
    cand["assistance"] = cand["family"].map(lambda k: fams[k].assistance)
    cand["needs"] = cand["families"].map(
        lambda s: "|".join(sorted({n for k in s.split("|") for n in fams[k].needs})))

    agg_path = out_dir / "review_aggregates.parquet"
    agg = pd.read_parquet(agg_path) if agg_path.exists() else pd.DataFrame(columns=["place_id"])
    cand = cand.merge(agg, on="place_id", how="left", validate="one_to_one")
    cand["sampled_review_count"] = cand["sampled_review_count"].fillna(0).astype(int)

    ver = load_verification(files["verification_file"])
    cand = cand.merge(ver, on="place_id", how="left", validate="one_to_one")
    cand["verification_status"] = cand["verification_status"].fillna("unverified")
    unmatched_ver = sorted(set(ver["place_id"]) - set(cand["place_id"]))

    snip = load_snippets(files["snippets_file"])
    snip_json = (snip.groupby("place_id")
                 .apply(lambda d: json.dumps(d[["snippet", "topic", "review_date"]].to_dict("records")),
                        include_groups=False)
                 .rename("snippets_json")) if len(snip) else pd.Series(dtype=str, name="snippets_json")
    cand = cand.merge(snip_json, left_on="place_id", right_index=True, how="left")

    # Family prior C: mean overall rating among rated candidates of the same family.
    rated = cand[cand["rating"].notna()]
    priors = rated.groupby("family")["rating"].agg(["mean", "size"]).round(4)
    global_c = float(rated["rating"].mean()) if len(rated) else np.nan
    stable = priors[priors["size"] >= int(cfg["ranking"]["min_rated_for_family_prior"])]
    cand["family_mean_rating"] = cand["family"].map(stable["mean"]).fillna(global_c)
    cand["prior_source"] = np.where(cand["family"].isin(stable.index), "family_mean", "all_family_mean")
    cand["ranking_score"] = bayes_score(cand["rating"], cand["reviews_count"], cand["family_mean_rating"], m).round(4)
    cand["prior_weight_m"] = m

    cand.to_parquet(out_dir / "service_candidates.parquet", index=False)
    refs = reference_points(places, int(cfg["reference_point_min_records"]))
    refs.to_parquet(out_dir / "area_reference_points.parquet", index=False)
    write_json(out_dir / "family_rating_priors.json", {
        "prior_weight_m": m, "global_mean": global_c,
        "min_rated_for_family_prior": int(cfg["ranking"]["min_rated_for_family_prior"]),
        "families": {k: {"family_mean": float(r["mean"]), "rated_candidates": int(r["size"]),
                         "C_used": float(r["mean"]) if k in stable.index else global_c}
                     for k, r in priors.iterrows()},
    })

    stats = {
        "source": source,
        "candidates": int(len(cand)),
        "by_family": cand["family"].value_counts().to_dict(),
        "rated_by_family": rated["family"].value_counts().to_dict(),
        "with_sampled_reviews": int((cand["sampled_review_count"] > 0).sum()),
        "verification_status": cand["verification_status"].value_counts().to_dict(),
        "verification_rows_not_matching_a_candidate": unmatched_ver,
        "published_snippets": int(len(snip)),
        "reference_points": refs["area_type"].value_counts().to_dict(),
    }
    write_json(out_dir / "index_stats.json", stats)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["real", "synthetic"], default="real")
    print(json.dumps(run(ap.parse_args().source), indent=2, default=str))


if __name__ == "__main__":
    main()

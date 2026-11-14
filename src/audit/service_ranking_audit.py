"""Descriptive service-ranking audit across service families (Phoenix.md section 8).

    uv run python -m src.audit.service_ranking_audit --source real

Outputs:
    reports/service_ranking_audit.csv    per family x city: coverage, missing ratings,
                                         review-join rate, group sizes, what a strict
                                         "highly rated only" view would hide
    reports/ranking_sensitivity.csv      top-10 overlap vs the default prior weight m

This complements, and does not replace, the required NLP subgroup analysis. It makes no
claim about recommendation accuracy: there are no labeled relevance judgments.
"""

from __future__ import annotations

import argparse

import pandas as pd

from src.common import REPORTS, load_config, processed_dir
from src.recommend.build_index import bayes_score

AUDIT_FAMILIES_MIN = 3


def family_city_table(cand: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    c = cand.copy()
    active = ~c["permanently_closed"].eq(True)
    c = c[active]
    rated = c["rating"].notna()
    enough = c["reviews_count"].fillna(0) >= cfg["highly_rated_min_reviews"]
    high = rated & enough & (c["rating"] >= cfg["highly_rated_min_rating"])
    c = c.assign(_rated=rated, _high=high, _limited=~(rated & enough),
                 _sampled=c["sampled_review_count"] > 0,
                 _verified=c["verification_status"].eq("verified_public_community"),
                 _temp=c["temporarily_closed"].eq(True))
    g = c.groupby(["family", "city"])
    t = pd.DataFrame({
        "candidates_active": g.size(),
        "rated": g["_rated"].sum(),
        "highly_rated": g["_high"].sum(),
        "limited_review_evidence": g["_limited"].sum(),
        "with_sampled_reviews": g["_sampled"].sum(),
        "verified_public_community": g["_verified"].sum(),
        "temporarily_closed": g["_temp"].sum(),
    }).reset_index()
    t["missing_rating_rate"] = (1 - t["rated"] / t["candidates_active"]).round(3)
    t["review_join_rate"] = (t["with_sampled_reviews"] / t["candidates_active"]).round(3)
    t["hidden_by_highly_rated_only_view"] = t["candidates_active"] - t["highly_rated"]
    t["hidden_share"] = (t["hidden_by_highly_rated_only_view"] / t["candidates_active"]).round(3)
    return t.sort_values(["family", "candidates_active"], ascending=[True, False])


def sensitivity(cand: pd.DataFrame, cfg: dict, top_k: int = 10) -> pd.DataFrame:
    base_m = cfg["prior_weight_m"]
    c = cand[~cand["permanently_closed"].eq(True) & cand["rating"].notna() & cand["assistance"]].copy()
    rows = []
    for (fam, city), grp in c.groupby(["family", "city"]):
        if len(grp) < top_k:
            continue
        base = set(grp.assign(s=bayes_score(grp["rating"], grp["reviews_count"], grp["family_mean_rating"], base_m))
                   .nlargest(top_k, "s")["place_id"])
        for m in cfg["sensitivity_prior_weights"]:
            top = set(grp.assign(s=bayes_score(grp["rating"], grp["reviews_count"], grp["family_mean_rating"], m))
                      .nlargest(top_k, "s")["place_id"])
            rows.append({"family": fam, "city": city, "rated_candidates": len(grp), "m": m,
                         "baseline_m": base_m, f"top{top_k}_overlap_with_baseline": len(base & top) / top_k})
    return pd.DataFrame(rows)


def run(source: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = load_config("services")["ranking"]
    cand = pd.read_parquet(processed_dir(source) / "service_candidates.parquet")
    table = family_city_table(cand, cfg)
    if table["family"].nunique() < AUDIT_FAMILIES_MIN:
        raise RuntimeError(f"Fewer than {AUDIT_FAMILIES_MIN} service families available to audit")
    sens = sensitivity(cand, cfg)
    suffix = "" if source == "real" else f"_{source}"
    REPORTS.mkdir(exist_ok=True)
    table.to_csv(REPORTS / f"service_ranking_audit{suffix}.csv", index=False)
    sens.to_csv(REPORTS / f"ranking_sensitivity{suffix}.csv", index=False)
    return table, sens


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["real", "synthetic"], default="real")
    table, sens = run(ap.parse_args().source)
    fam = table.groupby("family")[["candidates_active", "rated", "highly_rated", "limited_review_evidence",
                                   "with_sampled_reviews", "verified_public_community"]].sum()
    fam["missing_rating_rate"] = (1 - fam["rated"] / fam["candidates_active"]).round(3)
    print(fam.sort_values("candidates_active", ascending=False).to_string())
    if len(sens):
        print("\nMean top-10 overlap with m=baseline:")
        print(sens.groupby("m")[sens.columns[-1]].mean().round(3).to_string())


if __name__ == "__main__":
    main()

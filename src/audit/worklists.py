"""Human-review worklists for Person 4.

    uv run python -m src.audit.worklists --source real

reports/taxonomy_spot_check.csv
    Up to 10 random places per service family. Mark `relevant` y/n; tighten
    configs/service_taxonomy.yaml include/exclude patterns for off-topic matches.

reports/verification_worklist.csv
    Highest-priority unverified assistance candidates per need (rated first, then nearest
    to each city center). Check the provider's OFFICIAL page, fill the blank columns, and
    copy finished rows into data/resources/service_verification.csv. Unknown stays blank.

reports/review_snippet_candidates.csv
    Keyword-retrieved candidate snippets about access, cost, wait time, or staff. Keyword
    hits are retrieval only: they do not establish sentiment or a fact. A reviewer reads
    each one, removes any personal detail, and copies approved rows into
    data/resources/review_snippets.csv with checked_by / checked_on.
"""

from __future__ import annotations

import argparse
import re

import pandas as pd

from src.common import REPORTS, processed_dir
from src.recommend.build_index import MAX_SNIPPET_CHARS, VERIFICATION_COLUMNS

MIN_CHARS = 40

TOPICS = {
    "access": r"\b(wheelchair|accessible|bus|parking|easy to find|appointment|walk[- ]in|id\b|documents?)",
    "cost": r"\b(free|cost|price|pay|paid|charge|insurance|medi-?cal|fee)",
    "wait_time": r"\b(wait|waited|line|queue|hours? long|quick|fast|slow)",
    "staff": r"\b(staff|volunteers?|nurse|doctor|case manager|counsel+or|rude|kind|helpful|respect)",
}
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_PHONE = re.compile(r"\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
_URL = re.compile(r"https?://\S+|www\.\S+")
_NAMEISH = re.compile(r"\b(?:[A-Z][a-z]+ ){1,2}[A-Z][a-z]+\b|\b(?:Dr|Mr|Mrs|Ms)\.? [A-Z][a-z]+")


def scrub(text: str) -> str:
    return _URL.sub("[link removed]", _PHONE.sub("[phone removed]", _EMAIL.sub("[email removed]", text)))


def taxonomy_spot_check(cand: pd.DataFrame, n: int = 10, seed: int = 11) -> pd.DataFrame:
    parts = [g.sample(min(n, len(g)), random_state=seed) for _, g in cand.groupby("family")]
    out = pd.concat(parts)[["family", "place_id", "name", "category", "categories", "taxonomy_evidence", "city", "website"]]
    return out.assign(relevant="", reviewer="", note="")


def verification_worklist(cand: pd.DataFrame, refs: pd.DataFrame, per_family_city: int = 3) -> pd.DataFrame:
    from src.common import haversine_miles

    c = cand[cand["assistance"] & ~cand["permanently_closed"].eq(True)
             & cand["verification_status"].eq("unverified")].copy()
    cities = refs[refs["area_type"] == "city"].set_index("area_label")
    c = c[c["city"].isin(cities.index)]
    c["miles_from_city_center"] = haversine_miles(
        c["city"].map(cities["lat"]), c["city"].map(cities["lon"]), c["lat"], c["lon"]).round(2)
    c["_has_rating"] = c["rating"].notna()
    c = c.sort_values(["family", "city", "_has_rating", "ranking_score", "miles_from_city_center"],
                      ascending=[True, True, False, False, True])
    picked = c.groupby(["family", "city"]).head(per_family_city)
    out = picked[["family", "city", "place_id", "name", "category", "website", "phone", "rating", "reviews_count"]]
    blanks = {col: "" for col in VERIFICATION_COLUMNS if col != "place_id"}
    return out.assign(**blanks)


def snippet_candidates(reviews: pd.DataFrame, cand: pd.DataFrame, per_place: int = 3) -> pd.DataFrame:
    # Reviews README: some reviews are very short ("Great!"); skip under MIN_CHARS.
    r = reviews[reviews["review_text"].str.len() >= MIN_CHARS].merge(
        cand[["place_id", "name", "family"]], on="place_id", how="inner")
    rows = []
    for _, x in r.iterrows():
        text = x["review_text"]
        for topic, pat in TOPICS.items():
            if re.search(pat, text, re.IGNORECASE):
                rows.append({
                    "place_id": x["place_id"], "place_name": x["name"], "family": x["family"], "topic": topic,
                    "review_stars": x["review_rating"], "review_date": pd.Timestamp(x["review_date"]).date() if pd.notna(x["review_date"]) else None,
                    "candidate_snippet": scrub(text[:MAX_SNIPPET_CHARS]),
                    "truncated": len(text) > MAX_SNIPPET_CHARS,
                    "possible_personal_name": bool(_NAMEISH.search(text)),
                    "approved": "", "checked_by": "", "checked_on": "",
                })
                break
    out = pd.DataFrame(rows)
    return out.groupby("place_id").head(per_place) if len(out) else out


def run(source: str) -> dict[str, int]:
    d = processed_dir(source)
    cand = pd.read_parquet(d / "service_candidates.parquet")
    refs = pd.read_parquet(d / "area_reference_points.parquet")
    reviews = pd.read_parquet(d / "reviews_target.parquet")
    suffix = "" if source == "real" else f"_{source}"
    REPORTS.mkdir(exist_ok=True)
    outs = {
        f"taxonomy_spot_check{suffix}.csv": taxonomy_spot_check(cand),
        f"verification_worklist{suffix}.csv": verification_worklist(cand, refs),
        f"review_snippet_candidates{suffix}.csv": snippet_candidates(reviews, cand),
    }
    for name, df in outs.items():
        df.to_csv(REPORTS / name, index=False)
    return {k: len(v) for k, v in outs.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["real", "synthetic"], default="real")
    print(run(ap.parse_args().source))


if __name__ == "__main__":
    main()

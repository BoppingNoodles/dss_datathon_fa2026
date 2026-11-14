"""Request-time service selection and ranking (Phoenix.md section 6).

Order of decisions:
    need relevance -> geographic compatibility -> availability / eligibility evidence -> rating and distance

Each candidate lands in exactly one group, checked in this order:
    temporarily_closed      withheld from the main lists, shown collapsed
    verified_support        official-source verified public/community provider (always shown)
    highly_rated            rating >= 4.0 and reviews_count >= 10 (Places overall values)
    other_rated             rated, below the design threshold (neutral wording, not "poor")
    limited_review_evidence no usable rating or fewer than 10 overall reviews (not a quality judgment)
    essential_services      ordinary essentials (grocery, bank, pharmacy, private medical): never "free assistance"

Permanently closed places are excluded from recommendations and counted in the notes.
The highly-rated threshold is never silently relaxed: when too few places meet it, a note says so.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.common import haversine_miles, load_config, none_if_nan, normalize_location_input
from src.recommend.taxonomy import families_for_need, family_by_key, need_labels

GROUP_ORDER = [
    "verified_support", "highly_rated", "other_rated", "limited_review_evidence",
    "essential_services", "temporarily_closed",
]
GROUP_LABELS = {
    "verified_support": "Verified public and community support",
    "highly_rated": "Highly rated nearby",
    "other_rated": "Other nearby options with ratings",
    "limited_review_evidence": "Limited review evidence",
    "essential_services": "Essential services (not free assistance; cost and eligibility unknown)",
    "temporarily_closed": "Marked temporarily closed in the dataset",
}
GROUP_NOTES = {
    "limited_review_evidence": "Few or no Google ratings. This is not a judgment of quality.",
    "essential_services": "Ordinary businesses that meet everyday needs. Not verified as free, public, or reentry support.",
    "temporarily_closed": "Listed as temporarily closed when the data was collected. Call before visiting.",
}
CONFIRM_PROMPT = "Call or check the provider's website to confirm current hours, services, cost, and eligibility."
SOURCE_NOTE = ("Google Maps Places export provided for the 8th Annual Datathon for Social Good. "
               "Collection date not documented; ratings and closure flags may be out of date.")


@dataclass
class ReferencePoint:
    lat: float | None
    lon: float | None
    label: str
    precision: str            # "zip_center" | "city_center" | "none"
    city: str | None
    zipcode: str | None


def resolve_location(location: str, refs: pd.DataFrame, candidates: pd.DataFrame) -> ReferencePoint:
    kind, key = normalize_location_input(location)
    if kind == "zip":
        hit = refs[(refs["area_type"] == "zip") & (refs["area_key"] == key)]
        if len(hit):
            r = hit.iloc[0]
            return ReferencePoint(float(r.lat), float(r.lon), f"center of ZIP {key}", "zip_center",
                                  none_if_nan(r.city_for_zip), key)
        city_guess = candidates.loc[candidates["zipcode"] == key, "city"].mode()
        if len(city_guess):  # ZIP present but too sparse for a center: fall back to its city
            return resolve_location(str(city_guess.iloc[0]), refs, candidates)
        return ReferencePoint(None, None, f"ZIP {key} (not resolvable)", "none", None, key)
    hit = refs[(refs["area_type"] == "city") & (refs["area_key"] == key.lower())]
    if len(hit):
        r = hit.iloc[0]
        return ReferencePoint(float(r.lat), float(r.lon), f"center of {r.area_label}", "city_center", r.area_label, None)
    return ReferencePoint(None, None, key, "none", key, None)


def age_status(age: int | None, row: pd.Series) -> tuple[str, str]:
    lo, hi = none_if_nan(row.get("min_age")), none_if_nan(row.get("max_age"))
    text = none_if_nan(row.get("age_criteria_text"))
    verified = str(row.get("verification_status", "")).startswith("verified")
    if not verified or (lo is None and hi is None):
        return "eligibility_needs_confirmation", "Eligibility needs confirmation with the provider."
    criterion = text or f"ages {lo if lo is not None else 'any'}-{hi if hi is not None else 'any'}"
    if age is None:
        return "age_not_provided", f"Published age criterion: {criterion}. Confirm with the provider."
    if (lo is None or age >= lo) and (hi is None or age <= hi):
        return "meets_published_age_criterion", f"Published age criterion: {criterion}. Your answer fits it; confirm other eligibility."
    return "outside_published_age_criterion", f"Published age criterion: {criterion}. Your answer is outside it; confirm with the provider."


def _assign_group(row: pd.Series, cfg: dict) -> str:
    if row["temporarily_closed"] is True:
        return "temporarily_closed"
    if not row["assistance"]:
        return "essential_services"
    if row["verification_status"] == "verified_public_community":
        return "verified_support"
    r, n = none_if_nan(row["rating"]), none_if_nan(row["reviews_count"])
    if r is None or n is None or n < cfg["highly_rated_min_reviews"]:
        return "limited_review_evidence"
    if r >= cfg["highly_rated_min_rating"]:
        return "highly_rated"
    return "other_rated"


def _card(row: pd.Series, age: int | None, ref: ReferencePoint, need: str) -> dict[str, Any]:
    status, note = age_status(age, row)
    snippets = json.loads(row["snippets_json"]) if isinstance(row.get("snippets_json"), str) else []
    dist = none_if_nan(row["distance_miles"])
    temp = row["temporarily_closed"]
    return {
        "place_id": row["place_id"],
        "name": row["name"],
        "need": need,
        "family": row["family"],
        "family_label": row["family_label"],
        "group": row["group"],
        "verification": {
            "status": row["verification_status"],
            "provider_type": none_if_nan(row.get("provider_type")),
            "official_url": none_if_nan(row.get("official_url")),
            "checked_on": none_if_nan(row.get("checked_on")),
            "cost_eligibility_notes": none_if_nan(row.get("cost_eligibility_notes")),
            "service_area": none_if_nan(row.get("service_area")),
        },
        "eligibility": {"age_status": status, "note": note},
        "rating": {
            "overall_rating": none_if_nan(row["rating"]),
            "overall_review_count": none_if_nan(row["reviews_count"]),
            "ranking_score": none_if_nan(row["ranking_score"]),
            "family_mean_rating": none_if_nan(round(float(row["family_mean_rating"]), 2)),
            "prior_weight_m": none_if_nan(row["prior_weight_m"]),
            "overall_star_distribution": _overall_dist(row),
            "source": "Google Maps Places overall rating, review count, and star breakdown",
        },
        "review_evidence": {
            "sampled_review_count": int(row["sampled_review_count"]),
            "sampled_text_count": int(none_if_nan(row.get("sampled_text_count")) or 0),
            "date_min": _iso(row.get("sampled_date_min")),
            "date_max": _iso(row.get("sampled_date_max")),
            "star_distribution": {str(s): int(none_if_nan(row.get(f"sampled_stars_{s}")) or 0) for s in range(1, 6)},
            "snippets": [{"text": s["snippet"], "topic": none_if_nan(s.get("topic")),
                          "attribution": "A reviewer reported"} for s in snippets],
            "note": "Random sample of reviews; separate from the overall rating above.",
        },
        "distance": {
            "miles": None if dist is None else round(dist, 1),
            "reference_point": ref.label if dist is not None else None,
            "measure": "approximate straight-line distance from the area center, not travel time" if dist is not None else None,
        },
        "availability": {
            "permanently_closed": none_if_nan(row["permanently_closed"]),
            "temporarily_closed": none_if_nan(temp),
            "hours_text": none_if_nan(row["hours_text"]) or "Hours not listed",
            "note": "No closure flag in the dataset does not confirm the place is open now.",
        },
        "contact": {
            "address": none_if_nan(row["address"]),
            "city": none_if_nan(row["city"]),
            "zipcode": none_if_nan(row["zipcode"]),
            "phone": none_if_nan(row["phone"]),
            "website": none_if_nan(row["website"]),
            "maps_url": none_if_nan(row.get("maps_url")),
        },
        "source": {"dataset": "Google Maps Places", "snapshot_date": None, "note": SOURCE_NOTE},
        "confirm_prompt": CONFIRM_PROMPT,
    }


def _overall_dist(row: pd.Series) -> dict[str, int] | None:
    vals = [none_if_nan(row.get(f"overall_stars_{s}")) for s in range(1, 6)]
    return None if any(v is None for v in vals) else {str(s): int(v) for s, v in zip(range(1, 6), vals)}


def _iso(v: Any) -> str | None:
    v = none_if_nan(v)
    return None if v is None else pd.Timestamp(v).date().isoformat()


def _sort(df: pd.DataFrame, group: str, sort: str, tol: float) -> pd.DataFrame:
    df = df.copy()
    df["_dist"] = df["distance_miles"].fillna(np.inf)
    df["_age_last"] = df["age_status"].eq("outside_published_age_criterion")
    if sort == "nearest" or group in ("verified_support", "limited_review_evidence", "temporarily_closed"):
        return df.sort_values(["_age_last", "_dist", "place_id"], kind="stable")
    # Scores within `tol` of each other are treated as tied, then distance breaks the tie.
    df["_score_bucket"] = -(df["ranking_score"].fillna(-np.inf) / tol).round()
    return df.sort_values(["_age_last", "_score_bucket", "_dist", "place_id"], kind="stable")


def rank_services(candidates: pd.DataFrame, refs: pd.DataFrame, *, need: str, location: str,
                  age: int | None = None, sort: str = "highly_rated") -> dict[str, Any]:
    cfg_all = load_config("services")
    cfg = cfg_all["ranking"]
    notes: list[str] = []
    ref = resolve_location(location, refs, candidates)

    assist, ordinary = families_for_need(need)
    fam_keys = set(assist + ordinary)
    relevant = candidates[candidates["families"].fillna("").map(lambda s: bool(fam_keys & set(s.split("|"))))].copy()
    # A place matched on a secondary family is shown under the family relevant to this need.
    fams = family_by_key()
    first_rel = relevant["families"].map(lambda s: next(k for k in s.split("|") if k in fam_keys))
    relevant["family"] = first_rel
    relevant["family_label"] = first_rel.map(lambda k: fams[k].label)
    relevant["assistance"] = first_rel.map(lambda k: fams[k].assistance)

    if ref.precision != "none":
        relevant["distance_miles"] = haversine_miles(ref.lat, ref.lon, relevant["lat"], relevant["lon"])
        in_area = relevant["distance_miles"] <= cfg["search_radius_miles"]
        area_desc = f"within {cfg['search_radius_miles']} miles (straight line) of the {ref.label}"
    else:
        relevant["distance_miles"] = np.nan
        if ref.zipcode:
            in_area = relevant["zipcode"].eq(ref.zipcode)
            area_desc = f"in ZIP {ref.zipcode}"
        else:
            in_area = relevant["city"].str.lower().eq((ref.city or "").lower())
            area_desc = f"in {ref.city}"
        notes.append("Your location could not be matched to an area center, so distances are not shown.")
    local = relevant[in_area].copy()

    perm_closed = int(local["permanently_closed"].eq(True).sum())
    local = local[~local["permanently_closed"].eq(True)]
    if perm_closed:
        notes.append(f"{perm_closed} place(s) marked permanently closed in the dataset were removed.")
    local["temporarily_closed"] = local["temporarily_closed"].map(lambda v: none_if_nan(v))
    local["group"] = local.apply(_assign_group, axis=1, cfg=cfg)
    local["age_status"] = [age_status(age, r)[0] for _, r in local.iterrows()]

    groups = []
    for g in GROUP_ORDER:
        part = local[local["group"] == g]
        if g == "verified_support" and part.empty and need in cfg_all["urgent_needs"]:
            notes.append("No providers for this need have been verified against official sources yet. "
                         "Unverified candidates are listed below; confirm eligibility directly.")
        if part.empty:
            continue
        part = _sort(part, g, sort, float(cfg["close_score_tolerance"]))
        shown = part.head(int(cfg["max_items_per_group"]))
        groups.append({
            "key": g, "label": GROUP_LABELS[g], "note": GROUP_NOTES.get(g),
            "total": int(len(part)),
            "items": [_card(r, age, ref, need) for _, r in shown.iterrows()],
        })

    n_high = int((local["group"] == "highly_rated").sum())
    covered = {c.lower() for c in cfg_all["target_area"]["cities"]}
    if ref.precision == "none" and (ref.city or "").lower() not in covered and local.empty:
        notes.append("Phoenix currently covers Oakland and nearby East Bay cities: "
                     + ", ".join(cfg_all["target_area"]["cities"]) + ". Try one of these cities or a ZIP code in them.")
    elif n_high < cfg["min_highly_rated_before_note"] and not local[local["assistance"]].empty:
        notes.append(
            f"Only {n_high} place(s) {area_desc} meet the highly rated threshold "
            f"(rating {cfg['highly_rated_min_rating']}+ with {cfg['highly_rated_min_reviews']}+ reviews). "
            "The threshold was not lowered; other nearby options are shown separately.")
    if local.empty:
        notes.append(f"No candidate services for this need were found {area_desc}.")

    return {
        "status": "ok" if len(local) else "no_results",
        "priority_need": need,
        "need_label": need_labels().get(need, need),
        "sort": sort,
        "reference_point": {"label": ref.label, "precision": ref.precision,
                            "lat": None if ref.lat is None else round(ref.lat, 3),
                            "lon": None if ref.lon is None else round(ref.lon, 3)},
        "search_area": area_desc,
        "families_considered": assist + ordinary,
        "ranking_settings": {
            "highly_rated_min_rating": cfg["highly_rated_min_rating"],
            "highly_rated_min_reviews": cfg["highly_rated_min_reviews"],
            "prior_weight_m": cfg["prior_weight_m"],
            "formula": "(n*r + m*C)/(n+m); C = mean overall rating of the service family",
            "tie_break": f"scores within {cfg['close_score_tolerance']} are tied; nearer first",
        },
        "groups": groups,
        "notes": notes,
    }

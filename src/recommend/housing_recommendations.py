"""Explainable area suggestions using rent, relevant service access, and optional pay scenarios."""

from __future__ import annotations

import math

from src.recommend.taxonomy import families_for_need, need_labels


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def recommend_housing(section: dict, request: dict, selection: dict | None = None) -> dict:
    if section.get("status") != "ok":
        return section
    selection = selection or {}
    need = request.get("priority_need", "housing")
    assistance, ordinary = families_for_need(need)
    relevant = set(assistance + ordinary)
    need_label = need_labels().get(need, "relevant support").lower()
    source_areas = section.get("areas", [])
    zips = [area for area in source_areas if area.get("area_type") == "zip"]
    candidates = zips or source_areas
    comparisons = {item["area_id"]: item for item in selection.get("housing_comparisons", [])}
    stage = selection.get("housing_income_stage", "not_selected")
    prepared = []
    for area in candidates:
        rent = _number(area.get("median_monthly_rent"))
        if area.get("suppressed") or area.get("usable_rental_records", 0) < 5 or rent is None or rent <= 0:
            continue
        rows = [row for row in area.get("nearby_services", []) if row.get("family") in relevant]
        measured = [row for row in rows if _number(row.get("share_of_properties_with_service")) is not None]
        best = max(measured, key=lambda row: (_number(row.get("share_of_properties_with_service")) or 0,
            _number(row.get("median_count_within_1_mile")) or 0), default=None)
        share = _number(best.get("share_of_properties_with_service")) if best else None
        count = _number(best.get("median_count_within_1_mile")) if best else None
        comparison = comparisons.get(area["area_id"], {})
        low = _number(comparison.get("rent_burden_minimum"))
        high = _number(comparison.get("rent_burden_maximum"))
        # This is the project's gross-pay comparison guide, not rental approval.
        income_tier = 0 if high is not None and high <= .30 else 1 if low is not None and low <= .30 else 2
        has_service = share is not None and share > 0
        prepared.append({"area": area, "rent": rent, "share": share, "count": count,
                         "best": best, "low": low, "high": high, "income_tier": income_tier,
                         "has_service": has_service})
    has_income = any(item["high"] is not None for item in prepared)
    prioritize_services = need not in {"work", "housing"}

    def key(item):
        service_key = (not item["has_service"], item["share"] is None, -(item["share"] or 0))
        if has_income and item["income_tier"] < 2:
            return (item["income_tier"], *service_key, item["rent"], item["area"]["area_id"])
        if has_income:
            return (2, item["rent"], *service_key, item["area"]["area_id"])
        if prioritize_services:
            return (item["income_tier"] if has_income else 0, not item["has_service"],
                    item["rent"], *service_key, item["area"]["area_id"])
        return (item["income_tier"] if has_income else 0, item["rent"], *service_key, item["area"]["area_id"])

    ranked = sorted(prepared, key=key)
    ranked_ids = {item["area"]["area_id"] for item in ranked}
    output = []
    for rank, item in enumerate(ranked, 1):
        reasons = [f"Typical snapshot rent: ${item['rent']:,.0f} per month, across the recorded home sizes."]
        if item["has_service"]:
            label = item["best"].get("family_label") or need_label
            reasons.append(f"{round(item['share'] * 100):g}% of sampled rentals with coordinates have a {label.lower()} place within one straight-line mile. Confirm services and eligibility.")
        elif item["share"] is None:
            reasons.append(f"Nearby {need_label} service access is unmeasured; it was not treated as zero.")
        else:
            reasons.append(f"No nearby {need_label} places were found in the measured sample; this does not establish that none exist.")
        if item["high"] is not None:
            label = "interim-job" if stage == "interim_job_scenario" else "target-job"
            reasons.append(f"Median rent is {item['high']:.0%} of the lower {label} gross-pay scenario. This is not current income or rental eligibility.")
        output.append({**item["area"], "recommendation": {"rank": rank, "recommended": rank <= 3,
            "reasons": reasons, "rent_burden_minimum": item["low"], "rent_burden_maximum": item["high"],
            "income_stage": stage if item["high"] is not None else "not_selected"}})
    output.extend({**area, "recommendation": None} for area in source_areas if area["area_id"] not in ranked_ids)
    note = (f"Areas with measured nearby {need_label} places come first, then lower median rent."
            if prioritize_services else "Lower median rent comes first; nearby services for your priority need break ties.")
    if has_income:
        note = "Areas within 30% of the lower selected-job gross-pay scenario come first, followed by ranges that could meet that guide at higher pay. Within those groups, relevant service access and rent determine order; remaining areas use lower rent first."
    else:
        note += " No usable income scenario was supplied; affordability is not assumed."
    return {**section, "areas": output, "ranking_note": note}

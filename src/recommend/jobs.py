"""Person 1 adapter: preserve the backend's grouped public job contract."""

from __future__ import annotations

from collections import OrderedDict

from src.common import normalize_location_input, parse_zip
from src.phoenix.integration import build_recommendations
from src.phoenix.ranking import rank_jobs as native_rank_jobs
from src.phoenix.qualifications import redact_contacts
from src.recommend import oakland_jobs
from src.recommend.person1_data import Person1DataUnavailable, load_indeed_jobs, load_person1, native_profile

TIER = {"strong_match":"strong_match", "possible_match":"possible_match", "qualification_gap":"known_gaps"}
LABELS = {"strong_match":"Strong matches", "possible_match":"Possible matches", "known_gaps":"Jobs to work toward"}


def _public(card, job, source: str) -> dict:
    hourly_min = card.comparable_pay_minimum if card.pay_basis == "USD/hour" else None
    hourly_max = None
    if card.pay_basis == "USD/hour" and job.pay.maximum is not None:
        hourly_max = job.pay.maximum if job.pay.period == "hour" else job.pay.maximum / (job.hours_per_week * job.weeks_per_year)
    requirements = []
    for r in card.requirements:
        requirements.append({"label":{"education":"education_required", "experience_years":"experience_required", "certification":"certification_required"}[r.field],
            "status":r.kind if r.kind in {"required", "preferred"} else "unknown", "value":r.value,
            "requirement_kind":r.kind, "evidence":r.evidence,
            "source":"model_prediction" if r.source.startswith("model") else "manual" if r.source == "manual" else "rule_extraction"})
    return {"job_id":card.job_id, "title":card.title, "description":redact_contacts(job.description) or None,
        "employer":card.company, "posted_date":card.posted_at,
        "url":card.source_url, "suitability_tier":TIER[card.fit_tier], "requirements":requirements,
        "matches":card.matched_skills, "gaps":card.qualification_gaps, "unknowns":card.unknowns,
        "pay":{"min":card.pay.minimum, "max":card.pay.maximum,
               "period":None if card.pay.period == "unknown" else card.pay.period, "currency":card.pay.currency,
               "raw_text":card.pay.raw, "hours_per_week":job.hours_per_week,
               "hours_basis":"stated" if job.hours_per_week is not None else "unknown",
               "hourly_equivalent_min":hourly_min, "hourly_equivalent_max":hourly_max,
               "needs_confirmation":card.pay.source == "ambiguous",
               "conversion_note":" ".join(dict.fromkeys(card.pay_assumptions + card.pay.notes)) or None},
        "location":{"text":card.location_text, "city":card.city,
                    "precision":"worksite" if card.location_precision == "worksite" else "city" if card.city else "unknown",
                    "source":card.worksite_location_source or "Indeed city text; precise worksite coordinates not supplied",
                    "distance_miles":card.approximate_distance_miles, "reference_point":card.distance_reference,
                    **job_map_location(job, source)},
        "rank_explanation":" ".join(card.ranking_explanation),
        "selectable":card.selectable, "is_selected":card.is_selected, "credential_summary":card.credential_summary,
        "matches_reported_role":card.matches_reported_role,
        "qualification_checks":[check.model_dump() for check in card.qualification_checks],
        "source":{"dataset":"Indeed provided export", "mode":source, "file":job.source_file,
                  "posting_status":card.availability, "pay_basis":card.pay_basis, "pay_source":card.pay.source}}


def job_map_location(job, source: str) -> dict:
    point = job.point
    if point and point.precision == "worksite":
        return {"latitude": point.latitude, "longitude": point.longitude, "map_precision": "worksite",
                "map_note": "Worksite coordinates supplied by the job data; confirm the posting."}
    if point is None or point.precision not in {"city_center", "zip_center"}:
        try:
            point = native_profile({"location": job.city, "priority_need": "work"}, source).reference_point if job.city else None
        except (OSError, ValueError, Person1DataUnavailable):
            point = None
    if point:
        return {"latitude": point.latitude, "longitude": point.longitude, "map_precision": "approximate_area",
                "map_note": f"Approximate job area: {job.city or job.location_text}. Exact worksite coordinates are unavailable."}
    return {"latitude": None, "longitude": None, "map_precision": "unavailable",
            "map_note": "This posting has no mappable worksite or area coordinates."}


def _profile_with_jobs(request: dict, source: str):
    try:
        jobs, rentals, _ = load_person1(source)
    except Person1DataUnavailable:
        if source != "real":
            raise
        jobs, _ = load_indeed_jobs()
        profile = native_profile(request, source)
        kind, key = normalize_location_input(profile.location)
        if kind == "zip" and not profile.search_cities:
            cities = {job.city for job in jobs if job.city and parse_zip(job.location_text) == key}
            if len(cities) == 1:
                profile = profile.model_copy(update={"search_cities": list(cities)})
        return profile, jobs, []
    return native_profile(request, source), jobs, rentals


def rank_jobs(request: dict, sort: str, *, source: str = "real", area_city: str | None = None) -> dict:
    try:
        profile, jobs, _ = _profile_with_jobs({**request, "job_sort": sort}, source)
    except Person1DataUnavailable as error:
        if source == "real":
            return oakland_jobs.rank_jobs(request, sort, area_city=area_city)
        return {"status":"not_integrated", "sort":sort, "groups":[], "notes":[str(error)]}
    cards = native_rank_jobs(jobs, profile, include_other_roles=True)
    by_id = {j.job_id:j for j in jobs}
    groups = OrderedDict()
    other_groups = OrderedDict()
    selected_id = request.get("selected_job_id")
    selected_ids = {key[4:] for key in (request.get("phoenix_session") or {}).get("selectedRecommendationIds", []) if key.startswith("job:")}
    for card in cards:
        card = card.model_copy(update={"is_selected":card.job_id == selected_id})
        tier = TIER[card.fit_tier]
        key = tier if sort == "nearest" else tier + ":" + card.pay_basis
        destination = other_groups if card.matches_reported_role is False else groups
        group = destination.setdefault(key, {"key":key, "label":LABELS[tier] + ("" if sort == "nearest" else " · " + card.pay_basis), "total":0, "items":[]})
        if (len(group["items"]) < oakland_jobs.LIMIT_PER_GROUP or card.job_id == selected_id or card.job_id in selected_ids
                or card.job_id in (request.get("qualification_answers") or {})):
            group["items"].append(_public(card, by_id[card.job_id], source))
        group["total"] += 1
    notes = ["Snapshot records: confirm current availability and all qualifications before applying.",
             "Pay is compared only within the same suitability and pay-period group; age does not rank jobs.",
             "Credentials may need preparation; every displayed job remains selectable."]
    if sort == "nearest" and cards and not any(c.approximate_distance_miles is not None for c in cards):
        notes.append("Precise worksite distances are unavailable; Nearest cannot distinguish city-only job locations.")
    if (request.get("education") or {}).get("level") == "graduate":
        notes.append("Graduate-level education does not specify an exact degree; degree-specific matches require confirmation.")
    return {"status":"ok" if cards else "no_results", "sort":sort, "groups":list(groups.values()),
            "other_groups":list(other_groups.values()), "notes":notes}


def selected_job_plan(request: dict, *, source: str = "real") -> dict:
    if request.get("selected_job_id") is None:
        return {}
    profile, jobs, rentals = _profile_with_jobs(request, source)
    result = build_recommendations(profile, jobs, rentals,
        data_mode="full" if source == "real" else "synthetic", selected_job_id=request["selected_job_id"],
        include_other_roles=True,
        selected_interim_job_id=request.get("selected_interim_job_id"),
        scenario_hours_per_week=request.get("scenario_hours_per_week"),
        scenario_weeks_per_year=request.get("scenario_weeks_per_year"))
    return {"selected_job_id":result.selected_job_id,
            "thirty_day_plan":result.thirty_day_plan.model_dump(mode="json"),
            "housing_comparisons":result.housing_comparisons,
            "housing_income_job_id":result.housing_income_job_id,
            "housing_income_stage":result.housing_income_stage}

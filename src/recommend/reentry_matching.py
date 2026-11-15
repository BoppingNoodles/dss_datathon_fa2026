"""Orchestrate existing recommendations; scores are explained heuristics, not ML."""
from __future__ import annotations

import math
import os
import pickle
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from src.common import ROOT
from src.recommend.reentry_domain import PhoenixSession, Recommendation, ReentryProfile
from src.recommend.reentry_planner import candidate_referrals
from src.recommend.reentry_resources import resource_types, BARRIER_TYPES, HOUSING
from src.recommend.services import resolve_location

JOB_WEIGHTS = {"qualification_fit": .40, "preference_fit": .25, "location_fit": .20, "wage_fit": .15}
MODEL_CUES = {"education_required": re.compile(r"\b(?:diploma|GED|degree|college|high school|education)\b", re.I),
              "experience_required": re.compile(r"\b(?:experience|experienced)\b", re.I),
              "certification_required": re.compile(r"\b(?:certificate|certification|certified|license|licensed|CDL|ServSafe|credential)\b", re.I)}
MODEL_NEGATIONS = {
    "education_required": re.compile(r"\bno (?:diploma|degree|formal education) (?:is )?(?:required|needed)\b", re.I),
    "experience_required": re.compile(r"\b(?:no (?:previous |prior |related |work )?experience (?:is )?(?:required|needed|necessary)|experience (?:is )?not (?:required|needed|necessary))\b", re.I),
    "certification_required": re.compile(r"\b(?:no (?:certificates?|certifications?|licenses?) (?:is |are )?(?:required|needed)|(?:certificates?|certifications?|licenses?) (?:is |are )?not required)\b", re.I),
}


@lru_cache(maxsize=2)
def _artifact(path: str, modified: int):
    # Only explicit, trusted local training artifacts; never load user uploads.
    import joblib
    return joblib.load(path)


@lru_cache(maxsize=512)
def _predict(path: str, modified: int, description: str):
    from src.data.train_indeed import predict
    return predict(_artifact(path, modified), description)


def model_flags(description: str) -> tuple[dict[str, bool], str | None]:
    configured = os.environ.get("PHOENIX_NLP_ARTIFACT")
    paths = [Path(configured)] if configured else [ROOT / "models/requirements_v1/tfidf.joblib"]
    path = next((p for p in paths if p.is_file()), None)
    if path is None:
        return {}, "Saved NLP weights are unavailable; existing extracted requirements are retained."
    try:
        flags = _predict(str(path), path.stat().st_mtime_ns, description)
        return flags, None
    except (ImportError, ValueError, OSError, EOFError, AttributeError, KeyError, TypeError, pickle.UnpicklingError) as error:
        return {}, f"NLP inference unavailable ({type(error).__name__}); existing requirement evidence is retained."


def _words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _job_recommendations(profile: ReentryProfile, jobs: dict, selected_ids=(), hidden_ids=()) -> tuple[list[Recommendation], list[str]]:
    cards = [c for g in jobs.get("groups", []) + jobs.get("other_groups", []) for c in g["items"]]
    interests = set().union(*(_words(v) for v in profile.employment.preferredJobTypes)) if profile.employment.preferredJobTypes else set()
    result, warnings = [], []
    for c in cards:
        checks = c.get("qualification_checks", [])
        required = [q for q in checks if q["requirement_kind"] == "required"]
        known = [q for q in required if q["status"] in {"reported_met", "gap"}]
        components = {"qualification_fit": sum(1. if q["status"] == "reported_met" else 0. if q["status"] == "gap" else .5 for q in required) / len(required) if required else None,
                      "preference_fit": min(1., len(interests & _words(c["title"])) / max(1, len(interests))) if interests else None,
                      "location_fit": None, "wage_fit": None}
        reasons, unknowns = [], list(c.get("unknowns", []))
        if components["preference_fit"]:
            reasons.append("The job title overlaps your selected work interests.")
        if len(known) < len(required):
            unknowns.append(f"{len(required) - len(known)} mandatory checks need confirmation; each uses neutral 0.5.")
        loc = c["location"]
        distance = loc.get("distance_miles")
        if distance is not None and math.isfinite(distance):
            scale = 5 if profile.barriers.hasTransportation is False else 20
            components["location_fit"] = max(0., 1 - distance / scale)
            reasons.append(f"About {distance:g} miles from the area reference point; not route time.")
        elif loc.get("city") and profile.location.city:
            components["location_fit"] = 1. if loc["city"].casefold() == profile.location.city.casefold() else .5
        if profile.barriers.hasTransportation is False:
            unknowns.append("Transport is limited: confirm the actual worksite, shift, route, and cost.")
        pay = c["pay"].get("hourly_equivalent_min")
        if pay is not None and math.isfinite(pay) and pay > 0:
            # Fixed log scale prevents an unrelated high-pay outlier from
            # erasing a meaningful pay increase between two nearby jobs.
            components["wage_fit"] = min(1., math.log1p(pay / 20) / math.log(9))
            reasons.append(f"Comparable stated pay starts at ${pay:g}/hour; confirm hours and conditions.")
        elif c["pay"].get("min") is not None:
            unknowns.append("Pay periods/hours are not comparable; no unstated hours were assumed for this score.")
        for key, value in components.items():
            if value is None:
                unknowns.append(f"{key.replace('_', ' ').capitalize()} is uncertain; neutral 0.5 used.")
        score = sum(JOB_WEIGHTS[k] * (.5 if v is None else v) for k, v in components.items())
        reasons += [f"Qualification/preference/location/wage weights: 40/25/20/15 (heuristic).",
                    f"{sum(q['status'] == 'reported_met' for q in required)} of {len(required)} listed mandatory checks reported met."]
        result.append(Recommendation(id=f"job:{c['job_id']}", category="job", mode="job", title=c["title"],
            description=(c.get("description") or "Check the original posting for details.")[:1200], source="Indeed snapshot",
            sourceUrl=c.get("url"), location={"city": loc.get("city") or ""}, score=round(score, 4),
            matchReasons=reasons, uncertainties=list(dict.fromkeys(unknowns + ["Confirm the vacancy and employer requirements; no reentry acceptance is verified."])),
            details={"jobId": c["job_id"], "components": components, "weights": JOB_WEIGHTS,
                     "qualificationChecks": deepcopy(checks), "requirements": deepcopy(c.get("requirements", [])), "pay": c["pay"],
                     "employer": c.get("employer"), "postedDate": c.get("posted_date"),
                     "wageScoreMethod": "Fixed logarithmic scale: log(1 + hourly_pay / 20) / log(9), capped at 1 ($160/hour). Heuristic, not a living-wage or income guarantee."},
            resourceType="job_posting", serviceEvidence={"job_posting": "Original Indeed posting; vacancy unconfirmed."}))
    result.sort(key=lambda r: (-r.score, r.id))
    # Run the saved classifier only on the five shortlisted postings. Positive
    # flags influence preparation, not claimed exact credentials/eligibility.
    descriptions = {f"job:{c['job_id']}": c.get("description") or "" for c in cards}
    shortlist = set([r.id for r in result if r.id not in hidden_ids][:5])
    for recommendation in [r for r in result if r.id in shortlist or r.id in selected_ids and r.id not in hidden_ids]:
        if not descriptions[recommendation.id].strip():
            recommendation.uncertainties.append("No source description is available for NLP inference.")
            continue
        flags, warning = model_flags(descriptions[recommendation.id])
        if warning:
            warnings.append(warning)
        for label, positive in flags.items():
            if (positive and MODEL_CUES[label].search(descriptions[recommendation.id])
                    and not MODEL_NEGATIONS[label].search(descriptions[recommendation.id])
                    and not any(r["label"] == label and r.get("status") in {"required", "preferred"} for r in recommendation.details["requirements"])):
                recommendation.details["requirements"].append({"label": label, "status": "unknown", "source": "model_prediction", "evidence": None, "requirement_kind": "uncertain"})
                recommendation.uncertainties.append(f"NLP flags {label.replace('_', ' ')}; confirm the exact requirement.")
        recommendation.details["modelPredictions"] = flags
    return result, list(dict.fromkeys(warnings))


def recommend_for_profile(profile: ReentryProfile, request: dict, jobs: dict, housing: dict,
                          services: dict, candidates, refs, *, source: str, today) -> tuple[list[Recommendation], list[str], list[str]]:
    selected_ids = (request.get("phoenix_session") or {}).get("selectedRecommendationIds", [])
    if request.get("selected_job_id"):
        selected_ids = [*selected_ids, f"job:{request['selected_job_id']}"]
    hidden_ids = [r["id"] for r in (request.get("phoenix_session") or {}).get("recommendations", [])
                  if r["userStatus"] in {"dismissed", "rejected"} or r.get("userReportedAvailability") == "unavailable"]
    result, warnings = _job_recommendations(profile, jobs, selected_ids, hidden_ids)
    city = resolve_location(request["location"], refs, candidates).city if not candidates.empty else profile.location.city
    top_jobs = [r.id for r in result if r.id not in hidden_ids][:5]
    for area in housing.get("areas", []):
        rec = area.get("recommendation") or {}
        result.append(Recommendation(id=f"area:{area['area_id']}", category="housing", mode="long_term_area", title=area["label"],
            description="Area-level rental cost comparison; not an available home or landlord approval.", source="Zillow area summary",
            location={"city": profile.location.city}, score=1 / max(1, rec.get("rank", 10)),
            matchReasons=rec.get("reasons", []) + ([f"Your stated monthly budget is ${profile.housing.monthlyBudget:g}; confirm all costs."] if profile.housing.monthlyBudget is not None else []),
            uncertainties=["Rent snapshots may be outdated; hypothetical pay is not current income.", "Individual rental listings and approval are not verified."],
            resourceType="rental_market", serviceEvidence={"rental_market": "Zillow area summary, not a temporary-housing provider or available rental."},
            details={"areaId": area["area_id"], "medianMonthlyRent": area.get("median_monthly_rent"), "rentP25": area.get("rent_p25"), "rentP75": area.get("rent_p75"), "rentBasis": area.get("rent_basis")}))
    barriers = set()
    from src.recommend.reentry_finances import assess_finances
    budget = assess_finances(profile.finances)
    if budget["housingHigh"]:
        barriers.add("housing")
    if profile.barriers.hasFoodAccess is False or (budget["status"] in {"deficit", "tight"} and (profile.finances.monthlyFoodCost or 0) > 0):
        barriers.add("food")
    if profile.housing.status != "stable" or "housing" in profile.supportNeeds:
        barriers.add("housing")
    if profile.barriers.hasGovernmentId is not True:
        barriers.add("identification")
    if profile.barriers.hasTransportation is not True:
        barriers.add("transportation")
    if profile.barriers.hasPhoneAccess is not True and profile.barriers.hasInternetAccess is not True:
        barriers.add("communication")
    barriers.update({"employment": "employment", "education": "qualifications", "healthcare": "health_care"}.get(n, n) for n in profile.supportNeeds)
    for barrier in sorted(barriers):
        for referral in candidate_referrals(barrier, request, candidates, refs, source=source, today=today):
            verified = referral.verification == "verified_reentry_scope" or (
                referral.resource_id.startswith("manual:") and referral.verification == "verified_general_service")
            types = [t for t in referral.resource_types if (t in HOUSING) == (barrier == "housing")]
            primary = next((t for t in BARRIER_TYPES.get(barrier, []) if t in types), types[0] if types else "community_support")
            result.append(Recommendation(id=f"provider:{referral.resource_id}" if barrier == "housing" else f"service:{referral.resource_id}",
                category="housing" if barrier == "housing" else "service", mode="temporary_housing" if barrier == "housing" else "service",
                title=referral.name, description=referral.scope, source="Official scope check" if verified else "Google Places category candidate",
                sourceUrl=referral.url, location={"city": referral.city or ""}, score=.9 if verified else .5,
                resourceType=primary, supportedResourceTypes=types,
                serviceEvidence={t: referral.category_evidence or referral.scope for t in types},
                verificationStatus="verified" if verified else "partially_verified" if referral.verification == "verified_general_service" else "unverified",
                matchReasons=[f"An option for checking {barrier.replace('_', ' ')} support.", "Organization scope checked; capacity is unknown." if verified else "Category match; specific assistance needs confirmation."],
                uncertainties=[referral.confirmation, "Confirm intake and bed availability before relying on housing support." if barrier == "housing" else "Confirm current services and eligibility before relying on this option."],
                details={"resourceId": referral.resource_id, "barrier": barrier, "barriers": [barrier], "scope": referral.scope,
                         "category": referral.category_evidence, "requestedCity": city, "serviceAreaCities": referral.service_area_cities,
                         "distanceMiles": referral.distance_miles, "contact": {"phone": referral.phone, "address": referral.address, "website": referral.url},
                         "transitKind": "station" if "station" in (referral.category_evidence or "").lower() else "stop" if "bus stop" in (referral.category_evidence or "").lower() else None,
                         "officialSource": referral.source_url, "checkedOn": referral.checked_on.isoformat() if referral.checked_on else None}))
    # Preserve original service cards, including their existing review ranker.
    ids = [c["place_id"] for g in services.get("groups", []) for c in g["items"]]
    raw_cards = {str(r["place_id"]): r for r in candidates.loc[candidates["place_id"].isin(ids)].to_dict("records")} if not candidates.empty else {}
    for group in services.get("groups", []):
        if group["key"] == "temporarily_closed":
            continue
        for card in group["items"]:
            if card["eligibility"]["age_status"] == "outside_published_age_criterion":
                continue
            raw = raw_cards.get(card["place_id"], {})
            category = " ".join(str(raw.get(k, "")) for k in ["category", "categories"] if raw.get(k) is not None)
            types = resource_types(category)
            result.append(Recommendation(id=f"service:{card['place_id']}", category="service", mode="service", title=card["name"],
                description=card["family_label"], source="Google Places / Reviews snapshot", sourceUrl=card["verification"]["official_url"] or card["contact"]["website"] or card["contact"]["maps_url"],
                location={"city": card["contact"]["city"] or ""}, score=max(0., min(1., (card["rating"]["ranking_score"] or 0) / 5)),
                matchReasons=[f"Matches the currently displayed {services['need_label']} resource category."],
                uncertainties=[card["confirm_prompt"], "Reviews do not verify eligibility or availability."],
                verificationStatus="partially_verified" if card["verification"]["status"].startswith("verified_") else "unverified",
                resourceType=types[0], supportedResourceTypes=types, serviceEvidence={t: f"Google Places category: {category}; specific service unconfirmed." for t in types},
                details={"resourceId": card["place_id"], "family": card["family"], "need": card["need"], "category": category,
                         "requestedCity": city, "distanceMiles": card["distance"]["miles"], "contact": card["contact"],
                         "transitKind": "station" if "station" in category.lower() else "stop" if "bus stop" in category.lower() else None}))
    unique = {}
    for resource in result:
        if resource.id not in unique:
            unique[resource.id] = resource
        else:
            first = unique[resource.id]
            first.supportedResourceTypes = list(dict.fromkeys(first.supportedResourceTypes + resource.supportedResourceTypes))
            first.serviceEvidence = {**resource.serviceEvidence, **first.serviceEvidence}
            first.details["barriers"] = list(dict.fromkeys(first.details.get("barriers", []) + resource.details.get("barriers", [])))
    return list(unique.values()), top_jobs, warnings


def preserve_resource_state(current: list[Recommendation], previous: PhoenixSession | None) -> list[Recommendation]:
    if previous is None:
        return current
    old = {r.id: r for r in previous.recommendations}
    for r in current:
        if r.id in old:
            r.userStatus = old[r.id].userStatus
            r.userReportedAvailability = old[r.id].userReportedAvailability
    present = {r.id for r in current}
    for r in previous.recommendations:
        if r.id not in present:
            historical = r.model_copy(deep=True)
            historical.active = False
            historical.verificationStatus, historical.availabilityStatus = "unverified", "unknown"
            historical.uncertainties = ["Historical saved item; not confirmed in the current source results."]
            current.append(historical)
    return current

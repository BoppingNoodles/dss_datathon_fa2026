"""Source-grounded resource types and task joins; no geography-only referrals."""
from __future__ import annotations

import re

from src.recommend.reentry_domain import Recommendation, ReentryProfile

TRANSPORT = ["transportation_assistance", "public_transit"]
HOUSING = ["transitional_housing", "housing_assistance"]
BARRIER_TYPES = {"housing": HOUSING, "transportation": TRANSPORT, "identification": ["identification_assistance"],
                 "qualifications": ["workforce_training"], "employment": ["workforce_training"], "documents": ["workforce_training"],
                 "food": ["food_assistance"], "health_care": ["healthcare"], "communication": ["community_support"], "community_support": ["community_support"]}


def resource_types(category: str, *, official_types=()) -> list[str]:
    """Use explicit source categories or reviewed scope, never desired need alone."""
    if official_types:
        return list(official_types)
    text = category.casefold().replace("_", " ")
    patterns = {
        "transitional_housing": r"homeless shelter|transitional housing|halfway house|(?<!animal )\bshelter\b",
        "housing_assistance": r"housing authority|housing assistance|supportive housing|housing association|homeless service",
        "public_transit": r"bus (?:stop|station)|transit (?:station|depot)|train station|ferry terminal|subway station|light rail",
        "transportation_assistance": r"paratransit|transportation assistance|mobility assistance|community shuttle",
        "identification_assistance": r"department of motor vehicles|driver.?s? licen[sc]e office|identification (?:office|assistance)|vital records",
        "workforce_training": r"vocational|adult education|training (?:cent(?:er|re)|school)|technical school|workforce development|job training|career cent(?:er|re)",
        "food_assistance": r"food bank|food pantry|soup kitchen|meal assistance|food assistance",
        "healthcare": r"medical clinic|community health|health cent(?:er|re)|mental health|hospital|medical cent(?:er|re)|dental clinic|rehabilitation cent(?:er|re)",
    }
    return [key for key, pattern in patterns.items() if re.search(pattern, text)] or ["community_support"]


def task_types(task) -> list[str]:
    key = task.id
    if key.startswith("finances:housing:"):
        return ["housing_assistance", "transitional_housing", "rental_market"]
    if key.startswith("finances:food:"):
        return ["food_assistance"]
    if key.startswith("finances:income:"):
        return ["job_posting"]
    if key.startswith(("reentry:housing-long-term", "area-review:")):
        return ["rental_market"]
    if task.category == "housing":
        return HOUSING
    if task.category == "transportation":
        return TRANSPORT
    if key.startswith(("training:", "reentry:job-preparation:", "support:education")):
        return ["workforce_training"]
    if key.startswith(("reentry:job-", "reentry:model-check:", "reentry:qualification:", "employment:restart:")):
        return ["job_posting"]
    if key.startswith(("reentry:identification", "reentry:confirm-identification", "support:identification")):
        return ["identification_assistance"]
    if task.category == "healthcare":
        return ["healthcare"]
    if key in {"support:food", "reentry:priority-food"}:
        return ["food_assistance"]
    if key.startswith(("reentry:work-documents", "reentry:work-goal")):
        return []
    if task.category == "community_support":
        return ["community_support"]
    return []


def _city(text):
    return (text or "").casefold().split(",")[0].strip()


def geographic_fit(profile: ReentryProfile, resource: Recommendation) -> tuple[bool, str, int]:
    target = _city(resource.details.get("requestedCity") or profile.location.city)
    city = _city(resource.location.get("city"))
    service_area = {_city(c) for c in resource.details.get("serviceAreaCities", [])}
    if target and service_area and target not in service_area:
        return False, "Outside the documented service area.", 3
    if target and target in service_area:
        return True, "Your community is in its documented service area.", 0
    if target and city == target:
        return True, "Listed in your community; confirm the actual location and access.", 0
    miles = resource.details.get("distanceMiles")
    if isinstance(miles, (float, int)):
        if miles > (15 if profile.barriers.hasTransportation is False else 40):
            return False, "Outside the current local search range.", 3
        return True, f"About {miles:g} straight-line miles from the area reference; route unconfirmed.", 1
    return True, "Service area or travel distance is unconfirmed.", 2


def _training_fits(task, resource, profile):
    # Exclude a clearly different specialty; general workforce navigation can
    # remain a candidate, with its exact course/accepted credential unconfirmed.
    domains = [r"phlebotom", r"\bcpr\b|\bbls\b|\bacls\b|first aid", r"\bcna\b|nursing assistant", r"registered nurs|nursing school",
               r"forklift|warehouse|osha", r"\bcdl\b|commercial driv|truck driv", r"servsafe|food handler", r"\bged\b|high school|diploma"]
    context = " ".join([task.title, task.description, task.rationale]).casefold()
    if not any(re.search(pattern, context) for pattern in domains):
        context += " " + " ".join(l.get("label", "") for l in task.referenceLinks).casefold()
        if not task.referenceLinks:
            context += " " + " ".join(profile.employment.preferredJobTypes).casefold()
    source = " ".join([resource.title, resource.description, str(resource.details.get("category", ""))]).casefold()
    wanted = {i for i, pattern in enumerate(domains) if re.search(pattern, context)}
    offered = {i for i, pattern in enumerate(domains) if re.search(pattern, source)}
    return not offered or bool(wanted & offered)


def attach_resources(task, profile: ReentryProfile, resources: list[Recommendation], *, candidate_ids=None):
    allowed = set(task.allowedResourceTypes)
    ids = set(candidate_ids) if candidate_ids is not None else None
    matches = []
    for resource in resources:
        compatible = allowed & set(resource.supportedResourceTypes)
        if (not compatible or (ids is not None and resource.id not in ids) or not resource.active
                or resource.userStatus in {"dismissed", "rejected"} or resource.userReportedAvailability == "unavailable"):
            continue
        if resource.details.get("geographicReferenceOnly"):
            continue
        relevant, geography, geo_rank = geographic_fit(profile, resource)
        if not relevant or "workforce_training" in compatible and not _training_fits(task, resource, profile):
            continue
        kind = sorted(compatible)[0]
        evidence = resource.serviceEvidence.get(kind)
        # Typed Indeed/Zillow inputs are direct dataset evidence. For services,
        # the caller must preserve a source category or checked official scope.
        if not evidence and kind not in {"job_posting", "rental_market"}:
            continue
        evidence = evidence or ("Original job posting." if kind == "job_posting" else "Zillow area-level rental summary.")
        scope = "Source scope checked; personal eligibility and capacity still need confirmation." if resource.verificationStatus == "verified" else "Category candidate; confirm it offers this specific assistance."
        selected = resource.userStatus in {"selected", "contacted", "applied", "accepted"}
        rank = (0 if selected else 1, geo_rank, 0 if resource.verificationStatus == "verified" else 1,
                1 if resource.details.get("transitKind") == "stop" else 0, -resource.score, resource.id)
        matches.append((rank, resource, f"{'You selected this option. ' if selected else ''}{evidence} {geography} {scope}"))
    matches.sort(key=lambda row: row[0])
    distinct, seen = [], set()
    for row in matches:
        key = (row[1].title.casefold(), row[1].location.get("city", "").casefold(), tuple(sorted(set(row[1].supportedResourceTypes) & allowed)))
        if key not in seen:
            distinct.append(row)
            seen.add(key)
    task.relatedRecommendationIds = [r.id for _, r, _ in distinct[:3]]
    task.resourceMatchReasons = {r.id: why for _, r, why in distinct[:3]}
    task.resourceEmptyState = None if matches else "No compatible local resource is verified in the current data. Use the source information or ask a known support contact for a referral; confirm assistance before traveling or paying."
    if not allowed:
        task.resourceEmptyState = "This step uses your own information; no external resource is required."
    return task

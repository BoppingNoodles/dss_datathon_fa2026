"""Deterministic, explainable policy; this is not a trained hiring-success model."""

from __future__ import annotations

import re

from .credentials import credential_reported_held, credential_summary, with_credential_evidence
from .models import Job, JobCard, UserProfile
from .normalization import city_key, haversine_miles, request_cities
from .pay import comparable_pay

TIERS = {"strong_match": 0, "possible_match": 1, "qualification_gap": 2}
BASES = {"USD/hour": 0, "USD/year": 1, "USD/month": 2, "USD/week": 3, "USD/day": 4,
         "pay_needs_confirmation": 5}
LEVELS = {"none": 0, "high_school": 1, "some_college": 2, "associate": 3, "bachelor": 4, "master": 5, "doctorate": 6}
SKILL_FAMILIES = {
    "warehouse": ["warehouse", "forklift", "logistics", "inventory", "shipping", "receiving", "fulfillment", "stockroom", "stock clerk", "package handler", "material handler", "order picker"],
    "customer service": ["customer service", "customer support", "call center", "retail", "cashier", "sales associate"],
    "food service": ["food service", "restaurant", "cook", "kitchen", "barista", "dishwasher", "food preparation"],
    "construction": ["construction", "carpentry", "carpenter", "laborer", "labourer"],
    "cleaning": ["cleaning", "janitor", "janitorial", "custodian", "housekeeping"],
    "driving": ["delivery driver", "truck driver", "driving", "courier"],
    "administration": ["administrative", "administration", "data entry", "receptionist", "office assistant"],
}


def _contains(text: str, term: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", text.casefold()) is not None


def _skill_matches(job: Job, profile: UserProfile, active_families: list[tuple[str, list[str]]]) -> tuple[list[str], bool]:
    title = job.title.casefold()
    direct = [s.strip() for s in profile.experience.skills if len(s.strip()) >= 3]
    title_match = (any(_contains(title, term) for _, terms in active_families for term in terms)
                   or any(_contains(title, skill) for skill in direct))
    if not title_match:
        return [], False
    body = job.description.casefold()
    matches: set[str] = set()
    for family, terms in active_families:
        if any(_contains(title + " " + body, term) for term in terms):
            matches.add(family)
    for skill in direct:
        if _contains(title + " " + body, skill):
            matches.add(skill.casefold())
    return sorted(matches), title_match


def _qualifications(job: Job, profile: UserProfile) -> tuple[list[str], list[str]]:
    gaps, unknown = [], []
    for req in job.requirements:
        if req.kind != "required":
            if req.kind in {"alternative", "uncertain"}:
                unknown.append(f"Confirm alternative/uncertain requirement: {req.evidence}")
            continue
        if req.field == "education":
            required = LEVELS.get(str(req.value))
            actual = LEVELS.get(profile.education.level)
            if required is None or actual is None:
                unknown.append("Education requirement match needs confirmation.")
            elif actual < required:
                gaps.append(f"Posting requires {req.value}; stated education is {profile.education.level}.")
        elif req.field == "experience_years":
            try:
                needed = float(req.value)
            except (TypeError, ValueError):
                unknown.append("Required experience amount needs confirmation.")
                continue
            if profile.experience.years is None:
                unknown.append("Years of relevant experience are not confirmed.")
            elif profile.experience.years < needed:
                gaps.append(f"Posting requires {needed:g} years of relevant experience; {profile.experience.years:g} stated.")
            else:
                unknown.append("Confirm that stated experience covers the specific work required.")
        elif req.field == "certification":
            if not credential_reported_held(str(req.value), profile):
                unknown.append(f"Required credential not confirmed: {req.value}.")
    if not job.requirements or all(r.source.startswith(("posting_credential_hints_", "operator_role_check:")) for r in job.requirements):
        unknown.append("Structured requirements not supplied; confirm qualifications in the original posting.")
    return gaps, sorted(set(unknown))


def _distance(job: Job, profile: UserProfile) -> float | None:
    if not job.point or job.point.precision != "worksite" or not profile.reference_point:
        return None
    ref = profile.reference_point
    return haversine_miles(ref.latitude, ref.longitude, job.point.latitude, job.point.longitude)


def rank_jobs(jobs: list[Job], profile: UserProfile, *, include_expired: bool = False) -> list[JobCard]:
    cities = request_cities(profile.location, profile.search_cities)
    if not cities:
        return []  # An unresolved ZIP must not turn into a nationwide search.
    cards: list[JobCard] = []
    user = " ".join(profile.experience.skills + [profile.experience.text]).casefold()
    active_families = [(family, terms) for family, terms in SKILL_FAMILIES.items()
                       if any(_contains(user, term) for term in terms)]
    for job in jobs:
        if job.is_expired is True and not include_expired:
            continue
        if city_key(job.city) not in cities:
            continue
        distance = _distance(job, profile)
        if distance is not None and profile.max_distance_miles is not None and distance > profile.max_distance_miles:
            continue
        matches, title_match = _skill_matches(job, profile, active_families)
        if (profile.experience.skills or profile.experience.text.strip()) and not title_match:
            # Description-only terms (e.g. a software role mentioning warehouse clients)
            # must not let unrelated high salaries dominate the main recommendations.
            # This conservative role-title baseline can be replaced by a reviewed matcher.
            continue
        job = with_credential_evidence(job)
        gaps, unknown = _qualifications(job, profile)
        tier = "qualification_gap" if gaps else "strong_match" if title_match and not unknown else "possible_match"
        if not matches:
            unknown.append("Work/skill relevance needs confirmation.")
        if distance is None:
            unknown.append("Exact worksite distance is unknown; city compatibility only.")
        if job.is_expired is None:
            unknown.append("Posting availability is unknown.")
        basis, pay_min, assumptions = comparable_pay(job)
        why = [f"Suitability group: {tier.replace('_', ' ')}; this is not a hiring or eligibility guarantee."]
        if matches:
            why.append("Experience terms overlap: " + ", ".join(matches) + ".")
        if pay_min is not None:
            why.append(f"Lower advertised pay endpoint: {pay_min:g} {basis}; pay compared only within this basis.")
        else:
            why.append("Pay not listed or needs confirmation; no zero-pay assumption.")
        why.append("Nearest sort within suitability groups." if profile.sort == "nearest" else "Comparable pay first within suitability groups; verified distance breaks pay ties.")
        cards.append(JobCard(job_id=job.job_id, title=job.title, company=job.company, city=job.city,
            location_text=job.location_text, source_url=job.source_url, posted_at=job.posted_at,
            availability="expired_snapshot" if job.is_expired is True else "not_marked_expired_in_snapshot" if job.is_expired is False else "unknown",
            pay=job.pay, fit_tier=tier, matched_skills=matches, qualification_gaps=gaps,
            unknowns=sorted(set(unknown)), requirements=job.requirements,
            pay_basis=basis, comparable_pay_minimum=pay_min, pay_assumptions=assumptions,
            approximate_distance_miles=None if distance is None else round(distance, 3),
            distance_reference=profile.reference_point.label if distance is not None else None,
            location_precision=job.point.precision if job.point else "city_only" if job.city else "unknown",
            worksite_location_source=job.point.source if job.point else None,
            credential_summary=credential_summary(job.requirements, profile),
            ranking_explanation=why))

    def key(card: JobCard) -> tuple:
        distance = card.approximate_distance_miles
        pay_key = (BASES.get(card.pay_basis, 99), -(card.comparable_pay_minimum or 0))
        distance_key = (distance is None, distance if distance is not None else 0)
        if profile.sort == "nearest":
            return (TIERS[card.fit_tier], *distance_key, *pay_key, card.job_id)
        return (TIERS[card.fit_tier], *pay_key, *distance_key, card.job_id)

    return sorted(cards, key=key)

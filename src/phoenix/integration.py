"""Person 1's API-independent response builder; no frontend/backend framework needed."""

from __future__ import annotations

from .housing import compare_job_housing, summarize_housing
from .models import Job, RecommendationResponse, Rental, ServiceLocation, UserProfile
from .normalization import city_key, request_cities
from .ranking import BASES, TIERS, rank_jobs
from .spatial import attach_service_access
from .planning import build_thirty_day_plan


def build_recommendations(profile: UserProfile, jobs: list[Job], rentals: list[Rental], *,
                          data_mode: str, services: list[dict] | None = None,
                          service_locations: list[ServiceLocation] | None = None,
                          selected_job_id: str | None = None,
                          selected_interim_job_id: str | None = None,
                          scenario_hours_per_week: float | None = None,
                          scenario_weeks_per_year: float | None = None,
                          include_expired: bool = False) -> RecommendationResponse:
    cities = request_cities(profile.location, profile.search_cities)
    # Resolve a ZIP only when the input data maps it unambiguously to a city.
    if not cities and profile.location.strip().isdigit() and len(profile.location.strip()) == 5:
        cities = {city_key(r.city) for r in rentals if r.zipcode == profile.location.strip()}
        if len(cities) == 1:
            profile = profile.model_copy(update={"search_cities": sorted(cities)})
        else:
            cities = set()
    cards = rank_jobs(jobs, profile, include_expired=include_expired)
    if cities:
        areas, housing_status = summarize_housing(rentals, cities=cities)
    else:
        areas, housing_status = [], {"status": "location_needs_resolution", "public_areas": 0}
    if service_locations is not None:
        areas = attach_service_access(areas, rentals, service_locations)
    comparisons = []
    plan = None
    income_job_id = None
    income_stage = "not_selected"
    if selected_interim_job_id is not None and selected_job_id is None:
        raise ValueError("Select a target job before selecting interim work")
    if selected_job_id is not None:
        selected_card = next((c for c in cards if c.job_id == selected_job_id), None)
        selected = next((j for j in jobs if j.job_id == selected_job_id), None)
        if selected is None or selected_card is None:
            raise ValueError("Selected job is not in this profile's recommendation results")
        selected = selected.model_copy(update={"requirements":selected_card.requirements})
        plan = build_thirty_day_plan(profile, selected, cards, selected_interim_job_id=selected_interim_job_id)
        cards = [c.model_copy(update={"is_selected":c.job_id == selected_job_id}) for c in cards]
        income_job_id = selected_interim_job_id or selected_job_id
        income_stage = "interim_job_scenario" if selected_interim_job_id else "target_job_scenario"
        income_job = next(j for j in jobs if j.job_id == income_job_id)
        comparisons = [compare_job_housing(income_job, area, scenario_hours_per_week=scenario_hours_per_week,
                        scenario_weeks_per_year=scenario_weeks_per_year) for area in areas]
    groups = sorted({(c.fit_tier, c.pay_basis) for c in cards}, key=lambda g: (TIERS[g[0]], BASES.get(g[1], 99)))
    group_order = sorted({c.fit_tier for c in cards}, key=TIERS.get) if profile.sort == "nearest" else ["/".join(g) for g in groups]
    notes = ["Data mode: " + data_mode + ".", "Different pay-period groups are not an overall pay comparison."]
    if not cities:
        notes.append("Location could not be resolved; no broad-area fallback was applied.")
    if profile.age is not None:
        notes.append("Age is not used in job or housing ranking.")
    return RecommendationResponse(data_mode=data_mode, jobs=cards, housing_areas=areas,
        job_group_order=group_order, services=services or [],
        service_status="provided" if services is not None else "not_connected",
        selected_job_id=selected_job_id, thirty_day_plan=plan,
        housing_income_job_id=income_job_id, housing_income_stage=income_stage,
        housing_comparisons=comparisons, data_coverage={"input_jobs": len(jobs), "input_rentals": len(rentals),
            "result_jobs": len(cards), "housing": housing_status, "notes": notes},
        next_steps=["Follow the selected job's preparation plan; confirm requirements before paying for training.",
                    "Review interim work and its offered schedule while pursuing the target credential."] if plan else
                   ["Select any displayed job, including one with a qualification gap, to build its 30-day preparation plan.",
                    "Confirm requirements and current availability in the original posting."])

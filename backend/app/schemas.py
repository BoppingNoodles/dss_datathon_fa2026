"""Shared request/response contract (Phoenix.md section 10).

Persons 1 and 3 build against these models and backend/fixtures/*.json. Freeze after first
integration; change only with a note in docs/api_contract.md.

Every value that can be unknown is nullable. Unknown is never encoded as 0.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from src.phoenix.models import QualificationCheck, ThirtyDayPlan
from src.recommend.reentry_models import ReentryPlan, ReentrySituation
from src.recommend.reentry_domain import ReentryProfile, PhoenixSession, UserEvent, profile_request

Need = Literal["work", "housing", "food", "health_care", "transportation", "community_support"]
EducationLevel = Literal[
    "no_diploma", "high_school_or_ged", "some_college", "associate", "bachelor", "graduate", "not_sure",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----------------------------------------------------------------------------- request


class Experience(Strict):
    skills: list[str] = Field(default_factory=list, description="Selected skill / work areas")
    text: str | None = Field(None, max_length=1000, description="Optional short description")
    years: float | None = Field(None, ge=0, le=60)
    no_experience_yet: bool = False


class Education(Strict):
    level: EducationLevel | None = None
    credentials: list[str] = Field(default_factory=list, description="Certificates / licenses")
    no_credentials: bool = False

    @model_validator(mode="after")
    def consistent_credentials(self):
        if self.no_credentials and self.credentials:
            raise ValueError("Choose certificates or none, not both")
        return self


class RecommendationRequest(Strict):
    """The five onboarding inputs. Only location and priority_need are required."""

    age: int | None = Field(None, ge=14, le=110, description="Skip allowed. Used only for verified service age criteria.")
    location: str = Field(..., min_length=2, max_length=80, description="City or ZIP")
    priority_need: Need
    experience: Experience = Field(default_factory=Experience)
    education: Education = Field(default_factory=Education)
    service_sort: Literal["highly_rated", "nearest"] = "highly_rated"
    service_need: Need | None = None
    job_sort: Literal["highest_pay", "nearest"] = "highest_pay"
    selected_job_id: str | None = Field(None, min_length=1)
    qualification_answers: dict[str, dict[str, StrictBool]] = Field(default_factory=dict, max_length=100)
    selected_interim_job_id: str | None = Field(None, min_length=1)
    scenario_hours_per_week: float | None = Field(None, gt=0, le=80)
    scenario_weeks_per_year: float | None = Field(None, gt=0, le=53)
    reentry: ReentrySituation | None = None
    reentry_completed_ids: list[str] = Field(default_factory=list, max_length=200)
    reentry_start_date: date | None = None
    profile: ReentryProfile | None = None
    phoenix_session: PhoenixSession | None = None
    user_event: UserEvent | None = None

    @model_validator(mode="before")
    @classmethod
    def adapt_profile(cls, value):
        if isinstance(value, dict):
            profile = value.get("profile")
            state = value.get("phoenix_session")
            if not profile and state:
                profile = state.profile if isinstance(state, PhoenixSession) else state.get("profile")
            if profile:
                parsed = ReentryProfile.model_validate(profile)
                value = {**value, **profile_request(parsed), "profile": parsed}
        return value

    @model_validator(mode="after")
    def interim_requires_target(self):
        if self.selected_interim_job_id and not self.selected_job_id:
            raise ValueError("Select a target job before selecting interim work")
        if self.profile and self.phoenix_session and self.profile.profileId != self.phoenix_session.profile.profileId:
            raise ValueError("Session and profile IDs differ")
        return self


# ----------------------------------------------------------------------------- jobs (Person 1/2 fill)


class RequirementEvidence(Strict):
    label: Literal["education_required", "experience_required", "certification_required"]
    status: Literal["required", "preferred", "not_found", "unknown"]
    evidence: str | None = None
    source: Literal["model_prediction", "rule_extraction", "manual"] | None = None
    model_score: float | None = None
    value: str | float | None = None
    requirement_kind: Literal["required", "preferred", "alternative", "uncertain"] | None = None


class Pay(Strict):
    min: float | None = None
    max: float | None = None
    period: Literal["hour", "day", "week", "month", "year"] | None = None
    currency: str | None = "USD"
    raw_text: str | None = None
    hours_per_week: float | None = None
    hours_basis: Literal["stated", "assumed_40", "unknown"] = "unknown"
    hourly_equivalent_min: float | None = None
    hourly_equivalent_max: float | None = None
    conversion_note: str | None = None
    needs_confirmation: bool = False


class JobLocation(Strict):
    text: str | None = None
    city: str | None = None
    precision: Literal["worksite", "city", "unknown"] = "unknown"
    source: str | None = None
    distance_miles: float | None = None
    reference_point: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    map_precision: Literal["worksite", "approximate_area", "unavailable"] = "unavailable"
    map_note: str | None = None


class JobCard(Strict):
    job_id: str
    title: str
    description: str | None = None
    employer: str | None = None
    posted_date: str | None = None
    url: str | None = None
    suitability_tier: Literal["strong_match", "possible_match", "known_gaps"]
    requirements: list[RequirementEvidence] = Field(default_factory=list)
    matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    pay: Pay
    location: JobLocation
    rank_explanation: str
    source: dict = Field(default_factory=dict)
    selectable: bool = True
    is_selected: bool = False
    credential_summary: str | None = None
    matches_reported_role: bool | None = None
    qualification_checks: list[QualificationCheck] = Field(default_factory=list)


class JobGroup(Strict):
    key: str
    label: str
    total: int
    items: list[JobCard]


class JobsSection(Strict):
    status: Literal["ok", "no_results", "not_integrated"]
    sort: Literal["highest_pay", "nearest"]
    groups: list[JobGroup] = Field(default_factory=list)
    other_groups: list[JobGroup] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------------- housing (aggregates only)


class NearbyServiceSummary(Strict):
    family: str
    family_label: str
    count_within_1_mile: int | None = None
    nearest_miles: float | None = None
    median_count_within_1_mile: float | None = None
    share_of_properties_with_service: float | None = None
    properties_with_coordinates: int | None = None
    measurement: str | None = None


class NearbyPlace(Strict):
    """Public business names only; no housing property identifiers or coordinates."""

    place_id: str
    name: str
    family_label: str
    maps_url: str | None = None


class HousingRecommendation(Strict):
    rank: int = Field(ge=1)
    recommended: bool
    reasons: list[str]
    rent_burden_minimum: float | None = Field(None, ge=0)
    rent_burden_maximum: float | None = Field(None, ge=0)
    income_stage: Literal["not_selected", "target_job_scenario", "interim_job_scenario"] = "not_selected"


class HousingArea(Strict):
    """Publishable ZIP / city aggregate. No property addresses, IDs, or coordinates (Zillow README)."""

    area_id: str
    area_type: Literal["zip", "city"]
    label: str
    usable_rental_records: int
    suppressed: bool = Field(..., description="True when the cell is too small to publish detailed stats")
    median_monthly_rent: float | None = None
    rent_p25: float | None = None
    rent_p75: float | None = None
    rent_basis: Literal["listed_rent", "rent_estimate"] = "listed_rent"
    bedrooms: dict[str, int] = Field(default_factory=dict)
    property_types: dict[str, int] = Field(default_factory=dict)
    nearby_services: list[NearbyServiceSummary] = Field(default_factory=list)
    nearby_places: list[NearbyPlace] = Field(default_factory=list, max_length=10)
    source_note: str | None = None
    recommendation: HousingRecommendation | None = None


class HousingSection(Strict):
    status: Literal["ok", "no_results", "not_integrated"]
    areas: list[HousingArea] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    ranking_note: str | None = None


# ----------------------------------------------------------------------------- services (Person 4)


class Verification(Strict):
    status: Literal["verified_public_community", "verified_private", "verified_type_unknown",
                    "verification_incomplete", "unverified"]
    provider_type: str | None = None
    official_url: str | None = None
    checked_on: str | None = None
    cost_eligibility_notes: str | None = None
    service_area: str | None = None


class Eligibility(Strict):
    age_status: Literal["eligibility_needs_confirmation", "age_not_provided",
                        "meets_published_age_criterion", "outside_published_age_criterion"]
    note: str


class RatingInfo(Strict):
    overall_rating: float | None
    overall_review_count: int | None
    ranking_score: float | None
    family_mean_rating: float | None
    prior_weight_m: float | None
    overall_star_distribution: dict[str, int] | None = Field(
        None, description="Google's overall 1-5 star counts (all reviews), distinct from the sampled reviews")
    source: str


class Snippet(Strict):
    text: str
    topic: str | None = None
    attribution: str


class ReviewEvidence(Strict):
    sampled_review_count: int
    sampled_text_count: int
    date_min: str | None
    date_max: str | None
    star_distribution: dict[str, int]
    snippets: list[Snippet]
    note: str


class Distance(Strict):
    miles: float | None
    reference_point: str | None
    measure: str | None


class Availability(Strict):
    permanently_closed: bool | None
    temporarily_closed: bool | None
    hours_text: str
    note: str


class Contact(Strict):
    """Publicly listed business contact details (distinct from private housing addresses)."""

    address: str | None
    city: str | None
    zipcode: str | None
    phone: str | None
    website: str | None
    maps_url: str | None


class ServiceCard(Strict):
    place_id: str
    name: str
    need: Need
    family: str
    family_label: str
    group: str
    verification: Verification
    eligibility: Eligibility
    rating: RatingInfo
    review_evidence: ReviewEvidence
    distance: Distance
    availability: Availability
    contact: Contact
    source: dict
    confirm_prompt: str


class ServiceGroup(Strict):
    key: Literal["verified_support", "highly_rated", "other_rated", "limited_review_evidence",
                 "essential_services", "temporarily_closed"]
    label: str
    note: str | None
    total: int
    items: list[ServiceCard]


class ServicesSection(Strict):
    status: Literal["ok", "no_results"]
    priority_need: Need
    need_label: str
    sort: Literal["highly_rated", "nearest"]
    reference_point: dict
    search_area: str
    families_considered: list[str]
    ranking_settings: dict
    groups: list[ServiceGroup]
    notes: list[str]


# ----------------------------------------------------------------------------- response


class NextStep(Strict):
    id: str
    text: str
    tab: Literal["jobs", "housing", "services"]


class DataCoverage(Strict):
    mode: Literal["real", "synthetic"]
    sources: dict[str, dict]
    notes: list[str]


class ServiceMapPoint(Strict):
    """Coordinates of a publicly listed service, never a rental property."""

    place_id: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RecommendationResponse(Strict):
    open_tab: Literal["jobs", "housing", "services"]
    jobs: JobsSection
    housing_areas: HousingSection
    service_map_points: list[ServiceMapPoint] = Field(default_factory=list)
    services: ServicesSection
    data_coverage: DataCoverage
    next_steps: list[NextStep]
    disclaimer: str
    reentry_plan: ReentryPlan | None = None
    phoenix_session: PhoenixSession | None = None
    selected_job_id: str | None = None
    thirty_day_plan: ThirtyDayPlan | None = None
    housing_comparisons: list[dict] = Field(default_factory=list)
    housing_income_job_id: str | None = None
    housing_income_stage: Literal["not_selected", "target_job_scenario", "interim_job_scenario"] = "not_selected"


# ----------------------------------------------------------------------------- housing comparison


class HousingComparisonRequest(Strict):
    pay_min: float | None = Field(None, gt=0)
    pay_max: float | None = Field(None, gt=0)
    pay_period: Literal["hour", "day", "week", "month", "year"] | None = None
    hours_per_week: float | None = Field(None, gt=0, le=80, description="Stated hours; null -> labeled 40h assumption for hourly/daily pay")
    monthly_rent: float | None = Field(None, gt=0)
    area_label: str | None = None


class HousingComparisonResponse(Strict):
    annual_gross_min: float | None
    annual_gross_max: float | None
    monthly_rent: float | None
    rent_burden_min: float | None = Field(None, description="Lowest burden (uses highest pay)")
    rent_burden_max: float | None = Field(None, description="Highest burden (uses lowest pay)")
    status: Literal["ok", "unknown"]
    assumptions: list[str]
    formula: str = "rent_burden = 12 * monthly_rent / annual_gross_pay"
    caveat: str

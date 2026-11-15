"""Versioned, JSON-schema-exportable contracts shared with the API/UI teams."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Point(Contract):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    precision: Literal["worksite", "city_center", "zip_center", "user_provided"]
    label: str
    source: str | None = None


class Pay(Contract):
    minimum: float | None = Field(default=None, gt=0)
    maximum: float | None = Field(default=None, gt=0)
    period: Literal["hour", "day", "week", "month", "year", "unknown"] = "unknown"
    currency: str | None = None
    source: Literal["advertised", "missing", "ambiguous"] = "missing"
    raw: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered_range(self) -> Pay:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("pay minimum exceeds maximum")
        return self


class Requirement(Contract):
    field: Literal["education", "experience_years", "certification"]
    value: str | float
    kind: Literal["required", "preferred", "alternative", "uncertain"]
    evidence: str = Field(min_length=1)
    source: str = "extraction_rules"
    scope: str | None = None

    @property
    def key(self) -> str:
        value = json.dumps([self.field, str(self.value).casefold(), self.kind, self.scope], sort_keys=True)
        return "req-" + hashlib.sha256(value.encode()).hexdigest()[:12]


class Job(Contract):
    job_id: str
    title: str
    company: str
    city: str | None = None
    state: str | None = None
    location_text: str
    description: str = ""
    job_type: str | None = None
    pay: Pay = Field(default_factory=Pay)
    hours_per_week: float | None = Field(default=None, gt=0, le=168)
    weeks_per_year: float | None = Field(default=None, gt=0, le=53)
    point: Point | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    source_url: str | None = None
    posted_at: str | None = None
    is_expired: bool | None = None
    duplicate_group: str | None = None
    source_file: str | None = None
    source_row: int | None = Field(default=None, ge=1)


class Experience(Contract):
    skills: list[str] = Field(default_factory=list)
    text: str = ""
    years: float | None = Field(default=None, ge=0, le=100)


class Education(Contract):
    level: Literal["unknown", "none", "high_school", "some_college", "associate", "bachelor", "master", "doctorate"] = "unknown"
    certifications: list[str] = Field(default_factory=list)
    no_certifications: bool = False


class UserProfile(Contract):
    age: int | None = Field(default=None, ge=0, le=120)
    location: str = Field(min_length=1)
    priority_need: Literal["work", "housing", "food", "health", "transportation", "community_support"]
    experience: Experience = Field(default_factory=Experience)
    education: Education = Field(default_factory=Education)
    # Optional internal resolver/filter fields; not extra required onboarding questions.
    search_cities: list[str] = Field(default_factory=list)
    reference_point: Point | None = None
    max_distance_miles: float | None = Field(default=None, gt=0)
    sort: Literal["recommended", "highest_pay", "nearest"] = "recommended"
    qualification_answers: dict[str, dict[str, bool]] = Field(default_factory=dict)


class RecommendationRequest(Contract):
    profile: UserProfile
    selected_job_id: str | None = None
    selected_interim_job_id: str | None = None
    scenario_hours_per_week: float | None = Field(default=None, gt=0, le=168)
    scenario_weeks_per_year: float | None = Field(default=None, gt=0, le=53)

    @model_validator(mode="after")
    def interim_requires_target(self) -> RecommendationRequest:
        if self.selected_interim_job_id is not None and self.selected_job_id is None:
            raise ValueError("Select a target job before selecting interim work")
        return self


class Rental(Contract):
    """Internal only: never serialize individual records into the public response."""

    property_id: str
    city: str
    zipcode: str | None = None
    monthly_rent: float = Field(gt=0)
    currency: str = "USD"
    bedrooms: float | None = Field(default=None, ge=0)
    home_type: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    rent_basis: Literal["listed_price_unverified", "base_rent_cross_checked"]
    availability: Literal["snapshot_only"] = "snapshot_only"
    source_file: str | None = None
    source_row: int | None = None


class ServiceLocation(Contract):
    """Person 4 supplies deduplicated/mapped candidate locations, not reviewer data."""

    place_id: str
    service_family: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    permanently_closed: bool | None = None
    temporarily_closed: bool | None = None


class AreaServiceAccess(Contract):
    service_family: str
    radius_miles: float
    properties_with_coordinates: int = Field(ge=5)
    median_service_count_within_radius: float = Field(ge=0)
    share_of_properties_with_service: float = Field(ge=0, le=1)
    measurement: Literal["straight_line_proximity_not_travel_time"] = "straight_line_proximity_not_travel_time"


class HousingArea(Contract):
    area_id: str
    city: str
    zipcode: str | None = None
    geography: Literal["zipcode", "city"]
    listing_count: int = Field(ge=1)
    median_monthly_rent: float = Field(gt=0)
    minimum_monthly_rent: float = Field(gt=0)
    maximum_monthly_rent: float = Field(gt=0)
    currency: str = "USD"
    rent_basis: str
    notes: list[str] = Field(default_factory=list)
    service_access: list[AreaServiceAccess] = Field(default_factory=list)
    service_access_status: Literal["not_connected", "available", "insufficient_coordinates", "no_candidates"] = "not_connected"


class QualificationCheck(Contract):
    key: str
    field: Literal["education", "experience_years", "certification"]
    requirement_kind: Literal["required", "preferred", "alternative", "uncertain"]
    label: str
    status: Literal["reported_met", "gap", "needs_confirmation", "preferred"]
    detail: str


class JobCard(Contract):
    job_id: str
    title: str
    company: str
    city: str | None
    location_text: str
    source_url: str | None
    posted_at: str | None
    availability: Literal["expired_snapshot", "not_marked_expired_in_snapshot", "unknown"]
    pay: Pay
    fit_tier: Literal["strong_match", "possible_match", "qualification_gap"]
    matched_skills: list[str]
    qualification_gaps: list[str]
    unknowns: list[str]
    requirements: list[Requirement]
    pay_basis: str
    comparable_pay_minimum: float | None
    pay_assumptions: list[str]
    approximate_distance_miles: float | None
    distance_reference: str | None
    location_precision: str
    worksite_location_source: str | None
    ranking_explanation: list[str]
    selectable: bool = True
    is_selected: bool = False
    credential_summary: str = "Requirements need confirmation."
    matches_reported_role: bool | None = None
    qualification_checks: list[QualificationCheck] = Field(default_factory=list)


class PlanLink(Contract):
    label: str
    url: str
    role: Literal["job_posting", "official_requirements", "provider_finder", "funding_support"]


class PlanStep(Contract):
    step_id: str
    day_start: int = Field(ge=1, le=30)
    day_end: int = Field(ge=1, le=30)
    title: str
    action: str
    track: Literal["job_confirmation", "credential", "interim_work", "application", "experience"]
    depends_on: list[str] = Field(default_factory=list)
    links: list[PlanLink] = Field(default_factory=list)


class CredentialPath(Contract):
    credential: str
    requirement_kind: Literal["required", "preferred", "alternative", "uncertain"]
    user_status: Literal["reported_held", "not_confirmed"]
    job_evidence: str
    evidence_source: str
    completion_within_30_days: Literal["not_guaranteed"] = "not_guaranteed"
    links: list[PlanLink] = Field(default_factory=list)


class InterimJobOption(Contract):
    job_id: str
    title: str
    company: str
    pay: Pay
    credential_summary: str
    confirmation_needed: list[str]
    source_url: str | None
    is_selected: bool = False


class DailyPlanAction(Contract):
    action_id: str
    day: int = Field(ge=1, le=30)
    title: str
    action: str
    phase: str
    links: list[PlanLink] = Field(default_factory=list)


class ThirtyDayPlan(Contract):
    target_job_id: str
    target_job_title: str
    selected_interim_job_id: str | None = None
    credential_paths: list[CredentialPath] = Field(default_factory=list)
    interim_jobs: list[InterimJobOption] = Field(default_factory=list)
    steps: list[PlanStep]
    daily_actions: list[DailyPlanAction] = Field(default_factory=list)
    notes: list[str]

    @model_validator(mode="after")
    def complete_daily_schedule(self) -> ThirtyDayPlan:
        # Empty is retained for older fixtures/clients. Generated plans have all 30 days.
        if self.daily_actions and (sorted(a.day for a in self.daily_actions) != list(range(1, 31))
                or len({a.action_id for a in self.daily_actions}) != 30):
            raise ValueError("A daily schedule must contain days 1–30 with unique action IDs")
        return self


class RecommendationResponse(Contract):
    schema_version: str = "1.1.0"
    data_mode: Literal["synthetic", "sample", "full"]
    jobs: list[JobCard]
    job_group_order: list[str]
    housing_areas: list[HousingArea]
    # Person 4 supplies service cards. This adapter does not invent service results.
    services: list[dict] = Field(default_factory=list)
    service_status: Literal["not_connected", "provided"] = "not_connected"
    housing_comparisons: list[dict] = Field(default_factory=list)
    data_coverage: dict = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    selected_job_id: str | None = None
    thirty_day_plan: ThirtyDayPlan | None = None
    housing_income_job_id: str | None = None
    housing_income_stage: Literal["not_selected", "target_job_scenario", "interim_job_scenario"] = "not_selected"

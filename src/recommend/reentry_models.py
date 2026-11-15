"""Additive, versioned contracts for the optional deterministic reentry planner."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.phoenix.models import DailyPlanAction
from src.recommend.reentry_domain import ResourceType

Need = Literal["work", "housing", "food", "health_care", "transportation", "community_support"]
Answer = Literal["yes", "no", "unsure", "prefer_not_to_say"]
Priority = Literal["immediate", "high", "medium", "later"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReentrySituation(Contract):
    # Legacy API requests stay compatible. UI onboarding requires a response,
    # including uncertainty/privacy choices, rather than sensitive disclosure.
    release_status: Literal["preparing_for_release", "already_released", "unsure", "prefer_not_to_say"] | None = None
    release_date: date | None = None
    has_immediate_housing: Answer | None = None
    has_id: Answer | None = None
    has_transportation: Answer | None = None
    has_phone_access: Answer | None = None
    has_required_appointment: Answer | None = None
    priority_need: Need | None = None
    employment_goal: Literal["find_work", "prepare_for_work", "keep_work", "not_now", "unsure"] | None = None


class Referral(Contract):
    resource_id: str
    name: str
    url: str | None = None
    verification: Literal["verified_reentry_scope", "verified_general_service", "unverified"]
    provider_category: str
    scope: str
    source_url: str | None = None
    checked_on: date | None = None
    confirmation: str = "Contact to confirm current services, cost, eligibility, and availability."
    resource_types: list[ResourceType] = Field(default_factory=list)
    city: str | None = None
    service_area_cities: list[str] = Field(default_factory=list)
    category_evidence: str | None = None
    distance_miles: float | None = None
    phone: str | None = None
    address: str | None = None


class ReentryTask(Contract):
    task_id: str
    title: str
    action: str
    barrier: str
    priority: Priority
    stage: Literal["immediate_stability", "removing_barriers", "building_independence"] = "removing_barriers"
    resource_tab: Literal["jobs", "housing", "services"] | None = None
    resource_need: Need | None = None
    prerequisites: list[str] = Field(default_factory=list)
    rationale: str
    confirmations: list[str] = Field(default_factory=list)
    deadline: date | None = None
    planning_day: int = Field(1, ge=1, le=30)
    status: Literal["todo", "waiting", "completed"] = "todo"
    referrals: list[Referral] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)


class ReentryDay(DailyPlanAction):
    task_ids: list[str] = Field(default_factory=list)


class ReentryPlan(Contract):
    version: Literal["1"] = "1"
    start_date: date
    synthetic: bool
    tasks: list[ReentryTask]
    next_task_ids: list[str]
    completed_ids: list[str]
    daily_actions: list[ReentryDay]
    notes: list[str]

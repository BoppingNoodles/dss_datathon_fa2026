"""Versioned, device-local reentry state; source evidence and user reports stay separate."""
from __future__ import annotations

from datetime import date as Date, datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

SupportNeed = Literal["housing", "employment", "food", "healthcare", "transportation", "identification", "education", "community_support"]
ResourceStatus = Literal["recommended", "saved", "selected", "contacted", "applied", "accepted", "rejected", "dismissed"]
TaskStatus = Literal["not_started", "in_progress", "blocked", "completed", "skipped"]
ResourceType = Literal["job_posting", "transitional_housing", "housing_assistance", "rental_market", "transportation_assistance", "public_transit", "identification_assistance", "workforce_training", "food_assistance", "healthcare", "community_support"]


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProfileLocation(Domain):
    city: str = Field("", max_length=80)
    zipCode: str | None = Field(None, pattern=r"^\d{5}$")

    @model_validator(mode="after")
    def location_known(self):
        if len(self.city.strip()) < 2 and not self.zipCode:
            raise ValueError("A city or ZIP is required")
        return self


class Release(Domain):
    status: Literal["pre_release", "post_release", "unsure", "prefer_not_to_answer"]
    date: Date | None = None


class HousingSituation(Domain):
    status: Literal["stable", "temporary", "no_confirmed_housing", "unsure"]
    temporaryHousingEndDate: Date | None = None
    monthlyBudget: float | None = Field(None, ge=0, le=100000)


class EmploymentSituation(Domain):
    status: Literal["unemployed", "employed", "seeking_training", "not_seeking", "unsure"]
    preferredJobTypes: list[str] = Field(default_factory=list, max_length=30)
    experienceYears: float | None = Field(None, ge=0, le=60)
    skills: list[str] = Field(default_factory=list, max_length=100)
    experienceText: str | None = Field(None, max_length=1000)
    noExperienceYet: bool = False
    educationLevel: Literal["no_diploma", "high_school_or_ged", "some_college", "associate", "bachelor", "graduate", "not_sure"] | None = None
    certifications: list[str] = Field(default_factory=list, max_length=100)
    noCertifications: bool = False

    @model_validator(mode="after")
    def credentials_consistent(self):
        if self.noCertifications and self.certifications:
            raise ValueError("Choose certificates or none, not both")
        return self


class Barriers(Domain):
    hasFoodAccess: bool | None = None
    hasGovernmentId: bool | None = None
    hasTransportation: bool | None = None
    hasPhoneAccess: bool | None = None
    hasInternetAccess: bool | None = None
    communicationAccess: Literal["reliable", "limited", "none", "unsure"] = "unsure"


class Appointment(Domain):
    id: str = Field(min_length=1, max_length=120)
    label: str = Field("Appointment", min_length=1, max_length=120)
    date: Date | None = None
    location: str | None = Field(None, max_length=160)


class FinanceProjection(Domain):
    jobId: str | None = Field(None, max_length=200)
    housingId: str | None = Field(None, max_length=200)
    hoursPerWeek: float = Field(40, gt=0, le=80)
    takeHomePercent: float = Field(80, gt=0, le=100)
    estimatedFields: list[Literal["monthlyTakeHomePay", "monthlyHousingCost", "monthlyFoodCost", "monthlyOtherCosts"]] = Field(default_factory=list, max_length=4)


class Finances(Domain):
    monthlyTakeHomePay: float | None = Field(None, ge=0, le=1000000)
    monthlyHousingCost: float | None = Field(None, ge=0, le=1000000)
    monthlyFoodCost: float | None = Field(None, ge=0, le=1000000)
    monthlyOtherCosts: float | None = Field(None, ge=0, le=1000000)
    projection: FinanceProjection | None = None

    @field_validator("monthlyTakeHomePay", "monthlyHousingCost", "monthlyFoodCost", "monthlyOtherCosts")
    @classmethod
    def dollars_and_cents(cls, value):
        if value is not None and round(value, 2) != value:
            raise ValueError("Use dollars and cents, with at most two decimal places")
        return value


class ReentryProfile(Domain):
    profileId: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=100)
    location: ProfileLocation
    release: Release
    housing: HousingSituation
    employment: EmploymentSituation
    barriers: Barriers
    supportNeeds: list[SupportNeed] = Field(default_factory=list, max_length=8)
    upcomingAppointments: list[Appointment] = Field(default_factory=list, max_length=20)
    appointmentStatus: Literal["yes", "no", "unsure", "prefer_not_to_answer"] = "unsure"
    goals: list[str] = Field(default_factory=list, max_length=20)
    finances: Finances = Field(default_factory=Finances)

    @model_validator(mode="after")
    def unique_appointments(self):
        if len({a.id for a in self.upcomingAppointments}) != len(self.upcomingAppointments):
            raise ValueError("Appointment IDs must be unique")
        return self


class Recommendation(Domain):
    id: str
    category: Literal["job", "housing", "service"]
    title: str
    description: str
    source: str
    sourceUrl: str | None = None
    # Exact rental coordinates/addresses stay in the private source pipeline.
    location: dict[str, str] = Field(default_factory=dict)
    score: float = Field(ge=0, le=1)
    matchReasons: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    verificationStatus: Literal["verified", "partially_verified", "unverified"] = "unverified"
    availabilityStatus: Literal["confirmed_available", "confirmed_unavailable", "unknown"] = "unknown"
    userStatus: ResourceStatus = "recommended"
    userReportedAvailability: Literal["available", "unavailable"] | None = None
    mode: Literal["job", "temporary_housing", "long_term_area", "service"]
    active: bool = True
    details: dict[str, Any] = Field(default_factory=dict)
    resourceType: ResourceType = "community_support"
    supportedResourceTypes: list[ResourceType] = Field(default_factory=list, max_length=11)
    serviceEvidence: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def compatible_type_defaults(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            value.setdefault("resourceType", {"job": "job_posting", "long_term_area": "rental_market", "temporary_housing": "housing_assistance"}.get(value.get("mode"), "community_support"))
            if not value.get("supportedResourceTypes"):
                value["supportedResourceTypes"] = [value["resourceType"]]
        return value


class PlanTask(Domain):
    id: str
    title: str
    description: str
    category: Literal["housing", "employment", "documents", "transportation", "healthcare", "community_support", "other"]
    priority: Literal["critical", "high", "medium", "low"]
    status: TaskStatus = "not_started"
    prerequisiteTaskIds: list[str] = Field(default_factory=list)
    relatedRecommendationIds: list[str] = Field(default_factory=list)
    rationale: str
    deadline: Date | None = None
    estimatedDurationDays: int | None = Field(None, ge=1, le=365)
    source: Literal["profile", "recommendation", "user", "planner"] = "planner"
    userEditable: bool = True
    notes: str = Field("", max_length=1000)
    stage: Literal["immediate_stability", "removing_barriers", "building_independence"] = "removing_barriers"
    archived: bool = False
    blockedByUser: bool = False
    allowedResourceTypes: list[ResourceType] = Field(default_factory=list, max_length=11)
    resourceMatchReasons: dict[str, str] = Field(default_factory=dict)
    referenceLinks: list[dict[str, str]] = Field(default_factory=list, max_length=10)
    resourceEmptyState: str | None = None
    completionOutcome: Literal["housing_arranged", "food_secured", "transportation_arranged"] | None = None


def completion_outcome(task: PlanTask):
    if task.id.startswith(("reentry:housing-now", "reentry:confirm-housing", "housing:arrangement-check:", "housing:continuity")):
        return "housing_arranged"
    if task.id.startswith(("reentry:priority-food", "support:food")):
        return "food_secured"
    if task.id.startswith(("reentry:transportation", "reentry:confirm-transportation")):
        return "transportation_arranged"
    return None


class UserEvent(Domain):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=120)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: Literal["profile_updated", "resource_status", "resource_unavailable", "task_status", "job_obtained", "job_lost", "housing_changed", "transportation_changed"]
    payload: dict[str, Any] = Field(default_factory=dict)


class PlanChange(Domain):
    type: str
    task_id: str | None = None
    reason: str


class PhoenixSession(Domain):
    schemaVersion: Literal[1] = 1
    profile: ReentryProfile
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=500)
    tasks: list[PlanTask] = Field(default_factory=list, max_length=500)
    selectedRecommendationIds: list[str] = Field(default_factory=list, max_length=200)
    dismissedRecommendationIds: list[str] = Field(default_factory=list, max_length=500)
    events: list[UserEvent] = Field(default_factory=list, max_length=2000)
    lastPlannedAt: datetime | None = None
    changes: list[PlanChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    topJobIds: list[str] = Field(default_factory=list)
    schedule: list[dict] = Field(default_factory=list)
    scheduleStartDate: Date | None = None

    @model_validator(mode="after")
    def coherent_progress(self):
        ids = {t.id for t in self.tasks}
        if len(ids) != len(self.tasks) or any(not set(t.prerequisiteTaskIds) <= ids for t in self.tasks):
            raise ValueError("Duplicate task ID or unknown prerequisite")
        seen = set()
        while len(seen) < len(ids):
            ready = {t.id for t in self.tasks if t.id not in seen and set(t.prerequisiteTaskIds) <= seen}
            if not ready:
                raise ValueError("Task dependency cycle")
            seen |= ready
        malformed_days = any(not isinstance(d.get("day"), int) or not isinstance(d.get("action_id"), str)
            or not isinstance(d.get("task_ids"), list) or not all(isinstance(i, str) for i in d["task_ids"]) for d in self.schedule)
        if self.schedule and (malformed_days or len(self.schedule) != 30
                or {d.get("day") for d in self.schedule} != set(range(1, 31))
                or len({d.get("action_id") for d in self.schedule}) != 30):
            raise ValueError("A schedule must contain 30 distinct suggested days with task IDs")
        return self


def profile_request(profile: ReentryProfile) -> dict:
    """Adapt into existing request names, keeping the existing data adapters."""
    p = profile
    need_map = {"employment": "work", "healthcare": "health_care", "identification": "community_support", "education": "work"}
    needs = [need_map.get(n, n) for n in p.supportNeeds]
    priority = needs[0] if needs else "work" if p.employment.status in {"unemployed", "seeking_training"} else "community_support"
    answer = lambda v: "yes" if v is True else "no" if v is False else "unsure"
    communication = (True if p.barriers.hasPhoneAccess is True or p.barriers.hasInternetAccess is True else
                     False if p.barriers.hasPhoneAccess is False and p.barriers.hasInternetAccess is False else None)
    return dict(location=p.location.zipCode or p.location.city, priority_need=priority,
        experience={"skills": p.employment.skills, "text": p.employment.experienceText,
                    "years": p.employment.experienceYears, "no_experience_yet": p.employment.noExperienceYet},
        education={"level": p.employment.educationLevel, "credentials": p.employment.certifications,
                   "no_credentials": p.employment.noCertifications},
        reentry={"release_status": {"pre_release": "preparing_for_release", "post_release": "already_released", "prefer_not_to_answer": "prefer_not_to_say"}.get(p.release.status, "unsure"),
            "release_date": p.release.date, "has_immediate_housing": "yes" if p.housing.status in {"stable", "temporary"} else "no" if p.housing.status == "no_confirmed_housing" else "unsure",
            "has_id": answer(p.barriers.hasGovernmentId), "has_transportation": answer(p.barriers.hasTransportation),
            "has_phone_access": answer(communication), "has_required_appointment": "yes" if p.upcomingAppointments else "prefer_not_to_say" if p.appointmentStatus == "prefer_not_to_answer" else p.appointmentStatus,
            "priority_need": priority, "employment_goal": {"unemployed": "find_work", "seeking_training": "prepare_for_work", "employed": "keep_work", "not_seeking": "not_now"}.get(p.employment.status, "unsure")})


def apply_event(profile: ReentryProfile, previous: PhoenixSession | None, event: UserEvent | None) -> tuple[ReentryProfile, PhoenixSession | None]:
    """Apply only user-report fields to a copy. Source datasets are never mutated."""
    state = previous.model_copy(deep=True) if previous else None
    if state and state.profile.profileId != profile.profileId:
        raise ValueError("Session and profile IDs differ")
    if not state and event and event.type in {"resource_status", "resource_unavailable", "task_status"}:
        raise ValueError("This update requires an existing plan")
    if not event or (state and any(e.id == event.id for e in state.events)):
        return profile, state
    event = event.model_copy(deep=True)
    event.payload.pop("employmentTransition", None)
    value = profile.model_dump(mode="json")
    payload = event.payload
    if event.type == "profile_updated":
        # A full validated profile avoids unsafe arbitrary nested patch paths.
        value = ReentryProfile.model_validate(payload["profile"]).model_dump(mode="json")
        if value["profileId"] != profile.profileId:
            raise ValueError("An update must retain the current profile ID")
        if value["employment"]["status"] != profile.employment.status:
            event.payload["employmentTransition"] = "job_obtained" if value["employment"]["status"] == "employed" else "job_lost" if profile.employment.status == "employed" and value["employment"]["status"] == "unemployed" else "work_goal_changed"
    elif event.type in {"job_obtained", "job_lost"}:
        value["employment"]["status"] = "employed" if event.type == "job_obtained" else "unemployed"
    elif event.type == "housing_changed":
        value["housing"] = HousingSituation.model_validate(payload).model_dump(mode="json")
    elif event.type == "transportation_changed":
        reported = payload.get("hasTransportation")
        if reported is not None and not isinstance(reported, bool):
            raise ValueError("Transportation must be yes, no, or unknown")
        value["barriers"]["hasTransportation"] = reported
    reported_barriers = []
    if value["housing"]["status"] == "no_confirmed_housing" and profile.housing.status != "no_confirmed_housing":
        reported_barriers.append("housing")
    for field, barrier in (("hasGovernmentId", "identification"), ("hasTransportation", "transportation"), ("hasFoodAccess", "food")):
        if value["barriers"][field] is False and getattr(profile.barriers, field) is not False:
            reported_barriers.append(barrier)
    new_access = value["barriers"]
    if (new_access["hasPhoneAccess"] is False and new_access["hasInternetAccess"] is False
            and not (profile.barriers.hasPhoneAccess is False and profile.barriers.hasInternetAccess is False)):
        reported_barriers.append("communication")
    event.payload["reportedBarriers"] = reported_barriers
    if state:
        if event.type in {"resource_status", "resource_unavailable"}:
            resource = next((r for r in state.recommendations if r.id == payload.get("recommendationId")), None)
            if resource is None:
                raise ValueError("Choose an existing recommendation")
            status = "rejected" if event.type == "resource_unavailable" else payload.get("status")
            resource.userStatus = Recommendation.model_validate({**resource.model_dump(), "userStatus": status}).userStatus
            if event.type == "resource_unavailable":
                resource.userReportedAvailability = "unavailable"
            if status in {"selected", "contacted", "applied", "accepted"} and resource.id not in state.selectedRecommendationIds:
                state.selectedRecommendationIds.append(resource.id)
            if status == "dismissed":
                state.dismissedRecommendationIds = list(dict.fromkeys([*state.dismissedRecommendationIds, resource.id]))
                state.selectedRecommendationIds = [r for r in state.selectedRecommendationIds if r != resource.id]
            elif status == "recommended":
                state.dismissedRecommendationIds = [r for r in state.dismissedRecommendationIds if r != resource.id]
                state.selectedRecommendationIds = [r for r in state.selectedRecommendationIds if r != resource.id]
                resource.userReportedAvailability = None
            if status in {"saved", "selected"}:
                state.dismissedRecommendationIds = [r for r in state.dismissedRecommendationIds if r != resource.id]
                if status == "saved":
                    state.selectedRecommendationIds = [r for r in state.selectedRecommendationIds if r != resource.id]
        elif event.type == "task_status":
            task = next((t for t in state.tasks if t.id == payload.get("taskId")), None)
            if task is None:
                raise ValueError("Choose an existing task")
            update = {**task.model_dump(), "status": payload.get("status", task.status), "notes": payload.get("notes", task.notes)}
            validated = PlanTask.model_validate(update)
            if validated.status == "completed" and task.status != "completed":
                completed = {t.id for t in state.tasks if t.status == "completed"}
                if not set(task.prerequisiteTaskIds) <= completed:
                    raise ValueError("Complete the required prerequisite steps first")
            if payload.get("outcome") is not None:
                outcome = completion_outcome(task)
                if validated.status != "completed" or not outcome or payload["outcome"] != outcome:
                    raise ValueError("Choose a result that belongs to this completed step")
                if outcome == "housing_arranged" and value["housing"]["status"] != "stable":
                    value["housing"]["status"] = "temporary"
                    value["housing"]["temporaryHousingEndDate"] = None
                elif outcome == "food_secured":
                    value["barriers"]["hasFoodAccess"] = True
                elif outcome == "transportation_arranged":
                    value["barriers"]["hasTransportation"] = True
            task.status, task.notes = validated.status, validated.notes
            task.blockedByUser = validated.status == "blocked"
        # Declared outcomes finish matching need-based steps. Preferences and
        # completed research alone are not declarations of a secured result.
        newly_met = set()
        if value["housing"]["status"] in {"stable", "temporary"} and profile.housing.status not in {"stable", "temporary"}:
            newly_met.add("housing_arranged")
        if value["housing"]["status"] == "stable" and profile.housing.status == "temporary":
            newly_met.add("housing_arranged")
        for field, outcome in (("hasFoodAccess", "food_secured"), ("hasTransportation", "transportation_arranged")):
            if value["barriers"][field] is True and getattr(profile.barriers, field) is not True:
                newly_met.add(outcome)
        completed_from_report = []
        for related_task in state.tasks:
            if not related_task.archived and completion_outcome(related_task) in newly_met and related_task.status != "completed":
                related_task.status, related_task.blockedByUser = "completed", False
                completed_from_report.append(related_task.id)
        if completed_from_report:
            event.payload["completedTasksFromSituation"] = completed_from_report
        state.events.append(event)
    return ReentryProfile.model_validate(value), state

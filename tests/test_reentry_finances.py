from datetime import date

import pytest
from pydantic import ValidationError

from src.recommend.reentry_domain import Finances, PhoenixSession, ReentryProfile, Recommendation
from src.recommend.reentry_finances import assess_finances
from src.recommend.reentry_planner import planned_session


def profile(finances=None, status="unemployed"):
    return ReentryProfile.model_validate({"profileId": "fictional-budget", "location": {"city": "Oakland"}, "release": {"status": "post_release"},
        "housing": {"status": "stable"}, "employment": {"status": status, "skills": ["Warehouse"]},
        "barriers": {"hasGovernmentId": True, "hasTransportation": True, "hasFoodAccess": True, "hasPhoneAccess": True, "hasInternetAccess": True},
        **({"finances": finances} if finances else {})})


@pytest.mark.parametrize("values,status,remaining", [
    ((3000, 800, 300, 300), "within_budget", 1600),
    ((3000, 1000, 300, 300), "high_housing", 1400),
    ((2000, 1400, 300, 200), "tight", 100),
    ((1000, 800, 250, 200), "deficit", -250),
    ((0, 500, 0, 0), "deficit", -500),
    ((10.01, 4.10, 2.20, 3.30), "tight", 0.41),
])
def test_monthly_cashflow_is_explicit_and_cent_accurate(values, status, remaining):
    finance = Finances.model_validate(dict(zip(Finances.model_fields, values)))
    result = assess_finances(finance)
    assert result["status"] == status
    assert result["remaining"] == remaining


def test_unknown_costs_are_not_zero_and_threshold_boundaries_are_stated():
    unknown = assess_finances(Finances(monthlyTakeHomePay=3000, monthlyHousingCost=900))
    assert unknown["status"] == "incomplete" and unknown["remaining"] is None
    assert unknown["housingHigh"] is False
    assert assess_finances(Finances(monthlyTakeHomePay=3000, monthlyHousingCost=900, monthlyFoodCost=1000, monthlyOtherCosts=500))["status"] == "tight"
    for invalid in (-1, 0.001, float("inf")):
        with pytest.raises(ValidationError):
            Finances(monthlyTakeHomePay=invalid)


def test_financial_replanning_adds_relevant_steps_and_preserves_completed_history():
    candidates = [
        Recommendation(id="provider:food", category="service", mode="service", title="Fictional food pantry", description="Meals", source="fixture", score=.8,
            resourceType="food_assistance", serviceEvidence={"food_assistance": "Fixture source explicitly offers food assistance."}, location={"city": "Oakland"}, details={"barrier": "food"}),
        Recommendation(id="area:budget", category="housing", mode="long_term_area", title="Fictional rent area", description="Area costs", source="fixture", score=.5,
            resourceType="rental_market", location={"city": "Oakland"}),
        Recommendation(id="job:budget", category="job", mode="job", title="Fictional warehouse job", description="Warehouse", source="fixture", score=.7,
            resourceType="job_posting", location={"city": "Oakland"}, details={"jobId": "budget"}),
    ]
    p = profile({"monthlyTakeHomePay": 1000, "monthlyHousingCost": 800, "monthlyFoodCost": 250, "monthlyOtherCosts": 200})
    old = PhoenixSession(profile=p, recommendations=candidates)
    state = planned_session(p, candidates, old, None, today=date(2026, 11, 14), top_job_ids=["job:budget"], warnings=[])
    tasks = [task for task in state.tasks if task.id.startswith("finances:")]
    assert any(task.id.startswith("finances:budget:") and task.priority == "critical" for task in tasks)
    food = next(task for task in tasks if task.id.startswith("finances:food:"))
    assert food.relatedRecommendationIds == ["provider:food"]
    income = next(task for task in tasks if task.id.startswith("finances:income:"))
    assert income.relatedRecommendationIds == ["job:budget"]
    completed = next(task for task in tasks if task.id.startswith("finances:budget:"))
    completed.status, completed.notes = "completed", "Kept my budget review"
    changed = p.model_copy(deep=True)
    changed.finances.monthlyOtherCosts = 300
    replanned = planned_session(changed, candidates, state, None, today=date(2026, 11, 14), top_job_ids=["job:budget"], warnings=[])
    assert next(task for task in replanned.tasks if task.id == completed.id).notes == "Kept my budget review"
    assert any(task.id.startswith("finances:budget:") and task.id != completed.id and task.status == "not_started" for task in replanned.tasks)
    assert replanned.profile.employment.status == "unemployed"
    assert replanned.profile.housing.status == "stable"


def test_selected_plan_estimates_keep_their_basis_without_claiming_actual_outcomes():
    p = profile({"monthlyTakeHomePay": 1000, "monthlyHousingCost": 800, "monthlyFoodCost": 886.08, "monthlyOtherCosts": 730.92,
        "projection": {"jobId": "job:fixture", "housingId": "area:fixture", "hoursPerWeek": 20, "takeHomePercent": 80,
                       "estimatedFields": ["monthlyTakeHomePay", "monthlyHousingCost", "monthlyFoodCost", "monthlyOtherCosts"]}})
    p.housing.status = "no_confirmed_housing"
    state = planned_session(p, [], None, None, today=date(2026, 11, 14), top_job_ids=[], warnings=[])
    restored = PhoenixSession.model_validate_json(state.model_dump_json())
    assert restored.profile.finances.projection.jobId == "job:fixture"
    assert restored.profile.finances.projection.hoursPerWeek == 20
    assert restored.profile.housing.status == "no_confirmed_housing"
    assert restored.profile.employment.status == "unemployed"
    assert any("plan estimates" in task.rationale for task in restored.tasks if task.id.startswith("finances:"))
    for field, value in (("hoursPerWeek", 0), ("hoursPerWeek", 81), ("takeHomePercent", 101)):
        invalid = p.finances.model_dump()
        invalid["projection"][field] = value
        with pytest.raises(ValidationError):
            Finances.model_validate(invalid)

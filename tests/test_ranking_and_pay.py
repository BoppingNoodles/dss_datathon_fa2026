from pathlib import Path

import pytest

from src.phoenix.ingest import load_records
from src.phoenix.models import Job, Pay, Point, Requirement, UserProfile
from src.phoenix.pay import annual_income, comparable_pay, parse_pay, rent_burden
from src.phoenix.ranking import rank_jobs


@pytest.fixture
def profile():
    return UserProfile.model_validate_json(Path("examples/profile.synthetic.json").read_text())


@pytest.fixture
def jobs():
    return load_records(Path("examples/jobs.synthetic.jsonl"), Job)


@pytest.mark.parametrize("text,period,low,high", [
    ("$25–$32 an hour", "hour", 25, 32),
    ("$120K–$150K a year", "year", 120000, 150000),
    ("From $16 an hour", "hour", 16, None),
    ("Up to $18.83 an hour", "hour", None, 18.83),
    ("$25/hr", "hour", 25, 25),
    ("$1,000 per week", "week", 1000, 1000),
    ("$20 - $22 por hora", "hour", 20, 22),
    ("$60,000 - $75,000 por año", "year", 60000, 75000),
])
def test_pay_period_and_boundaries(text, period, low, high):
    pay = parse_pay(text)
    assert pay.source == "advertised"
    assert (pay.period, pay.minimum, pay.maximum) == (period, low, high)


@pytest.mark.parametrize("text", ["$0 an hour", "$30-$20 an hour", "$20", "€20 an hour",
                                      "$20 an hour or $40,000 a year", "$20 an hour plus tips", "$20,50 por hora"])
def test_ambiguous_pay_never_becomes_comparable_salary(text, jobs):
    pay = parse_pay(text)
    assert pay.source == "ambiguous"
    job = jobs[0].model_copy(update={"pay": pay})
    assert comparable_pay(job)[1] is None


def test_double_pay_half_mile_farther_wins(profile, jobs):
    cards = rank_jobs(jobs, profile)
    assert [c.job_id for c in cards[:2]] == ["example-b", "example-a"]
    assert cards[0].approximate_distance_miles - cards[1].approximate_distance_miles == pytest.approx(.5, abs=.01)
    assert cards[0].comparable_pay_minimum == 40


def test_nearest_is_explicit_user_preference(profile, jobs):
    cards = rank_jobs(jobs, profile.model_copy(update={"sort": "nearest"}))
    assert cards[0].job_id == "example-a"


def test_age_does_not_change_job_ranking(profile, jobs):
    young = rank_jobs(jobs, profile.model_copy(update={"age": 20}))
    older = rank_jobs(jobs, profile.model_copy(update={"age": 65}))
    assert [c.model_dump() for c in young] == [c.model_dump() for c in older]


def test_missing_pay_is_unknown_not_zero(profile, jobs):
    card = next(c for c in rank_jobs(jobs, profile) if c.job_id == "example-missing-pay")
    assert card.comparable_pay_minimum is None
    assert card.pay_basis == "pay_needs_confirmation"


def test_annual_pay_does_not_silently_assume_hours(jobs):
    job = jobs[0].model_copy(update={"pay": parse_pay("$80,000 a year")})
    assert comparable_pay(job)[:2] == ("USD/year", 80000)


def test_stated_hours_prevent_false_double_pay_claim(jobs):
    a = jobs[0].model_copy(update={"pay": parse_pay("$40,000 a year"), "hours_per_week": 20, "weeks_per_year": 52})
    b = jobs[1].model_copy(update={"pay": parse_pay("$80,000 a year"), "hours_per_week": 40, "weeks_per_year": 52})
    assert comparable_pay(a)[1] == comparable_pay(b)[1]


def test_only_worksite_locations_support_job_distance(profile, jobs):
    approximate = jobs[0].model_copy(update={"point": Point(latitude=37.8, longitude=-122.27,
                                                          precision="city_center", label="city centroid")})
    card = rank_jobs([approximate], profile)[0]
    assert card.approximate_distance_miles is None


def test_explicit_radius_uses_known_distances_only(profile, jobs):
    limited = profile.model_copy(update={"max_distance_miles": 2.2})
    ids = {c.job_id for c in rank_jobs(jobs, limited)}
    assert "example-a" in ids and "example-b" not in ids
    assert "example-missing-pay" in ids  # Unknown distance is not proof of being outside.


def test_expired_job_excluded_by_default(profile, jobs):
    expired = jobs[0].model_copy(update={"is_expired": True})
    assert not rank_jobs([expired], profile)
    assert rank_jobs([expired], profile, include_expired=True)[0].availability == "expired_snapshot"


def test_preferred_degree_does_not_create_qualification_gap(profile, jobs):
    job = jobs[0].model_copy(update={"requirements": [Requirement(field="education", value="bachelor",
                                kind="preferred", evidence="Bachelor's preferred.")]})
    assert not rank_jobs([job], profile)[0].qualification_gaps


def test_required_degree_gap_cannot_be_erased_by_pay(profile, jobs):
    specialist = jobs[1].model_copy(update={"requirements": [Requirement(field="education", value="bachelor",
                                kind="required", evidence="Bachelor's required.")]})
    cards = rank_jobs([jobs[0], specialist], profile)
    assert cards[0].job_id == "example-a"
    assert cards[1].fit_tier == "qualification_gap"


def test_unrelated_high_pay_does_not_become_relevant(profile, jobs):
    unrelated = jobs[1].model_copy(update={"title": "Neurosurgeon", "description": "Perform neurosurgery.",
                                        "pay": parse_pay("$500 an hour")})
    assert not rank_jobs([unrelated], profile)


def test_incidental_warehouse_terms_do_not_promote_unrelated_technical_roles(profile, jobs):
    unrelated = jobs[1].model_copy(update={"title": "Senior Data Engineer",
        "description": "Build analytics for warehouse inventory and shipping clients.",
        "pay": parse_pay("$150 an hour")})
    assert not rank_jobs([unrelated], profile)


def test_related_role_title_can_match_transferable_skill_family(profile, jobs):
    related = jobs[0].model_copy(update={"title": "Fulfillment Associate"})
    assert rank_jobs([related], profile)[0].matched_skills


def test_skipped_education_is_unknown_and_not_a_gap(profile, jobs):
    skipped = UserProfile.model_validate({**profile.model_dump(), "education": {"level": "unknown"}})
    card = rank_jobs([jobs[0]], skipped)[0]
    assert not card.qualification_gaps
    assert any("Education" in u for u in card.unknowns)
    assert card.fit_tier == "possible_match"


def test_unresolved_location_never_returns_all_jobs(profile, jobs):
    assert not rank_jobs(jobs, profile.model_copy(update={"location": "unresolved place"}))


def test_pay_increase_never_lowers_default_rank(profile, jobs):
    for amount in [21, 25, 39, 40, 80, 100]:
        raised = jobs[0].model_copy(update={"pay": Pay(minimum=amount, maximum=amount,
            period="hour", currency="USD", source="advertised")})
        cards = rank_jobs([raised, jobs[1]], profile)
        assert cards[0].job_id == ("example-a" if amount >= 40 else "example-b")


def test_income_scenario_is_explicit_and_30_percent_example_is_correct(jobs):
    assert annual_income(jobs[0])["minimum"] is None
    income = annual_income(jobs[0], scenario_hours_per_week=40, scenario_weeks_per_year=52)
    assert income["minimum"] == 41600
    assert "hypothetical" in income["assumptions"][0]
    assert rent_burden(1200, 48000) == pytest.approx(.3)
    assert rent_burden(1200, 0) is None
    assert rent_burden(None, 48000) is None

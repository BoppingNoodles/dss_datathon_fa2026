import pytest
from pydantic import ValidationError

from src.audit.privacy_check import scan
from src.phoenix.integration import build_recommendations
from src.phoenix.models import DailyPlanAction, Job, Requirement, ThirtyDayPlan, UserProfile
from src.phoenix.qualifications import qualification_checks, with_qualification_evidence
from src.phoenix.ranking import rank_jobs


@pytest.fixture
def profile():
    return UserProfile.model_validate({"location": "Oakland", "priority_need": "work",
        "experience": {"skills": ["warehouse", "inventory"], "years": 2},
        "education": {"level": "high_school"}})


def job(title="Warehouse Associate", **updates):
    return Job(job_id="target", title=title, company="Fictional employer", city="Oakland",
               location_text="Oakland, CA", source_url="https://example.com/job", **updates)


def plan_for(profile, target, **options):
    return build_recommendations(profile, [target], [], data_mode="synthetic",
        selected_job_id=target.job_id, include_other_roles=True, **options).thirty_day_plan


def test_schedule_is_complete_and_stable_across_age_and_sort(profile):
    target = job()
    plan = plan_for(profile, target)
    assert [a.day for a in plan.daily_actions] == list(range(1, 31))
    assert len({a.action_id for a in plan.daily_actions}) == 30
    assert len({a.title for a in plan.daily_actions}) == 30
    assert plan.daily_actions == plan_for(profile.model_copy(update={"age": 70, "sort": "nearest"}), target).daily_actions
    assert all(a.links[0].url == target.source_url for a in plan.daily_actions)


def test_preparation_changes_with_selected_role_without_inventing_experience(profile):
    warehouse = plan_for(profile, job())
    barista = plan_for(profile, job("Barista"))
    assert "inventory" in warehouse.daily_actions[15].action
    assert "sample order" in barista.daily_actions[15].action
    assert "food service" not in barista.daily_actions[1].action  # only reported work areas
    assert "Do not claim skills" in barista.daily_actions[3].action
    assert warehouse.daily_actions[15].action_id != barista.daily_actions[15].action_id


def test_missing_cdl_uses_pathway_and_held_cdl_uses_verification(profile):
    target = job("Warehouse / CDL-A Driver", description="Class-A CDL required.")
    missing = plan_for(profile, target)
    held_profile = profile.model_copy(update={"education": profile.education.model_copy(update={"certifications": ["CDL-A"]})})
    held = plan_for(held_profile, target)
    assert "Class-A CDL" in missing.daily_actions[2].action
    assert "accepted training" in missing.daily_actions[5].action
    assert "not_confirmed" == missing.credential_paths[0].user_status
    assert "Verify your existing" in held.daily_actions[2].action
    assert "Reuse accepted credential records" in held.daily_actions[5].action
    assert "sample route" in held.daily_actions[15].action
    assert any(link.url == "https://tpr.fmcsa.dot.gov/" for link in missing.daily_actions[5].links)


def test_known_education_and_experience_gaps_get_realistic_routes(profile):
    target = job(description="Bachelor's degree required. Five years of warehouse experience required.")
    actions = plan_for(profile, target).daily_actions
    assert "Bachelor's degree" in actions[4].action and "high school" in actions[1].action
    assert "longer than 30 days" in actions[4].action
    assert "5 years" in actions[8].action and "2 years" in actions[1].action
    assert "trainee" in actions[8].action
    assert "trainee route" in actions[9].action
    assert "takes longer" in actions[28].action


def test_skipped_answers_are_questions_and_zero_experience_is_explicit(profile):
    skipped = UserProfile(location="Oakland", priority_need="work")
    target = job(description="Bachelor's degree required. Two years of warehouse experience required.")
    actions = plan_for(skipped, target).daily_actions
    assert "Ask about accepted equivalents" in actions[4].action
    assert "2 years" in actions[8].action
    assert "0 years" not in actions[1].action
    zero = skipped.model_copy(update={"experience": skipped.experience.model_copy(update={"years": 0})})
    assert "no work experience yet" in plan_for(zero, job()).daily_actions[8].action


def test_preferred_certificate_does_not_force_a_training_delay(profile):
    plan = plan_for(profile, job(description="Forklift certification preferred."))
    assert "preferred" in plan.daily_actions[2].action
    assert "need not delay applying" in plan.daily_actions[9].action
    assert "If you choose optional training" in plan.daily_actions[11].action


def test_uncertain_forklift_role_is_not_misrepresented_as_preferred(profile):
    plan = plan_for(profile, job("Forklift Operator"))
    assert plan.credential_paths[0].requirement_kind == "uncertain"
    assert "Ask if it is needed before starting" in plan.daily_actions[2].action
    assert "marks it preferred" not in " ".join(a.action for a in plan.daily_actions)


def test_certificate_does_not_replace_specific_work_experience(profile):
    certified = profile.model_copy(update={"education": profile.education.model_copy(update={"certifications": ["CDL-A"]})})
    target = job("CDL-A Truck Driver", description="Requirements: Two years of tractor/trailer experience. Class-A CDL required.")
    action = plan_for(certified, target).daily_actions[8].action
    assert "tractor/trailer" in action and "trainee" in action


def test_selected_interim_work_is_conditional_and_named(profile):
    target = job(description="Class-A CDL required.")
    interim = job("Warehouse Assistant").model_copy(update={"job_id": "interim", "company": "Fictional interim employer"})
    plan = build_recommendations(profile, [target, interim], [], data_mode="synthetic",
        selected_job_id="target", selected_interim_job_id="interim").thirty_day_plan
    assert "Warehouse Assistant" in plan.daily_actions[7].action
    assert "Warehouse Assistant" in plan.daily_actions[12].action
    assert "If offered" in plan.daily_actions[12].action


def test_free_text_contact_details_are_not_echoed_into_calendar(profile):
    updated = profile.model_copy(update={"experience": profile.experience.model_copy(update={"text": "I did warehouse work; contact me at private@example.invalid"})})
    assert scan(plan_for(updated, job()).model_dump()) == []


def test_contract_rejects_incomplete_daily_schedule():
    action = DailyPlanAction(action_id="one", day=1, title="Check", action="Check the opening", phase="Get ready")
    with pytest.raises(ValidationError, match="days 1–30"):
        ThirtyDayPlan(target_job_id="target", target_job_title="Example", steps=[], notes=[], daily_actions=[action])


def statuses(target, profile):
    return {check.field: check.status for check in qualification_checks(with_qualification_evidence(target), profile)}


def test_checkboxes_distinguish_met_gap_and_missing_evidence(profile):
    checks = statuses(job(description="High school diploma required. Five years of warehouse experience required."), profile)
    assert checks == {"education": "reported_met", "experience_years": "gap"}
    assert statuses(job(), profile) == {}


def test_preferred_education_does_not_uncheck_met_mandatory_education(profile):
    target = job(description="High school diploma required; bachelor's degree preferred.")
    checks = qualification_checks(with_qualification_evidence(target), profile)
    assert checks[0].status == "reported_met"
    assert any(check.requirement_kind == "preferred" and check.status == "preferred" for check in checks)
    assert statuses(job(description="Bachelor's degree preferred."), profile)["education"] == "preferred"


def test_unknown_education_and_certificate_without_work_experience_stay_unchecked(profile):
    skipped = profile.model_copy(update={"education": profile.education.model_copy(update={"level": "unknown", "certifications": ["forklift"]})})
    target = job(description="High school diploma required. Forklift certification required. Two years of forklift operation experience required.")
    checks = statuses(target, skipped)
    assert checks == {"education": "needs_confirmation", "experience_years": "needs_confirmation", "certification": "reported_met"}


def test_other_roles_are_optional_in_native_ranking_and_cannot_enter_interim_shortlist(profile):
    related = job().model_copy(update={"job_id": "related"})
    other = job("Barista").model_copy(update={"job_id": "other"})
    assert [c.job_id for c in rank_jobs([related, other], profile)] == ["related"]
    cards = rank_jobs([related, other], profile, include_other_roles=True)
    assert {c.job_id: c.matches_reported_role for c in cards} == {"related": True, "other": False}
    plan = build_recommendations(profile, [related, other], [], data_mode="synthetic",
        selected_job_id="other", include_other_roles=True).thirty_day_plan
    assert plan.target_job_title == "Barista"
    assert [option.job_id for option in plan.interim_jobs] == ["related"]


def test_other_roles_keep_city_expiry_and_distance_rules(profile):
    in_area = job("Barista")
    expired = in_area.model_copy(update={"job_id": "expired", "is_expired": True})
    remote = in_area.model_copy(update={"job_id": "remote", "city": "Fresno"})
    assert [c.job_id for c in rank_jobs([in_area, expired, remote], profile, include_other_roles=True)] == ["target"]


def test_flattened_indeed_form_does_not_turn_preferred_experience_into_required(profile):
    target = job("Physical Therapist", description="Experience: clinical: 2 years (Preferred)Ability to Commute: Oakland, CA (Required)Work Location: In person")
    requirements = with_qualification_evidence(target).requirements
    assert len(requirements) == 1
    req = requirements[0]
    assert req.field == "experience_years" and req.kind == "preferred" and req.scope == "clinical"
    assert "Commute" not in req.evidence
    assert statuses(target, profile)["experience_years"] == "preferred"
    assert "Commute" not in plan_for(profile, target).daily_actions[8].action


def test_qualification_heading_and_alternative_experience_routes_are_preserved():
    target = job("Physical Therapist", description="Qualifications Bachelor of Science or advanced degree in Physical Therapy. 3 years of clinical experience without occupational health background OR 2 years with occupational health background.")
    reqs = with_qualification_evidence(target).requirements
    assert any(r.field == "education" and r.value == "bachelor" and r.kind == "required" for r in reqs)
    experience = [r for r in reqs if r.field == "experience_years"]
    assert {r.value for r in experience} == {2, 3}
    assert all(r.kind == "alternative" for r in experience)


def test_company_copy_is_not_appended_to_an_experience_scope():
    target = job(description="Qualifications 3 years of clinical experience OR 2 years with occupational health backgroundConcentra® pioneered the industry in 1979.")
    reqs = with_qualification_evidence(target).requirements
    assert next(r for r in reqs if r.value == 2).scope == "occupational health background"
    assert all(not r.scope or "Concentra" not in r.scope for r in reqs)

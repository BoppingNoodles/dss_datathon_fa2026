from pathlib import Path

import pytest

from src.phoenix.credentials import credential_reported_held, with_credential_evidence
from src.phoenix.ingest import load_records
from src.phoenix.integration import build_recommendations
from src.phoenix.models import Job, RecommendationRequest, Rental, Requirement, UserProfile
from src.phoenix.ranking import rank_jobs


@pytest.fixture
def inputs():
    profile = UserProfile.model_validate_json(Path("examples/profile.synthetic.json").read_text())
    jobs = load_records(Path("examples/jobs.synthetic.jsonl"), Job)
    rentals = load_records(Path("examples/rentals.synthetic.jsonl"), Rental)
    return profile, jobs, rentals


def target_with_cdl(job):
    return job.model_copy(update={"title":"Warehouse / CDL-A Driver",
        "description":"Warehouse cargo work. Certifications: Class-A CDL with required endorsements.",
        "requirements":[]})


def test_no_automatic_target_or_plan_before_user_selection(inputs):
    profile, jobs, rentals = inputs
    response = build_recommendations(profile,jobs,rentals,data_mode="synthetic")
    assert response.selected_job_id is None and response.thirty_day_plan is None
    assert all(j.selectable and not j.is_selected for j in response.jobs)


def test_selecting_missing_credential_job_builds_specific_path_and_keeps_it_selectable(inputs):
    profile,jobs,rentals=inputs
    target=target_with_cdl(jobs[1])
    response=build_recommendations(profile,[jobs[0],target],rentals,data_mode="synthetic",selected_job_id=target.job_id)
    card=next(c for c in response.jobs if c.job_id==target.job_id)
    assert card.selectable and card.is_selected
    assert "work toward" in card.credential_summary
    path=response.thirty_day_plan.credential_paths[0]
    assert path.credential=="Class-A CDL" and path.requirement_kind=="required"
    assert path.user_status=="not_confirmed" and path.completion_within_30_days=="not_guaranteed"
    assert any("tpr.fmcsa.dot.gov" in link.url for link in path.links)


def test_generic_experience_gap_does_not_disable_selection(inputs):
    profile,jobs,rentals=inputs
    target=jobs[1].model_copy(update={"requirements":[Requirement(field="experience_years",value=5,
        kind="required",evidence="Five years of warehouse experience required.")]})
    response=build_recommendations(profile,[jobs[0],target],rentals,data_mode="synthetic",selected_job_id=target.job_id)
    assert next(c for c in response.jobs if c.job_id==target.job_id).fit_tier=="qualification_gap"
    assert any(s.step_id=="experience-route" for s in response.thirty_day_plan.steps)


def test_preferred_certificate_does_not_force_waiting_before_application(inputs):
    profile,jobs,rentals=inputs
    target=jobs[1].model_copy(update={"description":"Warehouse work. Forklift certification preferred.","requirements":[]})
    response=build_recommendations(profile,[jobs[0],target],rentals,data_mode="synthetic",selected_job_id=target.job_id)
    assert response.thirty_day_plan.credential_paths[0].requirement_kind=="preferred"
    assert any(s.step_id=="apply-target-when-confirmed" for s in response.thirty_day_plan.steps)


def test_forklift_plan_includes_practical_training_and_employer_evaluation(inputs):
    profile,jobs,rentals=inputs
    target=jobs[1].model_copy(update={"description":"Warehouse work. Forklift certification required.","requirements":[]})
    response=build_recommendations(profile,[jobs[0],target],rentals,data_mode="synthetic",selected_job_id=target.job_id)
    text=" ".join(s.action for s in response.thirty_day_plan.steps)
    assert "online-only card is not enough" in text
    assert "workplace evaluation" in text


def test_negated_requirement_is_not_a_required_credential(inputs):
    _,jobs,_=inputs
    job=jobs[0].model_copy(update={"description":"No forklift certification required. Warehouse work.","requirements":[]})
    assert not with_credential_evidence(job).requirements


def test_aliases_reuse_reported_credentials_instead_of_repeating_training(inputs):
    profile,jobs,rentals=inputs
    profile=profile.model_copy(update={"education":profile.education.model_copy(update={"certifications":["CDL-A"]})})
    assert credential_reported_held("Class-A CDL",profile)
    target=target_with_cdl(jobs[1])
    response=build_recommendations(profile,[target],rentals,data_mode="synthetic",selected_job_id=target.job_id)
    assert response.thirty_day_plan.credential_paths[0].user_status=="reported_held"
    assert not any(s.step_id=="credential-1-3" for s in response.thirty_day_plan.steps)


def test_interim_options_exclude_target_and_unconfirmed_required_credentials(inputs):
    profile,jobs,rentals=inputs
    target=target_with_cdl(jobs[1])
    second=jobs[2].model_copy(update={"description":"Warehouse work. A valid driver's license is required.","requirements":[]})
    response=build_recommendations(profile,[jobs[0],target,second],rentals,data_mode="synthetic",selected_job_id=target.job_id)
    options=response.thirty_day_plan.interim_jobs
    assert [o.job_id for o in options]==[jobs[0].job_id]
    assert "confirm" in options[0].credential_summary


def test_interim_pay_is_used_for_its_housing_scenario_not_future_target_pay(inputs):
    profile,jobs,rentals=inputs
    target=target_with_cdl(jobs[1])
    response=build_recommendations(profile,[jobs[0],target],rentals,data_mode="synthetic",selected_job_id=target.job_id,
        selected_interim_job_id=jobs[0].job_id,scenario_hours_per_week=40,scenario_weeks_per_year=52)
    assert response.housing_income_stage=="interim_job_scenario"
    assert response.housing_income_job_id==jobs[0].job_id
    assert response.housing_comparisons[0]['annual_gross_pay_scenario']['minimum']==41600
    assert response.thirty_day_plan.interim_jobs[0].is_selected


def test_invalid_interim_selection_rejected(inputs):
    profile,jobs,rentals=inputs
    target=target_with_cdl(jobs[1])
    with pytest.raises(ValueError,match="Select a target"):
        build_recommendations(profile,jobs,rentals,data_mode="synthetic",selected_interim_job_id=jobs[0].job_id)
    with pytest.raises(ValueError,match="displayed interim"):
        build_recommendations(profile,[jobs[0],target],rentals,data_mode="synthetic",selected_job_id=target.job_id,
                              selected_interim_job_id=target.job_id)


def test_plan_dependencies_reference_existing_steps(inputs):
    profile,jobs,rentals=inputs
    target=target_with_cdl(jobs[1])
    plan=build_recommendations(profile,[jobs[0],target],rentals,data_mode="synthetic",selected_job_id=target.job_id).thirty_day_plan
    ids={s.step_id for s in plan.steps}
    assert all(set(s.depends_on)<=ids for s in plan.steps)
    assert all(1<=s.day_start<=s.day_end<=30 for s in plan.steps)


def test_plain_forklift_operator_is_not_presented_as_verified_no_training_needed(inputs):
    profile,jobs,_=inputs
    job=jobs[0].model_copy(update={"title":"Clamp Forklift Operator","description":"Warehouse operations.","requirements":[]})
    card=rank_jobs([job],profile)[0]
    assert any(r.kind=="uncertain" and "forklift" in str(r.value).lower() for r in card.requirements)


def test_partial_credential_hint_does_not_imply_all_qualifications_verified(inputs):
    profile,jobs,_=inputs
    job=jobs[0].model_copy(update={"requirements":[],"description":"Warehouse role. Forklift certification preferred."})
    card=rank_jobs([job],profile)[0]
    assert card.fit_tier=="possible_match"
    assert any("Structured requirements not supplied" in u for u in card.unknowns)


def test_request_envelope_requires_target_for_interim_selection(inputs):
    profile,_,_=inputs
    with pytest.raises(ValueError,match="Select a target"):
        RecommendationRequest(profile=profile,selected_interim_job_id="example-a")

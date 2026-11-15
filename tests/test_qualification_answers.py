from src.phoenix.integration import build_recommendations
from src.phoenix.models import Job, UserProfile
from src.phoenix.qualifications import qualification_checks, with_qualification_evidence
from src.recommend.certificates import credentials_in_jobs


def target(job_id="target"):
    return Job(job_id=job_id, title="Warehouse / CDL-A Driver", company="Fictional", city="Oakland",
        location_text="Oakland", description="High school diploma required. Class-A CDL required.")


def profile(**updates):
    return UserProfile.model_validate({"location": "Oakland", "priority_need": "work",
        "experience": {"skills": ["warehouse"], "years": 2},
        "education": {"level": "high_school", "no_certifications": True}, **updates})


def test_specific_checks_and_job_scoped_answers_drive_credential_plan():
    job = with_qualification_evidence(target())
    checks = qualification_checks(job, profile())
    assert {c.label for c in checks} == {"High school diploma or GED", "Class-A CDL"}
    credential = next(c for c in checks if c.field == "certification")
    assert credential.status == "gap"
    answered = profile(qualification_answers={job.job_id: {credential.key: True}})
    response = build_recommendations(answered, [job, target("another")], [], data_mode="synthetic", selected_job_id="target")
    assert response.thirty_day_plan.credential_paths[0].user_status == "reported_held"
    assert "Verify your existing" in response.thirty_day_plan.daily_actions[2].action
    assert answered.education.certifications == [] and answered.education.no_certifications
    another = next(c for c in response.jobs if c.job_id == "another")
    assert next(c for c in another.qualification_checks if c.field == "certification").status == "gap"


def test_unchecking_an_inferred_degree_changes_only_that_job_and_its_plan():
    job = with_qualification_evidence(target())
    diploma = next(c for c in qualification_checks(job, profile()) if c.field == "education")
    answered = profile(qualification_answers={job.job_id: {diploma.key: False}})
    result = build_recommendations(answered, [job], [], data_mode="synthetic", selected_job_id="target")
    check = next(c for c in result.jobs[0].qualification_checks if c.key == diploma.key)
    assert check.status == "gap"
    assert "accepted equivalents" in result.thirty_day_plan.daily_actions[4].action
    assert answered.education.level == "high_school"


def test_unknown_answer_ids_cannot_confirm_any_requirement():
    job = with_qualification_evidence(target())
    answered = profile(qualification_answers={"target": {"not-a-requirement": True}})
    assert next(c for c in qualification_checks(job, answered) if c.field == "certification").status == "gap"


def test_confirmed_role_specific_experience_updates_relevance_for_that_job_only():
    job = with_qualification_evidence(target().model_copy(update={"title": "Equipment Technician",
        "description": "Requirements: Two years of service technician experience."}))
    experience = next(check for check in qualification_checks(job, profile()) if check.field == "experience_years")
    answered = profile(qualification_answers={job.job_id: {experience.key: True}})
    from src.phoenix.ranking import rank_jobs
    card = rank_jobs([job], answered)[0]
    assert card.matches_reported_role is True
    assert "reported experience for this role" in card.matched_skills
    assert answered.experience.skills == ["warehouse"]


def test_certificate_catalog_comes_from_actual_mentions_and_deduplicates_per_posting():
    jobs = [target(), target("second").model_copy(update={"description": "Class-A CDL preferred. Class-A CDL required. ServSafe certification is a plus."})]
    catalog = {item["label"]: item["posting_count"] for item in credentials_in_jobs(jobs)}
    assert catalog == {"Class-A CDL": 2, "ServSafe certification": 1}
    assert "Security guard card" not in catalog


def test_public_none_selection_is_mutually_exclusive_and_answers_are_boolean(client):
    request = {"location": "Oakland", "priority_need": "work"}
    assert client.get("/job-certificates").status_code == 200
    bad = client.post("/recommendations", json={**request, "education": {"no_credentials": True, "credentials": ["CDL-A"]}})
    assert bad.status_code == 422
    bad = client.post("/recommendations", json={**request, "qualification_answers": {"target": {"req": "yes"}}})
    assert bad.status_code == 422


def test_daily_actions_stay_short_and_use_plain_steps():
    result = build_recommendations(profile(), [target()], [], data_mode="synthetic", selected_job_id="target")
    assert len(result.thirty_day_plan.daily_actions) == 30
    assert all(len(action.action.split()) <= 60 for action in result.thirty_day_plan.daily_actions)
    assert all(len(action.title.split()) <= 6 for action in result.thirty_day_plan.daily_actions)


def test_onboarding_autofills_matching_diploma_credentials_and_scoped_experience():
    job = with_qualification_evidence(target().model_copy(update={"title": "Warehouse / CDL-A Driver / Forklift Operator",
        "description": "High school diploma required. Class-A CDL required. Experience: 1 year of verifiable tractor/trailer experience (Candidates with less than 1 year experience may be eligible for training)."}))
    answered = profile(experience={"skills": ["warehouse", "tractor/trailer"], "years": 2},
        education={"level": "high_school", "certifications": ["CDL-A", "forklift"]})
    checks = qualification_checks(job, answered)
    assert len(checks) == 4
    assert all(check.status == "reported_met" for check in checks)
    assert any(check.requirement_kind == "uncertain" for check in checks)
    assert any(check.requirement_kind == "alternative" for check in checks)


def test_common_onboarding_credential_aliases_autofill_specific_posting_checks():
    job = with_qualification_evidence(target().model_copy(update={"title": "Barista",
        "description": "ServSafe certification required. CPR certification preferred."}))
    answered = profile(education={"level": "high_school", "certifications": ["ServSafe", "CPR"]})
    assert all(check.status == "reported_met" for check in qualification_checks(job, answered))


def test_reported_clinical_scope_can_autofill_without_inventing_it_from_a_certificate():
    job = with_qualification_evidence(target().model_copy(update={"title": "Clinical Assistant",
        "description": "Requirements: Two years of clinical experience."}))
    answered = profile(experience={"text": "Clinical experience", "years": 2})
    assert qualification_checks(job, answered)[0].status == "reported_met"
    certificate_only = profile(education={"level": "high_school", "certifications": ["CPR"]})
    assert qualification_checks(job, certificate_only)[0].status == "needs_confirmation"

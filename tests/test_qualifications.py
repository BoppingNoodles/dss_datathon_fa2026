from pathlib import Path

import pytest

from src.audit.privacy_check import scan
from src.phoenix.integration import build_recommendations
from src.phoenix.models import Job, Requirement, UserProfile
from src.phoenix.qualifications import experience_assessment, with_qualification_evidence
from src.phoenix.ranking import rank_jobs


@pytest.fixture
def profile():
    return UserProfile.model_validate({"location":"Oakland", "priority_need":"work",
        "experience":{"skills":["warehouse", "inventory"], "years":2},
        "education":{"level":"high_school"}})


def job(description, **updates):
    return Job(job_id="test-job",title="Warehouse Associate",company="Fictional employer",
               location_text="Oakland, CA",city="Oakland",description=description).model_copy(update=updates)


@pytest.mark.parametrize("description,field,value,kind",[
    ("A bachelor's degree is required.","education","bachelor","required"),
    ("Minimum qualifications: High school diploma or GED.","education","high_school","required"),
    ("Requirements: High School Diploma or equivalent education level.","education","high_school","required"),
    ("EDUCATION High School Diploma or equivalent. REQUIREMENTS Two years of warehouse experience.","education","high_school","required"),
    ("High school diploma required; bachelor's degree preferred.","education","bachelor","preferred"),
    ("Qualifications: Three years of warehouse experience preferred.","experience_years",3,"preferred"),
    ("At least 3–5 years of warehouse experience required.","experience_years",3,"required"),
    ("Requirements: 18 months of warehouse experience.","experience_years",1.5,"required"),
    ("Experience: 2 years in warehouse operations.","experience_years",2,"required"),
    ("EXPERIENCE 3 years.","experience_years",3,"required"),
    ("Bachelor's degree or equivalent experience required.","education","bachelor","alternative"),
    ("Requirements: Bachelor's or master's degree.","education","bachelor","alternative"),
    ("Requirements: Bachelor's or master's degree.","education","master","alternative"),
    ("Experience: 1 year of verifiable tractor/trailer experience (Candidates with less than 1 year experience may be eligible for training).", "experience_years",1,"alternative"),
])
def test_explicit_values_keep_their_qualification_kind(description,field,value,kind):
    requirements=with_qualification_evidence(job(description)).requirements
    matches=[r for r in requirements if r.field==field and r.value==value]
    assert matches, requirements
    assert all(r.kind==kind for r in matches)
    assert all(r.evidence and r.source=="posting_qualification_rules_v1" for r in matches)


@pytest.mark.parametrize("description",[
    "No bachelor's degree required. No prior warehouse experience required.",
    "A bachelor's degree is not required. Two years of warehouse experience is not required.",
    "Requirements: Zero to two years of warehouse experience.",
    "About us: We have 25 years of warehouse experience. Benefits: Tuition assistance for a bachelor's degree.",
    "Salary is based on 3 years of experience. Bachelor's degree tuition reimbursement available.",
    "Requirements: Must be at least 18 years of age. Warehouse experience preferred.",
    "Requirements: Must be 21 years old with warehouse experience preferred.",
    "Requirements: Must lift 50 pounds. About Us With over a century of experience, we serve customers nationwide.",
])
def test_negation_zero_minimum_and_company_or_benefit_text_do_not_create_required_gaps(description,profile):
    enriched=with_qualification_evidence(job(description))
    assert not any(r.kind=="required" for r in enriched.requirements),enriched.requirements
    assert not rank_jobs([enriched],profile)[0].qualification_gaps


def test_required_degree_and_years_are_compared_with_answers(profile):
    candidate=job("Minimum qualifications: Bachelor's degree required. At least five years of warehouse experience required.")
    card=rank_jobs([candidate],profile)[0]
    assert card.fit_tier=="qualification_gap"
    assert any("bachelor" in gap for gap in card.qualification_gaps)
    assert any("5 years" in gap for gap in card.qualification_gaps)
    assert card.selectable


def test_skipped_answers_stay_unknown_instead_of_becoming_negative_labels(profile):
    skipped=profile.model_copy(update={"education":profile.education.model_copy(update={"level":"unknown"}),
        "experience":profile.experience.model_copy(update={"years":None})})
    card=rank_jobs([job("Bachelor's degree required. Five years of warehouse experience required.")],skipped)[0]
    assert card.fit_tier=="possible_match" and not card.qualification_gaps
    assert any("Education" in note for note in card.unknowns)
    assert any("Years" in note for note in card.unknowns)


def test_manual_or_model_requirements_remain_authoritative():
    manual=Requirement(field="education",value="high_school",kind="preferred",evidence="Manually reviewed equivalent pathway.",source="manual")
    candidate=job("Bachelor's degree required.",requirements=[manual])
    assert with_qualification_evidence(candidate).requirements==[manual]


def test_preferred_higher_degree_does_not_weaken_high_school_minimum():
    requirements=with_qualification_evidence(job("Requirements: High school diploma or GED required, bachelor's degree preferred.")).requirements
    assert any(r.value=="high_school" and r.kind=="required" for r in requirements)
    assert any(r.value=="bachelor" and r.kind=="preferred" for r in requirements)


def test_generic_warehouse_experience_does_not_match_a_forklift_repair_technician(profile):
    specialist=job("POSITION QUALIFICATIONS EDUCATION High School Diploma. REQUIREMENTS 2+ years of experience in a service technician role. Previous experience with hydraulics and computer diagnostics.",title="Forklift Technician")
    assert rank_jobs([specialist],profile)==[]
    mechanic=profile.model_copy(update={"experience":profile.experience.model_copy(update={"skills":["service technician","hydraulics"]})})
    card=rank_jobs([specialist],mechanic)[0]
    assert not card.qualification_gaps
    assert any(r.scope and "service technician" in r.scope for r in card.requirements)


def test_negated_repair_experience_does_not_activate_the_repair_family(profile):
    negative=profile.model_copy(update={"experience":profile.experience.model_copy(update={"text":"No forklift repair experience, but I have warehouse experience."})})
    assert rank_jobs([job("Requirements: Two years of service technician experience.",title="Forklift Technician")],negative)==[]


def test_specific_experience_is_not_satisfied_by_equal_generic_years(profile):
    req=Requirement(field="experience_years",value=2,kind="required",scope="service technician",evidence="2 years in a service technician role required.")
    status,explanation=experience_assessment(req,profile)
    assert status=="unknown" and "not established" in explanation


def test_age_in_same_clause_is_not_read_as_work_experience():
    requirements=with_qualification_evidence(job("Requirements: Must be at least 18 years of age and have warehouse experience.")).requirements
    assert not any(r.field=="experience_years" and r.value==18 for r in requirements)


def test_trainee_waiver_is_not_a_second_required_experience_amount():
    requirements=with_qualification_evidence(job("Experience: 1 year of verifiable tractor/trailer experience (Candidates with less than 1 year experience may be eligible for training).")).requirements
    experience=[r for r in requirements if r.field=="experience_years"]
    assert len(experience)==1 and experience[0].kind=="alternative"


def test_preferred_degree_or_training_alternative_does_not_disqualify(profile):
    candidate=job("Bachelor's degree or equivalent experience required. Experience: 1 year of tractor/trailer experience (Candidates with less than 1 year experience may be eligible for training).")
    card=rank_jobs([candidate],profile)[0]
    assert not card.qualification_gaps
    assert all(r.kind=="alternative" for r in card.requirements)


def test_interim_options_exclude_unconfirmed_required_experience_and_keep_target_selectable(profile):
    target=job("Five years of warehouse experience required.",job_id="target")
    unrelated_experience=job("Requirements: Two years of commercial driving experience.",job_id="driving")
    insufficient_years=job("Three years of warehouse experience required.",job_id="senior")
    suitable=job("Requirements: High school diploma or GED.",job_id="interim")
    response=build_recommendations(profile,[target,unrelated_experience,insufficient_years,suitable],[],data_mode="synthetic",selected_job_id="target")
    assert {option.job_id for option in response.thirty_day_plan.interim_jobs}=={"interim"}
    assert next(card for card in response.jobs if card.job_id=="target").selectable
    assert any(step.step_id=="experience-route" for step in response.thirty_day_plan.steps)


def test_rules_do_not_mutate_cached_normalized_jobs(profile):
    original=job("High school diploma required. Two years of warehouse experience required.")
    rank_jobs([original],profile)
    assert original.requirements==[]


def test_public_requirement_evidence_omits_contact_emails(profile):
    card=rank_jobs([job("Requirements: Bachelor's degree required, contact recruiter@example.invalid. Two years of warehouse experience required.")],profile)[0]
    assert not scan(card.model_dump())
    assert any("[contact omitted]" in req.evidence for req in card.requirements)


def test_role_matching_does_not_turn_a_certificate_into_work_experience(profile):
    certified=profile.model_copy(update={"education":profile.education.model_copy(update={"certifications":["Forklift repair certificate"]})})
    assert rank_jobs([job("Two years of service technician experience required.",title="Forklift Technician")],certified)==[]


def test_forklift_certificate_and_warehouse_years_do_not_prove_forklift_work_experience(profile):
    certified=profile.model_copy(update={"education":profile.education.model_copy(update={"certifications":["forklift"]})})
    requirement=Requirement(field="experience_years",value=1,kind="required",scope="forklift operation",evidence="One year of forklift operation experience required.")
    assert experience_assessment(requirement,certified)[0]=="unknown"
    experienced=certified.model_copy(update={"experience":certified.experience.model_copy(update={"skills":["warehouse","forklift"]})})
    assert experience_assessment(requirement,experienced)[0]=="reported_match"


def test_generic_driving_does_not_prove_tractor_trailer_experience(profile):
    driving=profile.model_copy(update={"experience":profile.experience.model_copy(update={"skills":["driving"]})})
    requirement=Requirement(field="experience_years",value=1,kind="required",scope="tractor/trailer",evidence="One year of tractor/trailer experience required.")
    assert experience_assessment(requirement,driving)[0]=="unknown"

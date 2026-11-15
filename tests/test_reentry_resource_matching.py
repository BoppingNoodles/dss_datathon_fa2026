"""Task joins use service evidence, explicit types, locality and user intent."""
from datetime import date

from src.recommend.reentry_domain import Recommendation, ReentryProfile, PlanTask
from src.recommend.reentry_resources import attach_resources, resource_types
from src.recommend.reentry_planner import generate_plan, candidate_referrals, verified_referrals


def profile():
    return ReentryProfile.model_validate(dict(profileId="fictional-matching", location={"city": "Oakland"}, release={"status": "post_release"},
        housing={"status": "no_confirmed_housing"}, employment={"status": "unemployed", "preferredJobTypes": ["Warehouse"]},
        barriers={"hasGovernmentId": False, "hasTransportation": False}, appointmentStatus="no"))


def resource(id, type, *, mode="service", title="Fictional source", city="Oakland", details=None):
    return Recommendation(id=id, category="job" if mode == "job" else "housing" if mode in {"temporary_housing", "long_term_area"} else "service", mode=mode,
        title=title, description=type, source="fictional source", score=.7, resourceType=type,
        location={"city": city}, serviceEvidence={type: f"Fictional source category: {type}; service unconfirmed."}, details=details or {})


def task(types, title="Find assistance"):
    return PlanTask(id="fictional-task", title=title, description="Check the source.", category="other", priority="high", rationale="Fictional need", allowedResourceTypes=types)


def test_official_food_referral_precedes_category_only_candidates(synthetic):
    today = date(2026, 11, 14)
    rows = candidate_referrals("food", {"location": "Oakland", "priority_need": "food"}, synthetic["candidates"], synthetic["refs"], source="real", today=today)
    assert rows[0].resource_id == "manual:accfb-food-helpline"
    assert rows[0].verification == "verified_general_service"
    assert rows[0].phone == "510-635-3663"
    assert rows[0].source_url == "https://www.accfb.org/about-us/food-distribution/"
    assert "walk-in pantry" in rows[0].scope
    assert not verified_referrals("Richmond", "food", today)
    assert not verified_referrals("Oakland", "food", date(2026, 11, 13))


def test_transport_rejects_reference_points_and_unrelated_organizations():
    reference = resource("ref", "public_transit", title="City area reference", details={"geographicReferenceOnly": True})
    transit = resource("station", "public_transit", title="Actual station", details={"category": "Train station"})
    community = resource("generic", "community_support")
    output = attach_resources(task(["public_transit", "transportation_assistance"]), profile(), [reference, transit, community])
    assert output.relatedRecommendationIds == ["station"]
    assert "Fictional source category" in output.resourceMatchReasons["station"]
    assert resource_types("Geographic point of interest") == ["community_support"]
    assert resource_types("Bus stop") == ["public_transit"]


def test_temporary_housing_cannot_receive_zillow_area_and_application_cannot_receive_org():
    job = resource("job:one", "job_posting", mode="job", details={"jobId": "one"})
    rent = resource("area", "rental_market", mode="long_term_area")
    housing = resource("provider", "housing_assistance", mode="temporary_housing")
    organization = resource("organization", "community_support")
    tasks, _ = generate_plan(profile(), [job, rent, housing, organization], ["job:one"], [], [], today=date(2026, 11, 14))
    immediate = next(t for t in tasks if t.id == "reentry:housing-now")
    assert immediate.relatedRecommendationIds == ["provider"] and "rental_market" not in immediate.allowedResourceTypes
    application = next(t for t in tasks if t.id == "reentry:job-action:one")
    assert application.relatedRecommendationIds == ["job:one"]
    assert application.allowedResourceTypes == ["job_posting"]


def test_training_rejects_wrong_specialty_and_keeps_posting_as_context():
    job = resource("job:one", "job_posting", mode="job", title="Warehouse forklift operator", details={"jobId": "one", "qualificationChecks": [{"key": "forklift", "field": "certification", "status": "gap", "requirement_kind": "required", "label": "Forklift certification", "detail": "Listed mandatory forklift certification is missing."}]})
    job.sourceUrl = "https://example.test/job"
    health = resource("health-course", "workforce_training", title="Phlebotomy Training")
    forklift = resource("forklift-course", "workforce_training", title="Forklift Training")
    tasks, _ = generate_plan(profile(), [job, health, forklift], [job.id], [], [], today=date(2026, 11, 14))
    preparation = next(t for t in tasks if t.id == "training:one:forklift")
    assert preparation.relatedRecommendationIds == ["forklift-course"]
    assert preparation.allowedResourceTypes == ["workforce_training"]
    assert preparation.referenceLinks[0]["url"] == job.sourceUrl
    assert preparation.status == "blocked"  # Confirm employer's route first.


def test_no_evidence_or_out_of_area_has_honest_empty_state():
    no_evidence = resource("unknown", "identification_assistance")
    no_evidence.serviceEvidence = {}
    elsewhere = resource("outside", "identification_assistance", details={"serviceAreaCities": ["Los Angeles"]})
    output = attach_resources(task(["identification_assistance"]), profile(), [no_evidence, elsewhere])
    assert output.relatedRecommendationIds == [] and output.resourceEmptyState


def test_real_transit_referrals_preserve_actual_category_and_city(synthetic):
    # Synthetic fixtures run through the same Places taxonomy; no coordinate
    # reference table is ever promoted into a service recommendation.
    refs = candidate_referrals("transportation", {"location": "Oakland", "priority_need": "transportation"}, synthetic["candidates"], synthetic["refs"], source="synthetic", today=date(2026, 11, 14))
    assert refs
    assert all("public_transit" in r.resource_types or "transportation_assistance" in r.resource_types for r in refs)
    assert all(r.category_evidence and r.city for r in refs)


def test_cpr_requirement_does_not_link_forklift_or_phlebotomy_course():
    cpr = task(["workforce_training"], "Find preparation for CPR certification")
    cpr.referenceLinks = [{"label": "Source job: Warehouse assistant", "url": "https://example.test/job"}]
    choices = [resource("forklift", "workforce_training", title="Forklift Training"), resource("phlebotomy", "workforce_training", title="Phlebotomy School"), resource("cpr", "workforce_training", title="CPR and First Aid Training")]
    assert attach_resources(cpr, profile(), choices).relatedRecommendationIds == ["cpr"]

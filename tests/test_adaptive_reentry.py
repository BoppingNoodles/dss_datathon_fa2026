"""Stateful acceptance cases A–E and integration with real saved NLP weights."""
from datetime import date, timedelta
from copy import deepcopy

import pytest

from src.audit.privacy_check import scan
from src.recommend.reentry_domain import ReentryProfile, Recommendation, PhoenixSession, UserEvent, apply_event
from src.recommend.reentry_planner import planned_session
from src.recommend.reentry_matching import model_flags, _job_recommendations

TODAY = date(2026, 11, 14)


def profile(**changes):
    data = dict(profileId="fictional-demo", location={"city": "Oakland"}, release={"status": "post_release", "date": "2026-10-31"},
        housing={"status": "stable"}, employment={"status": "unemployed", "preferredJobTypes": ["Warehouse"], "skills": ["Warehouse"],
        "experienceYears": 2, "educationLevel": "high_school_or_ged", "noCertifications": True},
        barriers={"hasGovernmentId": True, "hasTransportation": True, "hasPhoneAccess": True, "hasInternetAccess": True},
        supportNeeds=["employment"], appointmentStatus="no")
    data.update(changes)
    return ReentryProfile.model_validate(data)


def resources():
    return [Recommendation(id="job:one", category="job", mode="job", title="Warehouse assistant", description="Warehouse duties", source="fixture", score=.8,
        details={"jobId": "one", "requirements": [{"label": "certification_required", "source": "model_prediction", "status": "unknown"}], "qualificationChecks": []}),
        Recommendation(id="job:two", category="job", mode="job", title="Picker", description="Picking duties", source="fixture", score=.7, details={"jobId": "two"}),
        *[Recommendation(id=f"provider:{i}", category="housing", mode="temporary_housing", title=f"Fictional provider {i}", description="Housing assistance", source="fixture", score=.6,
            verificationStatus="verified", serviceEvidence={"housing_assistance": "Fictional source explicitly offers housing assistance."},
            details={"resourceId": str(i), "barrier": "housing"}) for i in (1, 2)]]


def initial(p, selected=()):
    old = PhoenixSession(profile=p, recommendations=resources(), selectedRecommendationIds=list(selected))
    return planned_session(p, resources(), old, None, today=TODAY, top_job_ids=["job:one", "job:two"], warnings=[])


def update(state, kind, payload):
    event = UserEvent(type=kind, payload=payload)
    p, previous = apply_event(state.profile, state, event)
    return planned_session(p, previous.recommendations, previous, event, today=TODAY, top_job_ids=["job:one", "job:two"], warnings=[])


def test_declared_task_results_update_situation_without_claiming_stable_housing():
    state = initial(profile(housing={"status": "no_confirmed_housing"}, supportNeeds=["food"],
        barriers={"hasGovernmentId": True, "hasTransportation": False, "hasFoodAccess": False}))
    original = state.model_dump()
    housing = update(state, "task_status", {"taskId": "reentry:housing-now", "status": "completed", "outcome": "housing_arranged"})
    assert housing.profile.housing.status == "temporary"
    assert housing.profile.housing.temporaryHousingEndDate is None
    assert state.model_dump() == original
    food_step = next(t for t in housing.tasks if t.completionOutcome == "food_secured")
    food = update(housing, "task_status", {"taskId": food_step.id, "status": "completed", "outcome": "food_secured"})
    result = update(food, "task_status", {"taskId": "reentry:transportation", "status": "completed", "outcome": "transportation_arranged"})
    assert result.profile.barriers.hasFoodAccess is True
    assert result.profile.barriers.hasTransportation is True
    assert all(next(t for t in result.tasks if t.id == key).status == "completed" for key in ("reentry:housing-now", food_step.id, "reentry:transportation"))
    reopened = update(result, "task_status", {"taskId": "reentry:transportation", "status": "not_started"})
    assert reopened.profile.barriers.hasTransportation is True


def test_result_confirmation_can_catch_up_an_already_completed_search():
    state = initial(profile(housing={"status": "no_confirmed_housing"}))
    searched = update(state, "task_status", {"taskId": "reentry:housing-now", "status": "completed"})
    assert searched.profile.housing.status == "no_confirmed_housing"
    result = update(searched, "task_status", {"taskId": "reentry:housing-now", "status": "completed", "outcome": "housing_arranged"})
    assert result.profile.housing.status == "temporary"
    assert all(t.status == "completed" for t in result.tasks if t.id.startswith("housing:arrangement-check:"))
    with pytest.raises(ValueError, match="result"):
        update(state, "task_status", {"taskId": "reentry:housing-now", "status": "completed", "outcome": "food_secured"})


def test_reported_access_completes_matching_needs_and_a_food_setback_keeps_history():
    state = initial(profile(housing={"status": "no_confirmed_housing"}, supportNeeds=["food"],
        barriers={"hasGovernmentId": True, "hasTransportation": False, "hasFoodAccess": False}))
    next_profile = state.profile.model_dump(mode="json")
    next_profile["housing"]["status"] = "temporary"
    next_profile["barriers"].update(hasFoodAccess=True, hasTransportation=True)
    result = update(state, "profile_updated", {"profile": next_profile})
    assert all(t.status == "completed" for t in result.tasks if t.completionOutcome in {"food_secured", "transportation_arranged"})
    previous_food = next(t for t in result.tasks if t.completionOutcome == "food_secured")
    next_profile["barriers"]["hasFoodAccess"] = False
    setback = update(result, "profile_updated", {"profile": next_profile})
    assert next(t for t in setback.tasks if t.id == previous_food.id).status == "completed"
    assert any(t.completionOutcome == "food_secured" and t.status == "not_started" for t in setback.tasks)


def test_three_preferences_are_mutually_exclusive_and_restore_dismissed_options():
    state = initial(profile())
    selected = update(state, "resource_status", {"recommendationId": "job:one", "status": "selected"})
    assert "job:one" in selected.selectedRecommendationIds
    interested = update(selected, "resource_status", {"recommendationId": "job:one", "status": "saved"})
    assert "job:one" not in interested.selectedRecommendationIds
    dismissed = update(interested, "resource_status", {"recommendationId": "job:one", "status": "dismissed"})
    assert "job:one" in dismissed.dismissedRecommendationIds
    restored = update(dismissed, "resource_status", {"recommendationId": "job:one", "status": "selected"})
    assert "job:one" in restored.selectedRecommendationIds
    assert "job:one" not in restored.dismissedRecommendationIds
    assert restored.profile.employment.status == "unemployed"


def test_interested_job_removes_the_selected_calendar_target_through_api(client):
    created = client.post("/recommendations", json={"profile": profile().model_dump(mode="json")})
    assert created.status_code == 200
    state = created.json()["phoenix_session"]
    job = next(r for r in state["recommendations"] if r["category"] == "job")
    selected = client.post("/recommendations", json={"phoenix_session": state,
        "user_event": {"type": "resource_status", "payload": {"recommendationId": job["id"], "status": "selected"}}})
    assert selected.status_code == 200
    assert selected.json()["selected_job_id"] is not None
    interested = client.post("/recommendations", json={"phoenix_session": selected.json()["phoenix_session"], "selected_job_id": None,
        "user_event": {"type": "resource_status", "payload": {"recommendationId": job["id"], "status": "saved"}}})
    assert interested.status_code == 200
    assert job["id"] not in interested.json()["phoenix_session"]["selectedRecommendationIds"]
    assert interested.json()["selected_job_id"] is None


def test_a_housing_crisis_precedes_jobs_without_id_assumption():
    p = profile(housing={"status": "no_confirmed_housing"}, barriers={"hasGovernmentId": True, "hasTransportation": False})
    state = initial(p)
    assert state.tasks[0].id == "reentry:housing-now" and state.tasks[0].priority == "critical"
    assert state.tasks[0].deadline is None  # Urgency is not a fabricated user deadline.
    assert "reentry:transportation" in {t.id for t in state.tasks}
    assert "reentry:identification" not in {t.id for t in state.tasks}
    assert any(r.mode == "temporary_housing" for r in state.recommendations)
    after_action = update(state, "task_status", {"taskId": "reentry:housing-now", "status": "completed"})
    assert after_action.profile.housing.status == "no_confirmed_housing"
    followup = next(t for t in after_action.tasks if t.id.startswith("housing:arrangement-check:"))
    assert followup.priority == "critical" and followup.status == "not_started"
    assert next(t for t in after_action.tasks if t.id == "reentry:housing-now").status == "completed"


def test_b_employment_and_model_preparation_without_emergency_housing():
    state = initial(profile(), ["job:one"])
    assert any(t.id == "reentry:model-check:one:certification_required" for t in state.tasks)
    assert not any(t.id == "reentry:housing-now" for t in state.tasks)
    assert any(t.category == "employment" for t in state.tasks)


def test_c_two_jobs_new_employment_then_housing_deadline_preserve_history():
    state = initial(profile(housing={"status": "temporary", "temporaryHousingEndDate": "2026-12-15"}), ["job:one", "job:two"])
    assert {"reentry:job-review:one", "reentry:job-review:two"} <= {t.id for t in state.tasks}
    state = update(state, "task_status", {"taskId": "reentry:job-review:one", "status": "completed", "notes": "Confirmed opening"})
    before = state.model_dump()
    employed = update(state, "job_obtained", {})
    assert state.model_dump() == before  # Preview is pure.
    assert employed.profile.employment.status == "employed"
    assert any(t.id.startswith("employment:start:") for t in employed.tasks)
    assert all(t.archived or t.status == "completed" for t in employed.tasks if t.id.startswith("reentry:job-action:"))
    later = update(employed, "housing_changed", {"status": "temporary", "temporaryHousingEndDate": (TODAY + timedelta(days=2)).isoformat()})
    continuity = next(t for t in later.tasks if t.id == "housing:continuity")
    assert continuity.priority == "critical" and continuity.deadline == TODAY + timedelta(days=2)
    completed = next(t for t in later.tasks if t.id == "reentry:job-review:one")
    assert completed.status == "completed" and completed.notes == "Confirmed opening"
    assert later.selectedRecommendationIds == ["job:one", "job:two"]
    assert any(c.type == "priority_changed" for c in later.changes)


def test_d_unavailable_provider_is_personal_and_preserves_contact():
    state = initial(profile(housing={"status": "no_confirmed_housing"}), ["provider:1"])
    contacted = update(state, "resource_status", {"recommendationId": "provider:1", "status": "contacted"})
    rejected = update(contacted, "resource_unavailable", {"recommendationId": "provider:1"})
    provider = next(r for r in rejected.recommendations if r.id == "provider:1")
    assert provider.userReportedAvailability == "unavailable" and provider.availabilityStatus == "unknown"
    assert provider.verificationStatus == "verified"  # Source scope is distinct.
    assert next(t for t in rejected.tasks if t.id == "contact:provider:1").status == "completed"
    alternative = next(t for t in rejected.tasks if t.id == "alternative:provider:1")
    assert alternative.relatedRecommendationIds == ["provider:2"]
    assert resources()[2].userReportedAvailability is None
    assert len(rejected.events) == 2


def test_e_unknown_information_confirmation_without_dates():
    state = initial(profile(release={"status": "unsure"}, employment={"status": "unsure"},
        barriers={"hasGovernmentId": None}, appointmentStatus="unsure"))
    assert "reentry:confirm-identification" in {t.id for t in state.tasks}
    assert all(t.deadline is None for t in state.tasks)
    assert not state.profile.employment.preferredJobTypes
    unrequested = initial(profile(release={"status": "unsure"}, employment={"status": "unsure"}, supportNeeds=[]))
    assert not any(t.id.startswith("reentry:priority-") for t in unrequested.tasks)


def test_replanning_graph_ids_history_dismissal_idempotence():
    state = initial(profile(), ["job:one", "job:two"])
    event = UserEvent(type="resource_status", payload={"recommendationId": "job:one", "status": "dismissed"})
    p, once = apply_event(state.profile, state, event)
    _, twice = apply_event(p, once, event)
    assert once == twice and len(twice.events) == 1
    assert "job:one" in twice.dismissedRecommendationIds and "job:one" not in twice.selectedRecommendationIds
    planned = planned_session(p, twice.recommendations, twice, event, today=TODAY, top_job_ids=[], warnings=[])
    seen = set()
    for task in planned.tasks:
        assert task.id not in seen and set(task.prerequisiteTaskIds) <= seen
        seen.add(task.id)
    assert len(planned.schedule) == 30
    assert scan(planned.model_dump(mode="json")) == []
    with pytest.raises(ValueError, match="prerequisite"):
        update(initial(profile(), ["job:one"]), "task_status", {"taskId": "reentry:job-action:one", "status": "completed"})


def test_profile_api_uses_existing_pipelines_and_actual_model(client):
    response = client.post("/recommendations", json={"profile": profile().model_dump(mode="json")})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["jobs"]["status"] == "ok" and data["housing_areas"]["status"] == "ok" and data["services"]["status"] == "ok"
    state = data["phoenix_session"]
    assert 1 <= len(state["topJobIds"]) <= 5
    job = next(r for r in state["recommendations"] if r["id"] == state["topJobIds"][0])
    assert set(job["details"]["modelPredictions"]) == {"education_required", "experience_required", "certification_required"}
    assert state["warnings"] == []
    assert all(r["availabilityStatus"] == "unknown" for r in state["recommendations"])
    assert scan(data) == []
    request = {"phoenix_session": state, "user_event": {"type": "resource_status", "payload": {"recommendationId": job["id"], "status": "selected"}}}
    selected = client.post("/recommendations", json=request)
    assert selected.status_code == 200, selected.text
    assert job["id"] in selected.json()["phoenix_session"]["selectedRecommendationIds"]
    native = client.post("/recommendations", json={"phoenix_session": selected.json()["phoenix_session"], "selected_job_id": job["details"]["jobId"]})
    assert native.status_code == 200, native.text
    rejected = client.post("/recommendations", json={"phoenix_session": native.json()["phoenix_session"], "selected_job_id": job["details"]["jobId"],
        "user_event": {"type": "resource_status", "payload": {"recommendationId": job["id"], "status": "rejected"}}})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["selected_job_id"] is None and rejected.json()["thirty_day_plan"] is None
    assert client.post("/recommendations", json={"phoenix_session": state, "user_event": {"type": "task_status", "payload": {"taskId": "invented", "status": "completed"}}}).status_code == 422


def test_multiple_selected_jobs_stay_current_beyond_group_display_limit(client, monkeypatch):
    from src.recommend import oakland_jobs
    state = client.post("/recommendations", json={"profile": profile().model_dump(mode="json")}).json()["phoenix_session"]
    selected = state["topJobIds"][0]
    monkeypatch.setattr(oakland_jobs, "LIMIT_PER_GROUP", 0)
    response = client.post("/recommendations", json={"phoenix_session": state, "user_event": {"type": "resource_status", "payload": {"recommendationId": selected, "status": "selected"}}})
    assert response.status_code == 200, response.text
    resource = next(r for r in response.json()["phoenix_session"]["recommendations"] if r["id"] == selected)
    assert resource["active"] is True
    assert any(t["id"] == f"reentry:job-review:{selected[4:]}" and not t["archived"] for t in response.json()["phoenix_session"]["tasks"])


def test_saved_classifier_inference_and_missing_artifact_fallback(monkeypatch):
    flags, warning = model_flags("A valid forklift certification and warehouse experience are required.")
    assert warning is None and flags["certification_required"] is True
    monkeypatch.setenv("PHOENIX_NLP_ARTIFACT", "/missing/weights.joblib")
    assert model_flags("A valid license is required.")[1]


def test_corrupt_model_falls_back_without_breaking_recommendations(monkeypatch, tmp_path):
    artifact = tmp_path / "corrupt.joblib"
    artifact.write_bytes(b"not model weights")
    monkeypatch.setenv("PHOENIX_NLP_ARTIFACT", str(artifact))
    flags, warning = model_flags("A valid license is required.")
    assert flags == {} and "unavailable" in warning.lower()


def test_qualification_uncertainty_is_neutral_not_a_positive_fit():
    checks = [{"requirement_kind": "required", "status": "reported_met"}, {"requirement_kind": "required", "status": "needs_confirmation"}]
    jobs = {"groups": [{"items": [dict(job_id="one", title="Warehouse", description="Duties only", pay={}, location={}, requirements=[], qualification_checks=checks)]}]}
    cards, _ = _job_recommendations(profile(), jobs)
    assert cards[0].details["components"]["qualification_fit"] == .75
    assert not cards[0].details["requirements"]  # No text cue, no invented model requirement.


def test_model_prediction_cannot_override_explicit_no_experience(monkeypatch):
    import src.recommend.reentry_matching as matching
    monkeypatch.setattr(matching, "model_flags", lambda text: ({"experience_required": True}, None))
    jobs = {"groups": [{"items": [dict(job_id="one", title="Warehouse", description="No prior experience is required. We provide training.", pay={}, location={}, requirements=[], qualification_checks=[])]}]}
    cards, _ = _job_recommendations(profile(), jobs)
    assert cards[0].details["modelPredictions"]["experience_required"] is True
    assert not cards[0].details["requirements"]


def test_completed_housing_step_gets_new_followup_as_end_approaches():
    state = initial(profile(housing={"status": "temporary", "temporaryHousingEndDate": "2026-12-15"}))
    state = update(state, "task_status", {"taskId": "housing:continuity", "status": "completed"})
    next_state = update(state, "housing_changed", {"status": "temporary", "temporaryHousingEndDate": "2026-11-16"})
    assert next(t for t in next_state.tasks if t.id == "housing:continuity").status == "completed"
    assert next(t for t in next_state.tasks if t.id == "housing:continuity-check:2026-11-16").priority == "critical"


def test_profile_edit_records_new_work_transition_once():
    state = initial(profile())
    employed = profile().model_dump(mode="json")
    employed["employment"]["status"] = "employed"
    first = update(state, "profile_updated", {"profile": employed})
    work = next(t for t in first.tasks if t.id.startswith("employment:start:"))
    first = update(first, "task_status", {"taskId": work.id, "status": "completed"})
    employed["housing"]["monthlyBudget"] = 1200
    second = update(first, "profile_updated", {"profile": employed})
    assert [t.id for t in second.tasks if t.id.startswith("employment:start:")] == [work.id]
    assert next(t for t in second.tasks if t.id == work.id).status == "completed"


@pytest.mark.parametrize("barrier", ["transportation", "housing"])
def test_new_setback_keeps_prior_completion_and_adds_stable_action(barrier):
    missing = profile(barriers={"hasGovernmentId": True, "hasTransportation": False}) if barrier == "transportation" else profile(housing={"status": "no_confirmed_housing"})
    state = initial(missing)
    key = "reentry:transportation" if barrier == "transportation" else "reentry:housing-now"
    state = update(state, "task_status", {"taskId": key, "status": "completed"})
    state = update(state, "transportation_changed", {"hasTransportation": True}) if barrier == "transportation" else update(state, "housing_changed", {"status": "stable"})
    state = update(state, "transportation_changed", {"hasTransportation": False}) if barrier == "transportation" else update(state, "housing_changed", {"status": "no_confirmed_housing"})
    assert next(t for t in state.tasks if t.id == key).status == "completed"
    action = next(t for t in state.tasks if t.id.startswith(key + ":reported:"))
    assert action.status == "not_started" and not action.archived
    again = planned_session(state.profile, state.recommendations, state, None, today=TODAY, top_job_ids=[], warnings=[])
    assert len([t for t in again.tasks if t.id.startswith(key + ":reported:")]) == 1


def test_job_loss_creates_new_action_without_resetting_past_applications():
    state = initial(profile(), ["job:one"])
    state = update(state, "task_status", {"taskId": "reentry:job-review:one", "status": "completed"})
    state = update(state, "task_status", {"taskId": "reentry:job-action:one", "status": "completed"})
    state = update(update(state, "job_obtained", {}), "job_lost", {})
    assert next(t for t in state.tasks if t.id == "reentry:job-action:one").status == "completed"
    assert any(t.id.startswith("employment:restart:") and t.status == "not_started" for t in state.tasks)


def test_employed_person_can_explicitly_choose_a_new_job():
    state = update(initial(profile()), "job_obtained", {})
    assert not any(t.id == "reentry:job-review:one" and not t.archived for t in state.tasks)
    selected = update(state, "resource_status", {"recommendationId": "job:one", "status": "selected"})
    assert any(t.id == "reentry:job-review:one" and not t.archived for t in selected.tasks)


def test_calendar_preserves_completed_slots_and_moves_new_actions_forward():
    state = initial(profile(), ["job:one"])
    review_day = next(d["day"] for d in state.schedule if "reentry:job-review:one" in d["task_ids"])
    state = update(state, "task_status", {"taskId": "reentry:job-review:one", "status": "completed"})
    assert next(d["day"] for d in state.schedule if "reentry:job-review:one" in d["task_ids"]) == review_day
    future = planned_session(state.profile, state.recommendations, state, None, today=TODAY + timedelta(days=5), top_job_ids=[], warnings=[])
    assert future.scheduleStartDate == TODAY
    assert next(d["day"] for d in future.schedule if "reentry:job-review:one" in d["task_ids"]) == review_day
    completed = {t.id for t in future.tasks if t.status == "completed"}
    assert all(d["day"] >= 6 for d in future.schedule if any(i not in completed for i in d["task_ids"]))


def test_invalid_saved_dependency_cycle_is_rejected_at_api_boundary(client):
    state = initial(profile(), ["job:one"]).model_dump(mode="json")
    task = state["tasks"][0]
    task["prerequisiteTaskIds"] = [task["id"]]
    response = client.post("/recommendations", json={"phoenix_session": state})
    assert response.status_code == 422
    state = initial(profile()).model_dump(mode="json")
    other = profile(profileId="different-fictional-profile").model_dump(mode="json")
    assert client.post("/recommendations", json={"phoenix_session": state, "profile": other}).status_code == 422


def test_higher_pay_small_extra_distance_and_no_source_mutation():
    def card(identifier, pay, distance):
        return dict(job_id=identifier, title="Warehouse assistant", description="Warehouse duties", pay={"hourly_equivalent_min": pay},
            location={"city": "Oakland", "distance_miles": distance}, requirements=[], qualification_checks=[])
    jobs = {"groups": [{"items": [card("one", 20, 2), card("two", 40, 2.5)]}]}
    before = deepcopy(jobs)
    result, _ = _job_recommendations(profile(), jobs)
    assert result[0].id == "job:two"
    assert jobs == before
    # An unrelated extreme salary must not rescale the same $20->$40 choice.
    jobs["groups"][0]["items"].append(card("outlier", 500, 20))
    p = profile(barriers={"hasGovernmentId": True, "hasTransportation": False})
    result, _ = _job_recommendations(p, jobs)
    scores = {r.id: r.score for r in result}
    assert scores["job:two"] > scores["job:one"]

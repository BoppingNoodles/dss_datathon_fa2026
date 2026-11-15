"""Fictional profiles; no personal reentry data. Covers requested cases A–G."""
from datetime import date
from itertools import product
import json

import pytest

from src.audit.privacy_check import scan
from src.common import ROOT
from src.recommend.reentry_models import ReentrySituation, ReentryTask
from src.recommend.reentry_planner import build_reentry_plan, candidate_referrals, ordered_tasks, verified_referrals

TODAY = date(2026, 11, 14)
READY = dict(release_status="already_released", has_immediate_housing="yes", has_id="yes",
             has_transportation="yes", has_phone_access="yes", has_required_appointment="no")
BASE = dict(location="Oakland", priority_need="work", experience={"skills": ["Warehouse"], "years": 2},
            education={"level": "high_school_or_ged", "credentials": []})


def plan(**changes):
    return build_reentry_plan({**BASE, "reentry": {**READY, **changes}}, {}, {}, {}, source="synthetic", today=TODAY)


def test_a_ready_user_prioritizes_jobs():
    result = plan()
    assert result.tasks[0].barrier in {"employment", "documents", "qualifications"}
    assert not any(t.task_id == "reentry:identification" for t in result.tasks)


def test_b_missing_id_adds_help_without_blocking_jobs():
    result = plan(has_id="no")
    task = next(t for t in result.tasks if t.task_id == "reentry:identification")
    assert task.title == "Find ID assistance" and task.priority == "high"
    assert not any(task.task_id in t.prerequisites for t in result.tasks if t.barrier == "employment")


def test_c_missing_housing_first_and_scheduled_today():
    result = plan(has_immediate_housing="no")
    assert result.next_task_ids[0] == "reentry:housing-now"
    first = result.tasks[0]
    assert first.priority == "immediate" and first.deadline == TODAY
    assert first.task_id in result.daily_actions[0].task_ids


@pytest.mark.parametrize("unknown", [None, "unsure"])
def test_d_unknown_id_is_confirmation_not_missing(unknown):
    result = plan(has_id=unknown)
    assert "reentry:confirm-identification" in {t.task_id for t in result.tasks}
    assert "reentry:identification" not in {t.task_id for t in result.tasks}


def test_privacy_answers_are_not_assumed_missing(client):
    reentry = {**READY, "release_status": "prefer_not_to_say", "has_id": "prefer_not_to_say",
               "has_phone_access": "prefer_not_to_say", "has_required_appointment": "prefer_not_to_say", "employment_goal": "unsure"}
    response = client.post("/recommendations", json={**BASE, "reentry": reentry})
    assert response.status_code == 200, response.text
    ids = {t["task_id"] for t in response.json()["reentry_plan"]["tasks"]}
    assert "reentry:confirm-identification" in ids
    assert "reentry:identification" not in ids and "reentry:appointment" not in ids


def test_e_old_api_requests_unchanged(client):
    old = client.post("/recommendations", json=BASE)
    assert old.status_code == 200, old.text
    assert old.json()["reentry_plan"] is None
    new = client.post("/recommendations", json={**BASE, "reentry": READY})
    assert new.status_code == 200, new.text
    for key, value in old.json().items():
        if key != "reentry_plan":
            assert new.json()[key] == value
    assert scan(new.json()) == []
    assert new.json()["reentry_plan"]["synthetic"] is True


def test_f_all_barrier_combinations_have_unique_acyclic_graphs():
    for answers in product(["yes", "no", "unsure", "prefer_not_to_say", None], repeat=4):
        result = plan(**dict(zip(["has_id", "has_immediate_housing", "has_transportation", "has_phone_access"], answers)), has_required_appointment="yes")
        seen = set()
        for task in result.tasks:
            assert task.task_id not in seen
            assert set(task.prerequisites) <= seen
            seen.add(task.task_id)
        assert len(result.daily_actions) == 30
        assert len({a.action_id for a in result.daily_actions}) == 30
        assert [a.day for a in result.daily_actions] == list(range(1, 31))


def test_g_general_maps_verification_never_confirms_reentry_eligibility(synthetic):
    resources = candidate_referrals("housing", BASE, synthetic["candidates"], synthetic["refs"], source="synthetic", today=TODAY)
    assert resources
    assert all(r.verification != "verified_reentry_scope" for r in resources)
    assert all(r.confirmation.startswith("Contact to confirm") for r in resources)
    assert all("confirmed eligible" not in r.model_dump_json().lower() for r in resources)


def test_official_registry_has_sources_dates_scopes_and_geography():
    rows = verified_referrals("Oakland", "identification", TODAY)
    assert rows and all(r.source_url and r.checked_on and r.scope for r in rows)
    assert verified_referrals("Richmond", "identification", TODAY) == []
    assert verified_referrals("Oakland", "identification", date(2026, 11, 13)) == []
    assert all("guaranteed" not in r.confirmation for r in rows)


def test_only_reported_appointment_creates_dependency():
    assert not any(t.barrier == "appointment" for t in plan(has_required_appointment="prefer_not_to_say").tasks)
    result = plan(has_required_appointment="yes", has_transportation="no")
    trip = next(t for t in result.tasks if t.task_id == "reentry:appointment-trip")
    assert trip.prerequisites == ["reentry:appointment"] and trip.status == "waiting"
    assert trip.deadline is None
    assert next(t for t in result.tasks if t.task_id == "reentry:transportation").prerequisites == []


def test_unsure_appointment_prompts_a_private_check_without_inventing_an_obligation():
    result = plan(has_required_appointment="unsure", has_transportation="no")
    ids = {t.task_id for t in result.tasks}
    assert "reentry:confirm-appointment" in ids
    assert "reentry:appointment" not in ids and "reentry:appointment-trip" not in ids


def test_prerelease_housing_has_reported_date_without_inventing_tonight():
    result = plan(release_status="preparing_for_release", release_date="2026-12-01", has_immediate_housing="no")
    task = next(t for t in result.tasks if t.task_id == "reentry:housing-now")
    assert task.deadline == date(2026, 12, 1) and "tonight" not in task.title
    assert task.priority == "high"
    assert all(t.task_id != "reentry:release-timing" for t in result.tasks)


def test_passed_release_date_prompts_update_without_inferred_release():
    result = plan(release_status="preparing_for_release", release_date="2026-11-01", has_immediate_housing="no")
    assert "reentry:release-timing" in {t.task_id for t in result.tasks}
    assert all("tonight" not in t.title for t in result.tasks)


def test_completion_unlocks_tasks_and_rejects_out_of_order_completion():
    req = {**BASE, "reentry": {**READY, "has_required_appointment": "yes", "has_transportation": "no"}}
    req["reentry_completed_ids"] = ["reentry:appointment-trip", "made-up-task"]
    result = build_reentry_plan(req, {}, {}, {}, source="synthetic", today=TODAY)
    assert result.completed_ids == []
    req["reentry_completed_ids"] += ["reentry:appointment"]
    result = build_reentry_plan(req, {}, {}, {}, source="synthetic", today=TODAY)
    assert {"reentry:appointment", "reentry:appointment-trip"} <= set(result.completed_ids)
    req["reentry_completed_ids"] = ["reentry:appointment-trip"]
    result = build_reentry_plan(req, {}, {}, {}, source="synthetic", today=TODAY)
    assert "reentry:appointment-trip" not in result.completed_ids


def test_deadline_order_and_rule_graph_guards():
    def task(key, **kw):
        return ReentryTask(task_id=key, title=key, action="Check", barrier="test", priority="high", rationale="Test", **kw)
    assert [t.task_id for t in ordered_tasks([task("a", deadline=date(2026, 12, 1)), task("b", deadline=TODAY)])] == ["b", "a"]
    for tasks in [[task("a"), task("a")], [task("a", prerequisites=["b"])],
                  [task("a", prerequisites=["b"]), task("b", prerequisites=["a"])]]:
        with pytest.raises(ValueError):
            ordered_tasks(tasks)


def test_schema_rejects_sensitive_fields_and_invalid_dates(client):
    for extra in [{"case_number": "fictional"}, {"release_date": "2026-02-30"}, {"has_id": "maybe"}]:
        response = client.post("/recommendations", json={**BASE, "reentry": {**READY, **extra}})
        assert response.status_code == 422
    assert ReentrySituation().has_id is None


def test_selected_job_qualifications_and_existing_daily_plan_are_used(client):
    initial = client.post("/recommendations", json={**BASE, "reentry": READY}).json()
    cards = [c for g in initial["jobs"]["groups"] + initial["jobs"]["other_groups"] for c in g["items"]]
    card = cards[0]
    selected = client.post("/recommendations", json={**BASE, "reentry": READY, "selected_job_id": card["job_id"]})
    assert selected.status_code == 200, selected.text
    response = selected.json()
    plan = response["reentry_plan"]
    assert any(card["title"] in t["action"] for t in plan["tasks"])
    free_day = next(day for day in plan["daily_actions"] if not day["task_ids"])
    original = next(day for day in response["thirty_day_plan"]["daily_actions"] if day["day"] == free_day["day"])
    assert free_day["action"] == original["action"]


def test_specific_qualification_gap_comes_from_selected_job():
    card = {"job_id": "fictional-cdl", "title": "Delivery driver", "url": "https://example.org/job",
            "qualification_checks": [{"key": "cdl-a", "label": "Class-A CDL", "status": "gap",
                "requirement_kind": "required", "detail": "Posting requires a Class-A CDL."}]}
    result = build_reentry_plan({**BASE, "reentry": READY, "selected_job_id": card["job_id"]},
        {"groups": [{"items": [card]}]}, {}, {}, source="synthetic", today=TODAY)
    task = next(t for t in result.tasks if t.task_id.startswith("reentry:qualification:"))
    assert task.title == "Check Class-A CDL" and task.rationale == card["qualification_checks"][0]["detail"]
    assert task.links[0]["url"] == card["url"]
    card["qualification_checks"][0]["status"] = "reported_met"
    held = build_reentry_plan({**BASE, "reentry": READY, "selected_job_id": card["job_id"]},
        {"groups": [{"items": [card]}]}, {}, {}, source="synthetic", today=TODAY)
    assert not any(t.task_id.startswith("reentry:qualification:") for t in held.tasks)


def test_changing_job_does_not_reuse_calendar_activity_completion():
    def selected(job_id, completed):
        request = {**BASE, "reentry": READY, "selected_job_id": job_id, "reentry_completed_ids": completed}
        card = {"job_id": job_id, "title": job_id, "url": None}
        return build_reentry_plan(request, {"groups": [{"items": [card]}]}, {}, {}, source="synthetic", today=TODAY)
    first = selected("fictional-role-a", [])
    day_id = first.daily_actions[7].action_id
    first = selected("fictional-role-a", [day_id, "reentry:work-documents"])
    assert day_id in first.completed_ids
    second = selected("fictional-role-b", first.completed_ids)
    assert day_id not in second.completed_ids
    assert "reentry:work-documents" in second.completed_ids


def test_three_fictional_profiles_have_materially_different_api_plans(client):
    profiles = json.loads((ROOT / "backend/fixtures/reentry_profiles.json").read_text())
    results = []
    for profile in profiles:
        response = client.post("/recommendations", json={k: v for k, v in profile.items() if not k.startswith("_")})
        assert response.status_code == 200, response.text
        result = response.json()
        assert scan(result) == []
        assert result["jobs"]["status"] == result["housing_areas"]["status"] == "ok"
        assert result["services"]["status"] == "ok"
        results.append(result)
    a, b, c = [result["reentry_plan"] for result in results]
    assert a["next_task_ids"][0] == "reentry:housing-now"
    assert "reentry:identification" in a["next_task_ids"]
    assert all(t["stage"] == "building_independence" for t in b["tasks"])
    assert b["next_task_ids"][0] == "reentry:job-review:browse"
    assert not any(t["barrier"] in {"housing", "identification", "transportation", "communication"} for t in b["tasks"])
    assert c["next_task_ids"][:2] == ["reentry:appointment", "reentry:transportation"]
    trip = next(t for t in c["tasks"] if t["task_id"] == "reentry:appointment-trip")
    assert trip["prerequisites"] == ["reentry:appointment"] and trip["status"] == "waiting"
    assert not any(t["task_id"] == "reentry:housing-now" for t in c["tasks"])
    assert len({tuple(p["next_task_ids"]) for p in [a, b, c]}) == 3
    assert results[0]["jobs"] == results[1]["jobs"]
    assert results[0]["housing_areas"] == results[1]["housing_areas"]
    housing_task = next(t for t in a["tasks"] if t["task_id"] == "reentry:housing-now")
    assert housing_task["resource_tab"] == "services" and housing_task["resource_need"] == "housing"
    assert housing_task["referrals"]
    transport = next(t for t in c["tasks"] if t["task_id"] == "reentry:transportation")
    assert transport["resource_need"] == "transportation" and transport["referrals"]


def test_resource_need_changes_services_without_changing_the_plan_or_matching(client):
    request = {**BASE, "reentry": {**READY, "has_immediate_housing": "no", "employment_goal": "find_work"}}
    before = client.post("/recommendations", json=request).json()
    after = client.post("/recommendations", json={**request, "service_need": "housing"}).json()
    assert after["services"]["priority_need"] == "housing"
    assert before["services"]["priority_need"] == "work"
    for field in ["jobs", "housing_areas", "reentry_plan"]:
        assert after[field] == before[field]


def test_no_application_tasks_when_work_is_not_the_persons_goal():
    result = plan(employment_goal="not_now", has_immediate_housing="no")
    assert not any(t.barrier in {"employment", "qualifications", "documents"} for t in result.tasks)
    keep = plan(employment_goal="keep_work")
    assert "reentry:work-routine" in {t.task_id for t in keep.tasks}
    assert next(t for t in keep.tasks if t.task_id == "reentry:work-routine").resource_tab is None
    assert not any(t.task_id.startswith("reentry:job-action:") for t in keep.tasks)
    preparing = plan(employment_goal="prepare_for_work")
    assert any(t.task_id.startswith("reentry:job-preparation:") for t in preparing.tasks)
    assert not any(t.task_id.startswith("reentry:job-action:") for t in preparing.tasks)
    assert len(plan(employment_goal="not_now").daily_actions) == 30


def test_existing_model_predictions_become_confirmation_steps_without_inventing_credentials():
    card = {"job_id": "fictional-model", "title": "Warehouse role", "url": "https://example.org/job",
            "requirements": [{"label": "certification_required", "status": "required", "source": "model_prediction"}],
            "qualification_checks": []}
    def build():
        return build_reentry_plan({**BASE, "reentry": {**READY, "employment_goal": "find_work"}, "selected_job_id": card["job_id"]},
            {"groups": [{"items": [card]}]}, {}, {}, source="synthetic", today=TODAY)
    result = build()
    task = next(t for t in result.tasks if "model-check" in t.task_id)
    assert task.barrier == "qualifications" and task.links[0]["url"] == card["url"]
    assert "model prediction" in " ".join(task.confirmations)
    assert "CDL" not in task.action and "forklift" not in task.action
    card["requirements"][0]["status"] = "preferred"
    assert not any("model-check" in t.task_id for t in build().tasks)

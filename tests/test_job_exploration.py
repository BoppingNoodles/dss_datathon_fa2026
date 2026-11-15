from src.phoenix.models import Job
from src.recommend import jobs, person1_data


def test_salary_sized_hourly_source_amount_does_not_dominate_ranking_or_rent_scenario():
    from src.phoenix.models import Pay, UserProfile
    from src.phoenix.pay import annual_income
    from src.phoenix.ranking import rank_jobs

    profile = UserProfile(location="Oakland", priority_need="work")
    mistaken = Job(job_id="uncertain", title="Example", company="Fictional", city="Oakland", location_text="Oakland",
        pay=Pay(minimum=103000, maximum=121000, period="hour", currency="USD", source="advertised", raw="$103,000–$121,000 per hour"))
    ordinary = mistaken.model_copy(update={"job_id": "ordinary", "pay": Pay(minimum=25, maximum=30, period="hour", currency="USD", source="advertised")})
    ranked = rank_jobs([mistaken, ordinary], profile)
    assert [card.job_id for card in ranked] == ["ordinary", "uncertain"]
    assert ranked[1].pay.minimum is None and ranked[1].pay_basis == "pay_needs_confirmation"
    assert "No annual salary was inferred" in ranked[1].pay.notes[0]
    public = jobs._public(ranked[1], mistaken, "synthetic")
    assert public["pay"]["needs_confirmation"] and public["pay"]["period"] is None
    assert public["pay"]["raw_text"] == mistaken.pay.raw
    assert annual_income(mistaken, scenario_hours_per_week=40, scenario_weeks_per_year=52)["minimum"] is None
    assert mistaken.pay.minimum == 103000  # cached source data stays unchanged


def test_job_exploration_separates_roles_and_selected_other_role_builds_plan(client, monkeypatch):
    records = [Job(job_id=title, title=title, company="Fictional employer", city="Oakland",
                   location_text="Oakland, CA", description="High school diploma required.")
               for title in ["Warehouse Associate", "Barista"]]
    monkeypatch.setattr(jobs, "_profile_with_jobs", lambda request, source:
        (person1_data.native_profile(request, "synthetic"), records, []))
    request = {"location": "Oakland", "priority_need": "work",
               "experience": {"skills": ["warehouse"], "years": 2},
               "education": {"level": "high_school_or_ged"}}
    result = client.post("/recommendations", json=request)
    assert result.status_code == 200, result.text
    section = result.json()["jobs"]
    assert [j["title"] for g in section["groups"] for j in g["items"]] == ["Warehouse Associate"]
    assert [j["title"] for g in section["other_groups"] for j in g["items"]] == ["Barista"]
    item = section["groups"][0]["items"][0]
    assert item["matches_reported_role"] is True
    assert item["qualification_checks"][0]["status"] == "reported_met"
    selected = client.post("/recommendations", json={**request, "selected_job_id": "Barista"})
    assert selected.status_code == 200, selected.text
    assert len(selected.json()["thirty_day_plan"]["daily_actions"]) == 30
    assert selected.json()["jobs"]["other_groups"][0]["items"][0]["is_selected"]


def test_no_matching_roles_still_allows_exploration_and_skipped_experience_does_not_duplicate(client, monkeypatch):
    record = Job(job_id="barista", title="Barista", company="Fictional", city="Oakland", location_text="Oakland")
    monkeypatch.setattr(jobs, "_profile_with_jobs", lambda request, source:
        (person1_data.native_profile(request, "synthetic"), [record], []))
    request = {"location": "Oakland", "priority_need": "work", "experience": {"skills": ["warehouse"]}}
    data = client.post("/recommendations", json=request).json()["jobs"]
    assert data["status"] == "ok" and data["groups"] == []
    assert len(data["other_groups"]) == 1
    data = client.post("/recommendations", json={"location": "Oakland", "priority_need": "work"}).json()["jobs"]
    assert len(data["groups"]) == 1 and data["other_groups"] == []
    assert data["groups"][0]["items"][0]["matches_reported_role"] is None

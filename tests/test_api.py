import json

import pytest

from src.audit.privacy_check import scan
from src.common import ROOT
from src.recommend import jobs
from src.recommend.housing_math import compare

PROFILES = [{k: v for k, v in p.items() if not k.startswith("_")}
            for p in json.loads((ROOT / "backend/fixtures/profiles.json").read_text())]


def test_health(client):
    j = client.get("/health").json()
    assert j["status"] == "ok" and j["source"] == "synthetic"


@pytest.mark.parametrize("profile", PROFILES)
def test_recommendations_contract_and_privacy(client, profile):
    r = client.post("/recommendations", json=profile)
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j) >= {"jobs", "housing_areas", "services", "data_coverage", "next_steps"}
    assert j["data_coverage"]["mode"] == "synthetic"
    assert any("SYNTHETIC" in n for n in j["data_coverage"]["notes"])
    assert scan(j) == []


def test_only_location_and_need_required(client):
    assert client.post("/recommendations", json={"location": "Oakland", "priority_need": "food"}).status_code == 200
    assert client.post("/recommendations", json={"location": "Oakland"}).status_code == 422
    assert client.post("/recommendations", json={"priority_need": "food"}).status_code == 422


def test_unrequested_sensitive_fields_rejected(client):
    r = client.post("/recommendations", json={"location": "Oakland", "priority_need": "food", "ssn": "x"})
    assert r.status_code == 422


def test_open_tab_follows_need(client):
    for need, tab in [("work", "jobs"), ("housing", "housing"), ("food", "services")]:
        assert client.post("/recommendations", json={"location": "Oakland", "priority_need": need}).json()["open_tab"] == tab


def test_jobs_and_housing_not_invented_before_integration(client):
    j = client.post("/recommendations", json={"location": "Oakland", "priority_need": "work"}).json()
    assert j["jobs"]["status"] in ("not_integrated", "ok", "no_results")
    if j["jobs"]["status"] == "not_integrated":
        assert j["jobs"]["groups"] == []
    if j["housing_areas"]["status"] == "not_integrated":
        assert j["housing_areas"]["areas"] == []


def test_oakland_jobs_contract_and_sorts(client, monkeypatch, tmp_path):
    path = tmp_path / "oakland_jobs.json"
    monkeypatch.setattr(jobs, "JOBS_PATH", path)
    row = {
        "title": "Warehouse associate", "employer": "Example employer", "city": "Oakland", "state": "CA",
        "source_url": "https://www.indeed.com/viewjob?jk=example", "salary_text": "$20 - $24 an hour",
        "annual_pay_low": 41600, "annual_pay_high": 49920,
        "requirements": {"experience_required": {"status": "unknown", "evidence": "Warehouse experience."}},
    }
    path.write_text(json.dumps({
        "metadata": {"hourly_pay_assumptions": {"hours_per_week": 40, "weeks_per_year": 52}},
        "jobs": [
            dict(row, job_id="newer", posted_date="2026-08-01"),
            dict(row, job_id="higher", posted_date="2026-07-01", salary_text="$25 an hour",
                 annual_pay_low=52000, annual_pay_high=52000),
        ],
    }), encoding="utf-8")

    def section(location, sort="highest_pay"):
        response = client.post("/recommendations", json={"location": location, "priority_need": "work", "job_sort": sort})
        assert response.status_code == 200, response.text
        return response.json()["jobs"]

    cards = section("94612")["groups"][0]["items"]
    assert [card["job_id"] for card in cards] == ["higher", "newer"]
    assert (cards[1]["pay"]["min"], cards[1]["pay"]["max"], cards[1]["pay"]["period"]) == (20, 24, "hour")
    assert cards[1]["requirements"][0]["status"] == "unknown"
    assert cards[1]["requirements"][0]["evidence"] == "Warehouse experience."
    assert cards[1]["url"] == row["source_url"]
    assert cards[1]["location"]["distance_miles"] is None
    assert section("Oakland", "nearest")["groups"][0]["items"][0]["job_id"] == "newer"
    assert section("Berkeley")["status"] == "no_results"
    path.unlink()
    assert section("Oakland")["status"] == "not_integrated"


def test_rent_burden_example_from_plan():
    out = compare(48000, None, "year", None, 1200)
    assert out["rent_burden_min"] == pytest.approx(0.30) and out["rent_burden_max"] == pytest.approx(0.30)


def test_rent_burden_interval_and_assumptions():
    out = compare(20, 25, "hour", None, 1800)
    assert out["annual_gross_min"] == 20 * 40 * 52 and out["annual_gross_max"] == 25 * 40 * 52
    assert out["rent_burden_min"] < out["rent_burden_max"]
    assert any("Assumed 40" in a for a in out["assumptions"])
    stated = compare(20, None, "hour", 20, 1800)
    assert stated["annual_gross_min"] == 20 * 20 * 52 and not any("Assumed 40" in a for a in stated["assumptions"])


def test_rent_burden_unknown_not_zero():
    for args in [(None, None, None, None, 1200), (50000, None, "year", None, None), (20, None, None, None, 1000)]:
        out = compare(*args)
        assert out["status"] == "unknown" and out["rent_burden_min"] is None and out["rent_burden_max"] is None


def test_housing_comparison_endpoint(client):
    r = client.post("/housing-comparison", json={"pay_min": 48000, "pay_period": "year", "monthly_rent": 1200})
    assert r.status_code == 200 and r.json()["rent_burden_max"] == pytest.approx(0.30)


def test_privacy_scanner_catches_violations():
    bad = {"services": {"x": "https://www.google.com/maps/contrib/123/reviews"},
           "housing_areas": {"areas": [{"zpid": "1", "address": "1 Main St"}]}}
    problems = scan(bad)
    assert any("contributor_url" in p for p in problems) and any("zpid" in p for p in problems)


def test_root_points_to_docs_and_app(client):
    j = client.get("/").json()
    assert j["docs"] == "/docs" and "localhost:3000" in j["app"]

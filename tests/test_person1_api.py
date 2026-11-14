import json

import pandas as pd
import pytest

from backend.app.schemas import HousingSection, RecommendationResponse
from src.audit.privacy_check import scan
from src.common import processed_dir
from src.phoenix.models import Job, Pay
from src.recommend import prepare_person1


@pytest.fixture(scope="module")
def person1_api(client):
    prepare_person1.run("synthetic")
    return client


def profile(**updates):
    return {"location":"Oakland", "priority_need":"work", "age":35,
            "experience":{"skills":["warehouse", "inventory"], "years":2},
            "education":{"level":"high_school_or_ged", "credentials":[]}, **updates}


def cards(response):
    return [item for group in response["jobs"]["groups"] for item in group["items"]]


def test_existing_public_contract_now_contains_real_adapter_sections(person1_api):
    response=person1_api.post("/recommendations",json=profile())
    assert response.status_code==200,response.text
    data=response.json()
    RecommendationResponse.model_validate(data)
    assert data["jobs"]["status"]=="ok" and data["housing_areas"]["status"]=="ok"
    assert cards(data)[0]["job_id"]=="example-b"
    assert cards(data)[1]["job_id"]=="example-a"
    assert data["housing_areas"]["areas"][0]["usable_rental_records"]==6
    assert scan(data)==[]
    assert data["thirty_day_plan"] is None and data["selected_job_id"] is None


def test_no_synthetic_request_reads_full_real_person1_data(person1_api):
    data=person1_api.post("/recommendations",json=profile()).json()
    assert data["data_coverage"]["mode"]=="synthetic"
    assert data["data_coverage"]["sources"]["jobs"]["retained_records"]==3
    assert {c["job_id"] for c in cards(data)}=={"example-a","example-b","example-missing-pay"}
    assert all(c["source"]["mode"]=="synthetic" for c in cards(data))


def test_missing_synthetic_inputs_never_fall_back_to_real_oakland_export(person1_api, monkeypatch):
    from src.recommend import jobs, oakland_jobs
    from src.recommend.person1_data import Person1DataUnavailable

    def unavailable(source):
        raise Person1DataUnavailable("Synthetic inputs intentionally absent")

    def real_export_must_not_run(*args, **kwargs):
        pytest.fail("A synthetic request attempted to load the real Oakland export")

    monkeypatch.setattr(jobs, "load_person1", unavailable)
    monkeypatch.setattr(oakland_jobs, "rank_jobs", real_export_must_not_run)
    response = person1_api.post("/recommendations", json=profile())
    assert response.status_code == 200
    assert response.json()["jobs"]["status"] == "not_integrated"
    assert response.json()["jobs"]["groups"] == []


def test_services_are_unchanged_by_job_selection(person1_api):
    before=person1_api.post("/recommendations",json=profile()).json()
    after=person1_api.post("/recommendations",json=profile(selected_job_id="example-b")).json()
    assert after["services"]==before["services"]
    assert after["selected_job_id"]=="example-b"
    assert after["thirty_day_plan"]["target_job_id"]=="example-b"
    assert next(c for c in cards(after) if c["job_id"]=="example-b")["is_selected"]


def test_credential_gap_selection_and_interim_income_round_trip(person1_api):
    path=processed_dir("synthetic")/"jobs.jsonl"
    original=path.read_text()
    target=Job(job_id="example-cdl",title="Warehouse / CDL-A Driver",company="Fictional carrier",
        city="Oakland",location_text="Oakland, CA",is_expired=False,
        description="Warehouse work. Certifications: Class-A CDL with required endorsements.",
        pay=Pay(minimum=60,maximum=60,period="hour",currency="USD",source="advertised"))
    try:
        path.write_text(original+target.model_dump_json()+"\n")
        response=person1_api.post("/recommendations",json=profile(selected_job_id="example-cdl",
            selected_interim_job_id="example-a",scenario_hours_per_week=40,scenario_weeks_per_year=52))
        assert response.status_code==200,response.text
        data=response.json()
        path_data=data["thirty_day_plan"]["credential_paths"][0]
        assert path_data["credential"]=="Class-A CDL" and path_data["user_status"]=="not_confirmed"
        assert data["housing_income_job_id"]=="example-a"
        assert data["housing_income_stage"]=="interim_job_scenario"
        assert data["housing_comparisons"][0]["annual_gross_pay_scenario"]["minimum"]==41600
        assert scan(data)==[]
    finally:
        path.write_text(original)


def test_bad_or_missing_selection_returns_validation_error(person1_api):
    for extra in [{"selected_job_id":"not-a-job"}, {"selected_interim_job_id":"example-a"},
                  {"selected_job_id":"example-b","selected_interim_job_id":"example-b"}]:
        result=person1_api.post("/recommendations",json=profile(**extra))
        assert result.status_code==422,result.text


def test_health_need_and_skipped_answers_keep_existing_request_shape(person1_api):
    response=person1_api.post("/recommendations",json={"location":"Oakland","priority_need":"health_care"})
    assert response.status_code==200,response.text
    assert response.json()["open_tab"]=="services"
    assert response.json()["jobs"]["status"]=="ok"


def test_out_of_area_does_not_broaden_to_all_cities(person1_api):
    data=person1_api.post("/recommendations",json=profile(location="Fresno")).json()
    assert data["jobs"]["status"]=="no_results" and not cards(data)
    assert data["housing_areas"]["status"]=="no_results"


def test_nearest_exposes_distance_precision_and_preserves_pay_groups(person1_api):
    data=person1_api.post("/recommendations",json=profile(job_sort="nearest")).json()
    assert data["jobs"]["sort"]=="nearest"
    assert all("USD/" not in group["key"] for group in data["jobs"]["groups"])
    for card in cards(data):
        if card["location"]["distance_miles"] is not None:
            assert card["location"]["precision"]=="worksite"


def test_housing_service_access_is_an_area_statistic_not_a_fake_point_count(person1_api,monkeypatch):
    from src.recommend import housing
    from src.recommend.person1_data import load_person1
    jobs,rentals,coverage=load_person1("synthetic")
    located=[r.model_copy(update={"latitude":37.8,"longitude":-122.27}) for r in rentals]
    monkeypatch.setattr(housing,"load_person1",lambda source:(jobs,located,coverage))
    services=pd.DataFrame([{"place_id":"example-food","family":"food_assistance","family_label":"Food assistance",
        "lat":37.801,"lon":-122.27,"permanently_closed":False,"temporarily_closed":False}])
    result=housing.housing_areas("Oakland",services,source="synthetic")
    HousingSection.model_validate(result)
    summary=result["areas"][0]["nearby_services"][0]
    assert summary["median_count_within_1_mile"]==1
    assert summary["share_of_properties_with_service"]==1
    assert summary.get("count_within_1_mile") is None
    assert scan({"housing_areas":result})==[]


def test_city_name_ending_in_ca_is_not_mistaken_for_a_state_suffix(person1_api):
    from src.recommend.person1_data import native_profile
    resolved=native_profile({"location":"Pacifica","priority_need":"housing"},"synthetic")
    assert resolved.search_cities==["Pacifica"]

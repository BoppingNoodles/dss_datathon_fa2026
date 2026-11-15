from copy import deepcopy

from src.audit.privacy_check import scan
from src.phoenix.models import Job, Point, UserProfile
from src.recommend.housing_recommendations import recommend_housing
from src.recommend.jobs import job_map_location


def area(key, rent, *, share=None, family="food_assistance", **extra):
    return {"area_id": key, "area_type": "zip", "label": key, "median_monthly_rent": rent,
            "usable_rental_records": 10, "suppressed": False,
            "nearby_services": [] if share is None else [{"family": family, "family_label": "Food assistance",
                "share_of_properties_with_service": share, "median_count_within_1_mile": 1}], **extra}


def section(*areas):
    return {"status": "ok", "areas": list(areas), "notes": []}


def test_housing_defaults_to_lower_rent_and_never_uses_age_or_education():
    data = section(area("higher", 2000), area("lower", 1200))
    before = deepcopy(data)
    result = recommend_housing(data, {"priority_need": "housing", "age": 20})
    assert [a["area_id"] for a in result["areas"]] == ["lower", "higher"]
    assert result == recommend_housing(data, {"priority_need": "housing", "age": 80, "education": {"level": "bachelor"}})
    assert data == before
    assert "not assumed" in result["ranking_note"]


def test_priority_need_changes_service_relevance_without_inventing_cost_eligibility():
    data = section(area("cheaper", 1200, share=0), area("food-nearby", 1400, share=.8))
    food = recommend_housing(data, {"priority_need": "food"})
    housing = recommend_housing(data, {"priority_need": "housing"})
    assert food["areas"][0]["area_id"] == "food-nearby"
    assert housing["areas"][0]["area_id"] == "cheaper"
    assert "80%" in food["areas"][0]["recommendation"]["reasons"][1]
    assert "eligibility" in food["areas"][0]["recommendation"]["reasons"][1]


def test_selected_job_gross_pay_guide_does_not_claim_current_income():
    data = section(area("lower", 1000, share=0), area("higher", 1500, share=1))
    selection = {"housing_income_stage": "target_job_scenario", "housing_comparisons": [
        {"area_id": "lower", "rent_burden_minimum": .3, "rent_burden_maximum": .3},
        {"area_id": "higher", "rent_burden_minimum": .45, "rent_burden_maximum": .45}]}
    result = recommend_housing(data, {"priority_need": "food"}, selection)
    assert result["areas"][0]["area_id"] == "lower"
    recommended = result["areas"][0]["recommendation"]
    assert recommended["rent_burden_maximum"] == .3
    assert recommended["income_stage"] == "target_job_scenario"
    assert "not current income" in recommended["reasons"][-1]
    assert "30%" in recommended["reasons"][-1]


def test_zip_and_city_populations_are_not_compared_or_counted_twice():
    result = recommend_housing(section(area("city", 500, area_type="city"), area("zip", 1500)), {"priority_need": "housing"})
    assert result["areas"][0]["area_id"] == "zip"
    assert result["areas"][1]["recommendation"] is None
    fallback = recommend_housing(section(area("city", 1500, area_type="city")), {"priority_need": "housing"})
    assert fallback["areas"][0]["recommendation"]["rank"] == 1


def test_sparse_suppressed_missing_rent_and_missing_service_data_are_not_fabricated():
    result = recommend_housing(section(area("unknown", None), area("small", 500, usable_rental_records=4),
        area("suppressed", 600, suppressed=True), area("usable", 1500)), {"priority_need": "housing"})
    assert [a["area_id"] for a in result["areas"] if a["recommendation"]] == ["usable"]
    assert "unmeasured" in result["areas"][0]["recommendation"]["reasons"][1]
    assert scan({"housing_areas": result}) == []
    absent = {"status": "not_integrated", "areas": [], "notes": ["Missing data"]}
    assert recommend_housing(absent, {"priority_need": "housing"}) == absent


def test_only_first_three_areas_are_highlighted_but_all_areas_remain_available():
    data = section(*[area(str(index), 1000 + index * 100) for index in range(6)])
    result = recommend_housing(data, {"priority_need": "housing"})
    assert len(result["areas"]) == 6
    assert sum(a["recommendation"]["recommended"] for a in result["areas"]) == 3


def test_job_pin_preserves_exact_worksite_and_marks_city_points_as_approximate(monkeypatch):
    from src.recommend import jobs

    def must_not_resolve(*args, **kwargs):
        raise AssertionError("Known job coordinates should not use the user's area")

    monkeypatch.setattr(jobs, "native_profile", must_not_resolve)
    point = Point(latitude=37.804, longitude=-122.271, precision="worksite", label="Fictional worksite")
    job = Job(job_id="job", title="Warehouse", company="Fictional", city="Oakland", location_text="Oakland", point=point)
    exact = job_map_location(job, "synthetic")
    assert exact["map_precision"] == "worksite" and exact["latitude"] == 37.804
    approximate = job_map_location(job.model_copy(update={"point": point.model_copy(update={"precision": "city_center"})}), "synthetic")
    assert approximate["map_precision"] == "approximate_area"
    assert "Exact worksite coordinates are unavailable" in approximate["map_note"]


def test_job_pin_fallback_uses_job_city_and_missing_coordinates_stay_unavailable(monkeypatch):
    from src.recommend import jobs

    calls = []
    def resolve(request, source):
        calls.append(request["location"])
        return UserProfile(location="Berkeley", priority_need="work", reference_point=
            Point(latitude=37.87, longitude=-122.27, precision="city_center", label="Berkeley city area"))

    monkeypatch.setattr(jobs, "native_profile", resolve)
    job = Job(job_id="job", title="Warehouse", company="Fictional", city="Berkeley", location_text="Berkeley")
    result = job_map_location(job, "synthetic")
    assert calls == ["Berkeley"] and result["map_precision"] == "approximate_area"
    missing = job_map_location(job.model_copy(update={"city": None}), "synthetic")
    assert missing["latitude"] is None and missing["map_precision"] == "unavailable"


def test_public_api_exposes_housing_suggestions_and_selected_job_map_precision(client):
    response = client.post("/recommendations", json={"location": "Oakland", "priority_need": "housing", "selected_job_id": "example-a"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["housing_areas"]["ranking_note"]
    assert any(a["recommendation"] and a["recommendation"]["recommended"] for a in data["housing_areas"]["areas"])
    card = next(j for g in data["jobs"]["groups"] for j in g["items"] if j["job_id"] == "example-a")
    assert card["location"]["map_precision"] == "worksite"
    assert scan(data) == []


def test_privacy_guard_only_allows_labeled_job_points_and_keeps_rental_coordinates_forbidden():
    point = {"latitude": 37.8, "longitude": -122.27, "map_precision": "worksite"}
    response = {"jobs": {"groups": [{"items": [{"location": point}]}]}}
    assert scan(response) == []
    assert scan({"housing_areas": {"areas": [{"location": point}]}})
    assert scan({"user": point})
    assert scan({"jobs": {"groups": [{"items": [{"location": {**point, "map_precision": "unknown"}}]}]}})
    assert scan({"jobs": {"groups": [{"items": [{"location": {**point, "latitude": 999}}]}]}})

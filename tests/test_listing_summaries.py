import pandas as pd

from src.audit.privacy_check import scan
from src.recommend.housing import nearby_places, service_map_points


def place(place_id, **updates):
    return {"place_id": place_id, "name": f"Fictional {place_id}", "city": "Oakland", "zipcode": "94612",
            "lat": 37.804, "lon": -122.271, "family_label": "Job support", "rating": 4.5,
            "reviews_count": 30, "verification_status": "unverified", "maps_url": None,
            "permanently_closed": False, "temporarily_closed": False, **updates}


def test_three_nearby_places_exclude_closed_far_and_duplicate_records():
    services = pd.DataFrame([
        place("verified", verification_status="verified_public_community"),
        place("rated", rating=4.8, reviews_count=100), place("rated", rating=4.8, reviews_count=100),
        place("third"), place("fourth", rating=3), place("closed", permanently_closed=True),
        place("temporary", temporarily_closed=True),
        place("far", zipcode="94704", lat=37.87, lon=-122.26, rating=5),
    ])
    result = nearby_places(services, "Oakland", "94612")
    assert [item["place_id"] for item in result] == ["verified", "rated", "third"]
    assert scan({"housing_areas": {"areas": [{"nearby_places": result}]}}) == []
    assert all(set(item) == {"place_id", "name", "family_label", "maps_url"} for item in result)


def test_unknown_areas_and_missing_place_data_are_not_filled_with_guesses():
    assert nearby_places(pd.DataFrame(), "Oakland", "94612") == []
    assert nearby_places(pd.DataFrame([place("one")]), "Oakland", "94601") == []
    assert nearby_places(pd.DataFrame([place("one", name=None)]), "Oakland", "94612") == []


def test_map_can_show_ten_places_while_the_card_preview_keeps_the_first_three():
    services = pd.DataFrame([
        *[place(f"place-{index:02}", family=f"family-{index % 4}") for index in range(12)],
        place("closed", permanently_closed=True, rating=5),
    ])
    preview = nearby_places(services, "Oakland", "94612")
    expanded = nearby_places(services, "Oakland", "94612", limit=10)
    assert len(expanded) == 10
    assert expanded[:3] == preview
    assert len({item["place_id"] for item in expanded}) == 10
    assert "closed" not in {item["place_id"] for item in expanded}
    areas = [{"nearby_places": expanded}]
    assert len(service_map_points(areas, services)) == 10
    assert scan({"housing_areas": {"areas": areas}, "service_map_points": service_map_points(areas, services)}) == []


def test_small_real_place_list_stays_small_and_handles_missing_ratings():
    services = pd.DataFrame([place("one", rating=None, reviews_count=None)])
    result = nearby_places(services, "Oakland", "94612")
    assert len(result) == 1 and result[0]["name"] == "Fictional one"


def test_nearby_shortlist_covers_distinct_service_families_when_available():
    services = pd.DataFrame([
        place("dentist-a", family="medical", family_label="Dental care", rating=5),
        place("dentist-b", family="medical", family_label="Dental care", rating=5),
        place("library", family="library", family_label="Public library", assistance=True, rating=4.6),
        place("food", family="food", family_label="Food assistance", assistance=True, rating=4.4),
    ])
    result = nearby_places(services, "Oakland", "94612")
    assert [item["place_id"] for item in result] == ["library", "food", "dentist-a"]


def test_map_points_only_expose_the_named_public_places_and_valid_coordinates():
    areas = [{"nearby_places": [{"place_id": "library"}, {"place_id": "missing"}, {"place_id": "invalid"}]}]
    services = pd.DataFrame([
        place("library", lat=37.8, lon=-122.27), place("library", lat=37.8, lon=-122.27),
        place("not-on-shortlist", lat=37.81, lon=-122.26), place("invalid", lat=200, lon=-122.27),
    ])
    points = service_map_points(areas, services)
    assert points == [{"place_id": "library", "lat": 37.8, "lon": -122.27}]
    assert scan({"housing_areas": {"areas": areas}, "service_map_points": points}) == []
    assert service_map_points(areas, pd.DataFrame()) == []
    # Rental coordinates stay forbidden under the housing aggregate contract.
    assert scan({"housing_areas": {"areas": [{"lat": 37.8, "lon": -122.27}]}})


def test_job_description_is_exposed_from_the_selected_dataset(monkeypatch):
    from src.phoenix.models import Job, UserProfile
    from src.recommend import jobs

    source_job = Job(job_id="test-description", title="Warehouse associate", company="Fictional employer",
                     city="Oakland", location_text="Oakland, CA", description="Pack orders and maintain inventory.")
    profile = UserProfile(location="Oakland", priority_need="work")
    monkeypatch.setattr(jobs, "_profile_with_jobs", lambda request, source: (profile, [source_job], []))
    section = jobs.rank_jobs({}, "highest_pay", source="synthetic")
    card = section["groups"][0]["items"][0]
    assert card["description"] == source_job.description
    assert "confirm requirements" not in section["groups"][0]["label"]

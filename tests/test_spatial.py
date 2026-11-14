from pathlib import Path

import pytest

from src.phoenix.housing import summarize_housing
from src.phoenix.ingest import load_records
from src.phoenix.models import Rental, ServiceLocation
from src.phoenix.spatial import attach_service_access


def test_spatial_join_aggregates_and_deduplicates_service_ids():
    rentals = [r.model_copy(update={"latitude": 37.8, "longitude": -122.27})
               for r in load_records(Path("examples/rentals.synthetic.jsonl"), Rental)]
    nearby = ServiceLocation(place_id="synthetic-near", service_family="food", latitude=37.801, longitude=-122.27)
    far = ServiceLocation(place_id="synthetic-far", service_family="food", latitude=38.0, longitude=-122.27)
    closed = nearby.model_copy(update={"place_id": "synthetic-closed", "permanently_closed": True})
    areas, _ = summarize_housing(rentals)
    result = attach_service_access(areas, rentals, [nearby, nearby, far, closed])
    assert all(a.service_access_status == "available" for a in result)
    assert result[0].service_access[0].median_service_count_within_radius == 1
    assert result[0].service_access[0].share_of_properties_with_service == 1
    assert "latitude" not in result[0].model_dump_json()


def test_missing_property_coordinates_do_not_generate_false_access_scores():
    rentals = load_records(Path("examples/rentals.synthetic.jsonl"), Rental)
    areas, _ = summarize_housing(rentals)
    result = attach_service_access(areas, rentals, [])
    assert result[0].service_access_status == "insufficient_coordinates"
    assert not result[0].service_access


def test_conflicting_service_ids_need_resolution_before_join():
    service = ServiceLocation(place_id="same-id", service_family="food", latitude=37.8, longitude=-122.27)
    from src.phoenix.spatial import ServiceIndex
    with pytest.raises(ValueError, match="Conflicting"):
        ServiceIndex([service, service.model_copy(update={"latitude": 38.0})])

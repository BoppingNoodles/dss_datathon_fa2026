import csv
import json
from pathlib import Path

import pytest

from src.phoenix.cli import attach_enrichment
from src.phoenix.housing import summarize_housing
from src.phoenix.ingest import load_records, normalize_job, normalize_rental, prepare_data
from src.phoenix.integration import build_recommendations
from src.phoenix.models import Job, Rental, UserProfile
from src.phoenix.normalization import parse_job_city


def test_geography_does_not_confuse_california_with_bay_area():
    assert parse_job_city("California, MD 20619", "MD") is None
    assert parse_job_city("California City, CA", "CA") is None
    assert parse_job_city("California", "CA") is None
    assert parse_job_city("200 California Hall, Berkeley, CA 94720", "CA") == "Berkeley"
    assert parse_job_city("South San Francisco, CA", "CA") == "South San Francisco"


def rental_row(**updates):
    return {"zpid": "1", "state": "CA", "county": "Alameda County", "city": "Oakland", "zipcode": "94612",
            "homeStatus": "FOR_RENT", "price": "1200", "base_rent": "1200", "currency": "USD", **updates}


def test_sale_prices_and_rent_estimates_are_not_available_rentals():
    row = rental_row(homeStatus="FOR_SALE", price="800000", rentZestimate="1200")
    assert normalize_rental(row, "example.csv", 2)[1] == "not_for_rent"


def test_rent_units_must_be_cross_checked_or_explicitly_unverified():
    row = rental_row(base_rent="")
    assert normalize_rental(row, "example.csv", 2)[1] == "rent_unit_needs_confirmation"
    rental, _ = normalize_rental(row, "example.csv", 2, allow_unverified_rent=True)
    assert rental.rent_basis == "listed_price_unverified"


def test_off_market_rental_does_not_become_an_opportunity():
    assert normalize_rental(rental_row(isOffMarket="true"), "example.csv", 2)[1] == "marked_off_market"


def test_profile_contract_validates_input_and_rejects_extra_fields():
    with pytest.raises(ValueError):
        UserProfile(location="Oakland", priority_need="work", age=-1)
    with pytest.raises(ValueError):
        UserProfile(location="Oakland", priority_need="work", prison_id="123")


def test_housing_suppresses_small_groups_and_avoids_private_fields():
    rentals = load_records(Path("examples/rentals.synthetic.jsonl"), Rental)
    areas, coverage = summarize_housing(rentals[:4])
    assert areas == [] and coverage["status"] == "insufficient_rental_data"
    areas, _ = summarize_housing(rentals)
    assert len(areas) == 2  # City and ZIP views; explicitly overlapping populations.
    public = json.dumps([a.model_dump() for a in areas])
    for private in ["property_id", "latitude", "longitude", "streetAddress"]:
        assert private not in public
    assert all(a.median_monthly_rent == 1450 for a in areas)


def test_duplicate_properties_do_not_defeat_minimum_group_size():
    rentals = load_records(Path("examples/rentals.synthetic.jsonl"), Rental)
    assert summarize_housing([rentals[0]] * 10)[0] == []


def test_response_builder_validates_selected_job_and_does_not_invent_services():
    profile = UserProfile.model_validate_json(Path("examples/profile.synthetic.json").read_text())
    jobs = load_records(Path("examples/jobs.synthetic.jsonl"), Job)
    rentals = load_records(Path("examples/rentals.synthetic.jsonl"), Rental)
    response = build_recommendations(profile, jobs, rentals, data_mode="synthetic", selected_job_id="example-b",
                                    scenario_hours_per_week=40, scenario_weeks_per_year=52)
    assert response.jobs[0].job_id == "example-b"
    assert response.services == [] and response.service_status == "not_connected"
    assert response.housing_comparisons[0]["rent_burden_maximum"] == pytest.approx(1450*12/83200)
    with pytest.raises(ValueError, match="not in this profile"):
        build_recommendations(profile, jobs, rentals, data_mode="synthetic", selected_job_id="not-a-job")


def test_enrichment_joins_by_id_and_rejects_orphans(tmp_path):
    jobs = load_records(Path("examples/jobs.synthetic.jsonl"), Job)
    attached = attach_enrichment(jobs, Path("examples/enrichment.synthetic.jsonl"))
    assert attached[-1].requirements[0].kind == "preferred"
    path = tmp_path / "bad.jsonl"
    path.write_text('{"job_id":"not-present","requirements":[]}\n')
    with pytest.raises(ValueError, match="Unknown"):
        attach_enrichment(jobs, path)


def write_csv(path, rows):
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_streaming_pipeline_deduplicates_and_prefers_unexpired_snapshot(tmp_path):
    job = {"jobid": "a", "job_title": "Warehouse Associate", "company_name": "Example", "location": "Oakland, CA",
           "region": "CA", "description_text": "Warehouse inventory work", "salary_formatted": "$20 an hour"}
    jobs_path, rentals_path = tmp_path / "jobs.csv", tmp_path / "rentals.csv"
    write_csv(jobs_path, [{**job, "is_expired": "true"}, {**job, "is_expired": "false"},
                         {**job, "jobid": "out", "location": "California, MD", "region": "MD"}])
    write_csv(rentals_path, [rental_row(), rental_row(), rental_row(zpid="sale", homeStatus="FOR_SALE")])
    output = tmp_path / "processed"
    report = prepare_data(indeed_paths=[jobs_path], zillow_paths=[rentals_path], output_dir=output, data_mode="sample")
    assert report["retained"] == {"jobs": 1, "rentals": 1, "jobs_not_marked_expired": 1, "jobs_unknown_expiry": 0}
    assert report["sources"][0]["counts"]["outside_or_unresolved_geography"] == 1
    assert load_records(output / "jobs.jsonl", Job)[0].is_expired is False
    assert "streetAddress" not in (output / "rentals.jsonl").read_text()
    # Identical rerun reproduces coverage and normalized output.
    again = prepare_data(indeed_paths=[jobs_path], zillow_paths=[rentals_path], output_dir=output, data_mode="sample")
    assert again == report


def test_schema_drift_is_an_error_not_silently_empty_data(tmp_path):
    path = tmp_path / "wrong.csv"
    write_csv(path, [{"renamed_title": "Warehouse"}])
    with pytest.raises(ValueError, match="required columns missing"):
        prepare_data(indeed_paths=[path], zillow_paths=[], output_dir=tmp_path / "out")


import pandas as pd
import pytest

from src.common import normalize_location_input, parse_categories, parse_city, parse_zip, to_bool
from src.data.places import clean_rating, parse_hours
from src.data.reviews import _guard_columns, aggregate, clean_review_text, clean_star, dedupe_reviews


def test_closure_flags_unknown_stays_unknown():
    assert to_bool("false") is False and to_bool("TRUE") is True
    assert to_bool(None) is None and to_bool(float("nan")) is None and to_bool("maybe") is None


def test_parse_categories_formats():
    assert parse_categories("Food bank", '["Food bank", "Charity"]') == ["Food bank", "Charity"]
    assert parse_categories("['A', 'B']") == ["A", "B"]
    assert parse_categories("A; B | C") == ["A", "B", "C"]
    assert parse_categories(None, float("nan")) == []


def test_address_parsing():
    a = "4546 El Camino Real B10-740, Los Altos, CA 94022, United States"
    assert parse_city(a) == "Los Altos" and parse_zip(a) == "94022"
    assert parse_zip("no zip here") is None and parse_city(None) is None
    assert normalize_location_input("94612") == ("zip", "94612")
    assert normalize_location_input("hayward, CA") == ("city", "Hayward")


def test_zero_rating_placeholder_is_unrated_not_zero_stars():
    assert clean_rating("0", "0") == (None, 0, "unrated_zero_placeholder")
    assert clean_rating("4.5", "12") == (4.5, 12, None)
    assert clean_rating("7", "12")[0] is None
    assert clean_rating("4.0", "0")[0] is None


def test_hours_parsing():
    assert parse_hours('{"Monday":"9 am–5 pm","Sunday":"Closed"}') == "Mon 9 am–5 pm; Sun Closed"
    assert parse_hours("{}") is None and parse_hours(None) is None


def test_review_text_and_stars():
    assert clean_review_text('Positive: "" Negative: ""') is None
    assert clean_review_text("  Kind staff ") == "Kind staff"
    assert clean_star("0") is None and clean_star("5") == 5.0 and clean_star("x") is None


def test_reviewer_identity_columns_are_refused():
    with pytest.raises(ValueError):
        _guard_columns({"review": "reviewer_name"}, ["reviewer", "profile"])


def test_review_dedupe_and_aggregate_keep_sampled_separate():
    df = pd.DataFrame({
        "place_id": ["p1", "p1", "p1", "p2"],
        "review_id": ["a", "a", None, "c"],
        "review_rating": pd.array([5, 5, 3, None], dtype="Float64"),
        "review_text": ["good", "good", None, "ok"],
        "review_date": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-02-01", None], utc=True),
        "place_rating_on_review": pd.array([4.2, 4.2, 4.2, 3.0], dtype="Float64"),
        "place_reviews_count_on_review": pd.array([200, 200, 200, 9], dtype="Int64"),
    })
    out, d = dedupe_reviews(df)
    assert len(out) == 3 and d["duplicate_review_id_rows"] == 1
    agg = aggregate(out).set_index("place_id")
    assert agg.loc["p1", "sampled_review_count"] == 2
    assert agg.loc["p1", "sampled_stars_5"] == 1 and agg.loc["p1", "sampled_stars_3"] == 1
    # The repeated overall count is deduplicated, not summed across review rows.
    assert agg.loc["p1", "overall_count_from_reviews"] == 200
    assert agg.loc["p2", "sampled_rated_count"] == 0


def test_pipeline_on_synthetic(synthetic):
    places, cand, reviews = synthetic["places"], synthetic["candidates"], synthetic["reviews"]
    assert places["place_id"].is_unique  # duplicate place row removed
    assert not any(c.startswith("reviewer") for c in reviews.columns)
    assert "NOT_IN_PLACES" not in set(reviews["place_id"])
    # Left joins: places without sampled reviews or verification remain candidates.
    assert (cand["sampled_review_count"] == 0).any()
    assert (cand["verification_status"] == "unverified").any()
    # Animal shelters are excluded from the housing family by the taxonomy.
    assert not cand["name"].str.contains("Animal Shelter").any()
    # Overall Places counts are untouched by the review sample.
    merged = places.set_index("place_id")["reviews_count"].reindex(cand["place_id"]).values
    assert (pd.Series(merged).fillna(-1).values == cand["reviews_count"].fillna(-1).values).all()
    assert cand.loc[cand["rating"].isna(), "ranking_score"].isna().all()


def test_overall_star_distribution_must_match_count():
    from src.data.places import parse_star_distribution

    j = '{"1_star_reviews":1,"2_star_reviews":0,"3_star_reviews":null,"4_star_reviews":2,"5_star_reviews":7}'
    assert parse_star_distribution(j, 10) == [1, 0, 0, 2, 7]
    assert parse_star_distribution(j, 11) is None  # disagrees with reviews_count -> not shown
    assert parse_star_distribution('{"1_star_reviews":null}', 0) is None


def test_off_topic_places_excluded_but_dentists_and_drugstores_kept():
    from src.recommend.taxonomy import classify

    assert classify(["Medical clinic", "Skin care clinic"])[0] == []
    assert classify(["Massage therapist", "Counseling"])[0] == []
    assert classify(["Coworking space", "Non-profit organization"])[0] == ["social_services"]
    assert "medical_providers" in classify(["Dentist", "Cosmetic dentist"])[0]
    assert "pharmacy" in classify(["Pharmacy", "Health and beauty shop"])[0]

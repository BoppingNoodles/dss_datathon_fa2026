import pandas as pd
import pytest

from src.recommend.build_index import bayes_score
from src.recommend.services import rank_services
from src.recommend.taxonomy import classify


def _all_items(out):
    return [(g["key"], c) for g in out["groups"] for c in g["items"]]


def test_bayes_score_formula_and_monotonicity():
    s = bayes_score(pd.Series([4.8, 4.8, None]), pd.Series([300, 3, 50]), pd.Series([4.0, 4.0, 4.0]), 10)
    assert s[0] == pytest.approx((300 * 4.8 + 10 * 4.0) / 310)
    assert s[0] > s[1]  # same stars, more reviews -> more confidence
    assert pd.isna(s[2])  # no rating -> no score, not a low score
    hi = bayes_score(pd.Series([4.5]), pd.Series([20]), pd.Series([4.0]), 10)[0]
    lo = bayes_score(pd.Series([4.2]), pd.Series([20]), pd.Series([4.0]), 10)[0]
    assert hi > lo


def test_taxonomy_excludes_and_primary():
    assert classify(["Animal shelter"])[0] == []
    assert classify(["Food bank", "Non-profit organization"])[0][0] == "food_assistance"
    assert "banking" not in classify(["Food bank"])[0]
    assert classify(["Bartending school"])[0] == []


def test_groups_are_exclusive_and_well_formed(synthetic):
    out = rank_services(synthetic["candidates"], synthetic["refs"], need="food", location="Oakland", age=30)
    ids = [c["place_id"] for _, c in _all_items(out)]
    assert len(ids) == len(set(ids))
    for key, c in _all_items(out):
        r = c["rating"]
        if key == "highly_rated":
            assert r["overall_rating"] >= 4.0 and r["overall_review_count"] >= 10
        if key == "essential_services":
            assert c["family"] == "grocery"  # ordinary essentials never appear as assistance
        if key != "essential_services":
            assert c["family"] != "grocery"
        assert c["availability"]["permanently_closed"] is not True
        assert c["distance"]["miles"] is None or c["distance"]["reference_point"]


def test_threshold_not_relaxed_and_note_added(synthetic):
    out = rank_services(synthetic["candidates"], synthetic["refs"], need="housing", location="Oakland", age=30)
    highs = [c for k, c in _all_items(out) if k == "highly_rated"]
    assert all(c["rating"]["overall_review_count"] >= 10 for c in highs)
    if len(highs) < 3:
        assert any("threshold was not lowered" in n for n in out["notes"])


def test_permanently_closed_removed_temporarily_closed_separate(synthetic):
    food = rank_services(synthetic["candidates"], synthetic["refs"], need="food", location="Oakland")
    assert any("permanently closed" in n for n in food["notes"])
    health = rank_services(synthetic["candidates"], synthetic["refs"], need="health_care", location="Oakland")
    temp = [c for k, c in _all_items(health) if c["availability"]["temporarily_closed"]]
    assert temp and all(c["group"] == "temporarily_closed" for c in temp)


def test_verified_support_and_age_criteria(synthetic):
    out = rank_services(synthetic["candidates"], synthetic["refs"], need="housing", location="Oakland", age=34)
    verified = [c for k, c in _all_items(out) if k == "verified_support"]
    assert verified and verified[0]["eligibility"]["age_status"] == "outside_published_age_criterion"
    out21 = rank_services(synthetic["candidates"], synthetic["refs"], need="housing", location="Oakland", age=21)
    v21 = [c for k, c in _all_items(out21) if k == "verified_support"][0]
    assert v21["eligibility"]["age_status"] == "meets_published_age_criterion"
    out_none = rank_services(synthetic["candidates"], synthetic["refs"], need="housing", location="Oakland")
    assert [c for k, c in _all_items(out_none) if k == "verified_support"][0]["eligibility"]["age_status"] == "age_not_provided"
    # Unverified places never get an age-based eligibility claim.
    assert all(c["eligibility"]["age_status"] == "eligibility_needs_confirmation"
               for k, c in _all_items(out) if c["verification"]["status"] == "unverified")


def test_age_does_not_change_which_services_are_listed(synthetic):
    a = rank_services(synthetic["candidates"], synthetic["refs"], need="food", location="Oakland", age=19)
    b = rank_services(synthetic["candidates"], synthetic["refs"], need="food", location="Oakland", age=70)
    assert {c["place_id"] for _, c in _all_items(a)} == {c["place_id"] for _, c in _all_items(b)}


def test_nearest_sort_orders_by_distance_and_is_deterministic(synthetic):
    args = dict(need="food", location="Oakland", sort="nearest")
    out = rank_services(synthetic["candidates"], synthetic["refs"], **args)
    for g in out["groups"]:
        d = [c["distance"]["miles"] for c in g["items"] if c["distance"]["miles"] is not None]
        assert d == sorted(d)
    assert out == rank_services(synthetic["candidates"], synthetic["refs"], **args)


def test_highly_rated_sort_uses_score(synthetic):
    out = rank_services(synthetic["candidates"], synthetic["refs"], need="food", location="Berkeley")
    for g in out["groups"]:
        if g["key"] == "highly_rated":
            s = [c["rating"]["ranking_score"] for c in g["items"]]
            assert all(a >= b - 0.02 for a, b in zip(s, s[1:]))


def test_review_snippets_only_from_checked_file(synthetic):
    out = rank_services(synthetic["candidates"], synthetic["refs"], need="food", location="Oakland")
    snippets = [s for _, c in _all_items(out) for s in c["review_evidence"]["snippets"]]
    assert snippets and all(s["attribution"] == "A reviewer reported" for s in snippets)


def test_unknown_location(synthetic):
    out = rank_services(synthetic["candidates"], synthetic["refs"], need="work", location="Fresno")
    assert out["status"] == "no_results"
    assert any("currently covers" in n for n in out["notes"])


def test_overlong_snippets_refused(tmp_path):
    from src.recommend.build_index import load_snippets

    p = tmp_path / "s.csv"
    pd.DataFrame([{"place_id": "x", "snippet": "a" * 201, "topic": "staff", "review_date": None,
                   "checked_by": "me", "checked_on": "2026-11-14"}]).to_csv(p, index=False)
    with pytest.raises(ValueError):
        load_snippets(p)

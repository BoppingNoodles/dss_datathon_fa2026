"""Reproduce fresh/partial teammate checkouts without reading real datasets."""

import json
import shutil

from fastapi.testclient import TestClient
import pytest

from src.common import ROOT


@pytest.fixture
def checkout(tmp_path, monkeypatch, synthetic):
    from backend.app import main
    from src.recommend import oakland_jobs, person1_data

    real = tmp_path / "data/processed/real"
    real.mkdir(parents=True)
    monkeypatch.setattr(main, "ROOT", tmp_path)
    monkeypatch.setattr(person1_data, "processed_dir", lambda source: tmp_path / "data/processed" / source)
    monkeypatch.setattr(person1_data, "INDEED_DIR", tmp_path / "data/processed/indeed")
    monkeypatch.setattr(oakland_jobs, "JOBS_PATH", tmp_path / "data/jobs/oakland_jobs.json")
    monkeypatch.setenv("PHOENIX_SOURCE", "real")
    main.load_data.cache_clear()
    person1_data._load.cache_clear()
    person1_data._load_indeed.cache_clear()
    person1_data._refs.cache_clear()
    yield tmp_path, real, TestClient(main.app)
    main.load_data.cache_clear()
    person1_data._load.cache_clear()
    person1_data._load_indeed.cache_clear()
    person1_data._refs.cache_clear()


def person1(real):
    for name in ("jobs.jsonl", "rentals.jsonl"):
        shutil.copyfile(ROOT / "data/processed/synthetic" / name, real / name)
    (real / "person1_coverage.json").write_text(json.dumps({
        "data_mode": "full", "sources": [], "retained": {"jobs": 3, "rentals": 6}}))


def services(real, synthetic, refs=True):
    synthetic["candidates"].to_parquet(real / "service_candidates.parquet")
    if refs:
        synthetic["refs"].to_parquet(real / "area_reference_points.parquet")


@pytest.mark.parametrize("layout", ["services_only", "indeed_only", "normalized_only", "full", "missing_refs"])
def test_partial_checkout_health_and_recommendations(checkout, synthetic, layout):
    root, real, client = checkout
    if layout in {"services_only", "full", "missing_refs"}:
        services(real, synthetic, refs=layout != "missing_refs")
    if layout in {"normalized_only", "full", "missing_refs"}:
        person1(real)
    if layout == "indeed_only":
        indeed = root / "data/processed/indeed"
        indeed.mkdir()
        shutil.copyfile(ROOT / "examples/jobs.synthetic.jsonl", indeed / "jobs.jsonl")
        (indeed / "coverage.json").write_text(json.dumps({"data_mode": "full", "sources": [{"kind": "jobs", "counts": {"input_rows": 3}}]}))
    health = client.get("/health").json()
    assert health["status"] == ("ok" if layout == "full" else "degraded")
    assert health["project_root"] == str(root)
    assert health["sections"]["jobs"]["status"] == ("missing" if layout == "services_only" else "ready")
    assert health["sections"]["housing"]["status"] == ("missing" if layout in {"services_only", "indeed_only"} else "ready")
    response = client.post("/recommendations", json={"location": "Oakland", "priority_need": "work"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data_coverage"]["mode"] == "real"
    assert body["jobs"]["status"] == ("not_integrated" if layout == "services_only" else "ok")
    assert body["housing_areas"]["status"] == ("not_integrated" if layout in {"services_only", "indeed_only"} else "ok")
    if layout in {"indeed_only", "normalized_only", "missing_refs"}:
        assert body["services"]["status"] == "no_results"
        assert body["services"]["groups"] == []


def test_empty_checkout_is_actionable_503(checkout):
    _, _, client = checkout
    assert client.get("/health").json()["status"] == "degraded"
    response = client.post("/recommendations", json={"location": "Oakland", "priority_need": "food"})
    assert response.status_code == 503
    assert "docs/teammate_setup.md" in response.json()["detail"]


def test_auto_source_detects_normalized_real_without_services(checkout, monkeypatch):
    from backend.app import main

    _, real, _ = checkout
    monkeypatch.delenv("PHOENIX_SOURCE")
    assert main.data_source() == "synthetic"
    person1(real)
    assert main.data_source() == "real"


def test_invalid_mode_and_manifest_are_diagnosed(checkout, monkeypatch):
    _, real, client = checkout
    monkeypatch.setenv("PHOENIX_SOURCE", "typo")
    health = client.get("/health").json()
    assert health["status"] == "degraded" and "PHOENIX_SOURCE" in health["detail"]
    monkeypatch.setenv("PHOENIX_SOURCE", "real")
    person1(real)
    (real / "person1_coverage.json").write_text('{"data_mode":"synthetic"}')
    health = client.get("/health").json()
    assert health["sections"]["housing"]["status"] == "invalid"
    assert "data_mode=full" in health["sections"]["housing"]["detail"]

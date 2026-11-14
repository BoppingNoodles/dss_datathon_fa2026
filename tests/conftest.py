import os

import pandas as pd
import pytest

os.environ["PHOENIX_SOURCE"] = "synthetic"


@pytest.fixture(scope="session")
def synthetic():
    """Build the synthetic fixture through the real pipeline code once per test session."""
    from src.common import processed_dir
    from src.data import make_synthetic, places, reviews
    from src.recommend import build_index

    make_synthetic.build()
    places.run("synthetic")
    reviews.run("synthetic")
    build_index.run("synthetic")
    d = processed_dir("synthetic")
    return {
        "candidates": pd.read_parquet(d / "service_candidates.parquet"),
        "refs": pd.read_parquet(d / "area_reference_points.parquet"),
        "places": pd.read_parquet(d / "places_target.parquet"),
        "reviews": pd.read_parquet(d / "reviews_target.parquet"),
        "agg": pd.read_parquet(d / "review_aggregates.parquet"),
    }


@pytest.fixture(scope="session")
def client(synthetic):
    from fastapi.testclient import TestClient

    from backend.app.main import app, load_data

    load_data.cache_clear()
    return TestClient(app)

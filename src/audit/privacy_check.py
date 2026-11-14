"""Scan public API responses for data that must never be published.

    uv run python -m src.audit.privacy_check --source real

Runs every fictional profile in backend/fixtures/profiles.json through POST /recommendations
and fails if a response contains reviewer identity fields, review/contributor URLs, emails,
or housing property identifiers / coordinates / street addresses. Writes
reports/privacy_check.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from src.common import REPORTS, ROOT, write_json

FORBIDDEN_KEYS = {"reviewer_name", "reviewer_url", "profile_pic_url", "reviews_by_reviewer", "photos_by_reviewer",
                  "local_guide", "response_of_owner", "author", "zpid", "streetAddress", "latitude", "longitude"}
FORBIDDEN_PATTERNS = {
    "contributor_url": re.compile(r"google\.com/maps/contrib/"),
    "reviewer_avatar": re.compile(r"googleusercontent\.com/(a-|a/|local-reviews)"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b", re.IGNORECASE),
}
HOUSING_FORBIDDEN = {"address", "zpid", "lat", "lon", "latitude", "longitude", "url", "streetAddress"}


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k, v
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def scan(response: dict) -> list[str]:
    problems = []
    for p, key, val in walk(response):
        if key in FORBIDDEN_KEYS:
            problems.append(f"forbidden key {p}")
        if isinstance(val, str):
            for name, pat in FORBIDDEN_PATTERNS.items():
                if pat.search(val):
                    problems.append(f"{name} in {p}")
    for p, key, _ in walk(response.get("housing_areas", {})):
        if key in HOUSING_FORBIDDEN:
            problems.append(f"housing field {key} at housing_areas{p}")
    return problems


def run(source: str) -> dict:
    os.environ["PHOENIX_SOURCE"] = source
    from fastapi.testclient import TestClient

    from backend.app.main import app

    client = TestClient(app)
    profiles = json.loads((ROOT / "backend/fixtures/profiles.json").read_text())
    results = []
    for prof in profiles:
        body = {k: v for k, v in prof.items() if not k.startswith("_")}
        r = client.post("/recommendations", json=body)
        problems = scan(r.json()) if r.status_code == 200 else [f"HTTP {r.status_code}"]
        results.append({"profile": prof["_fixture"], "status": r.status_code, "problems": problems})
    report = {"source": source, "passed": all(not x["problems"] for x in results), "results": results}
    write_json(REPORTS / ("privacy_check.json" if source == "real" else f"privacy_check_{source}.json"), report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["real", "synthetic"], default="real")
    rep = run(ap.parse_args().source)
    for x in rep["results"]:
        print(("PASS " if not x["problems"] else "FAIL ") + x["profile"], x["problems"][:5])
    sys.exit(0 if rep["passed"] else 1)


if __name__ == "__main__":
    main()

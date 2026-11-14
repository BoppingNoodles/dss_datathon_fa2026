"""Feasibility-gate summary for Places/Reviews -> reports/places_reviews_coverage.json

    uv run python -m src.audit.coverage_report --source real
"""

from __future__ import annotations

import argparse
import json

from src.common import REPORTS, processed_dir, write_json


def run(source: str) -> dict:
    d = processed_dir(source)
    load = lambda n: json.loads((d / f"{n}.json").read_text())  # noqa: E731
    p, r, i = load("places_stats"), load("reviews_stats"), load("index_stats")
    pri = load("family_rating_priors")
    report = {
        "source": source,
        "places": {k: p[k] for k in ("file", "sha256", "rows_read", "unique_place_ids_full_export",
                                     "target_cities", "target_rows_after_dedupe", "target_duplicate_rows_removed",
                                     "target_by_city", "target_fill_rates", "target_rating_issues", "target_closure",
                                     "fields_absent_or_unmapped")},
        "reviews": {k: r[k] for k in ("file", "sha256", "rows_read", "unique_place_ids_in_reviews",
                                      "row_match_rate_full_places", "target_rows_after_dedupe",
                                      "duplicate_review_id_rows", "duplicate_content_rows",
                                      "target_places_with_sampled_reviews", "target_place_coverage_rate",
                                      "date_min", "date_max")},
        "service_index": i,
        "rating_priors": pri,
    }
    write_json(REPORTS / ("places_reviews_coverage.json" if source == "real" else f"places_reviews_coverage_{source}.json"), report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["real", "synthetic"], default="real")
    rep = run(ap.parse_args().source)
    print(json.dumps({"places_in_target": rep["places"]["target_rows_after_dedupe"],
                      "service_candidates": rep["service_index"]["candidates"],
                      "places_with_sampled_reviews": rep["reviews"]["target_places_with_sampled_reviews"]}, indent=2))


if __name__ == "__main__":
    main()

"""Generate a small, clearly fictional Places/Reviews fixture in the real raw-file format.

    uv run python -m src.data.make_synthetic

Used by tests, CI, and frontend development without the large exports. Every name says
"(synthetic)", streets are "Fixture Ave", websites use the reserved example.org domain, and
the API labels responses built from it as SYNTHETIC. Never present it as real data.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.common import ROOT

OUT = ROOT / "data" / "synthetic"
CITIES = {  # rough area centers used only to scatter fictional points
    "Oakland": (37.804, -122.271, "94612"),
    "Berkeley": (37.871, -122.273, "94704"),
    "Hayward": (37.669, -122.081, "94541"),
}
KINDS = [
    ("Community Food Pantry", "Food bank", ["Food bank", "Non-profit organization"]),
    ("Neighborhood Meal Program", "Soup kitchen", ["Soup kitchen"]),
    ("Family Shelter", "Homeless shelter", ["Homeless shelter", "Social services organization"]),
    ("Workforce Center", "Employment agency", ["Employment agency", "Career counseling"]),
    ("Community Clinic", "Community health center", ["Community health center", "Medical clinic"]),
    ("Recovery Support Center", "Addiction treatment center", ["Addiction treatment center"]),
    ("Corner Grocery", "Grocery store", ["Grocery store"]),
    ("Transit Station", "Transit station", ["Transit station"]),
    ("Animal Shelter", "Animal shelter", ["Animal shelter"]),  # must NOT map to housing
    ("Reentry Services Office", "Social services organization", ["Social services organization", "Non-profit organization"]),
]


def build(seed: int = 7) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    n = 0
    for city, (lat0, lon0, zipc) in CITIES.items():
        for kind, cat, cats in KINDS:
            for k in range(3):
                n += 1
                pid = f"SYN{n:04d}"
                rated = k != 2
                count = int(rng.choice([3, 12, 45, 150])) if rated else 0
                rating = round(float(rng.uniform(3.2, 4.9)), 1) if rated else 0
                rows.append({
                    "place_id": pid, "url": f"https://example.org/maps/{pid}", "country": "United States",
                    "name": f"{city} {kind} {k + 1} (synthetic)", "category": cat,
                    "address": f"{100 + n} Fixture Ave, {city}, CA {zipc}, United States",
                    "open_hours": json.dumps({"Monday": "9 am–5 pm", "Tuesday": "9 am–5 pm"}) if k == 0 else "{}",
                    "reviews_count": count, "rating": rating,
                    "lat": lat0 + rng.normal(0, 0.01), "lon": lon0 + rng.normal(0, 0.01),
                    "open_website": f"https://example.org/{pid}" if k < 2 else None,
                    "phone_number": f"+1 555-01{n % 100:02d}" if k < 2 else None,
                    "permanently_closed": "true" if (kind == "Corner Grocery" and k == 2) else "false",
                    "temporarily_closed": "true" if (kind == "Community Clinic" and k == 1) else "false",
                    "all_categories": json.dumps(cats),
                    "top_reviews": json.dumps([{"content": "x", "reviewer_name": "SHOULD NOT BE READ"}]),
                })
    places = pd.DataFrame(rows)
    places = pd.concat([places, places.iloc[[0]]], ignore_index=True)  # one duplicate place row
    places.to_csv(OUT / "places.csv", index=False)

    reviews = []
    for pid in places["place_id"].unique()[:12]:
        for j in range(4):
            reviews.append({
                "url": f"https://example.org/review/{pid}/{j}", "place_id": pid, "place_name": "x",
                "review_id": f"R{pid}{j}", "reviewer_name": "Synthetic Person (SHOULD NOT BE READ)",
                "reviewer_url": "https://example.org/contrib/1", "review_rating": [5, 4, 0, 3][j],
                "review": ["Staff were kind and the wait was short.", "Positive: \"\" Negative: \"\"",
                           "Helpful with paperwork.", "Long line in the morning."][j],
                "review_date": f"2025-0{j + 1}-15T12:00:00.000Z",
                "response_of_owner": "Thanks Synthetic Person!",
                "place_general_rating": 4.2, "overall_place_riviews": 45,
            })
    reviews.append(dict(reviews[0]))  # an exact duplicate review row
    reviews.append({**reviews[0], "place_id": "NOT_IN_PLACES", "review_id": "RX"})
    pd.DataFrame(reviews).to_csv(OUT / "reviews.csv", index=False)

    pd.DataFrame([
        {"place_id": "SYN0001", "provider_type": "nonprofit_community", "relevant_service": "Food pantry",
         "official_url": "https://example.org/SYN0001", "min_age": None, "max_age": None,
         "age_criteria_text": None, "cost_eligibility_notes": "Free (synthetic)", "service_area": "Oakland",
         "checked_on": "2026-11-14", "checked_by": "synthetic", "notes": "SYNTHETIC"},
        {"place_id": "SYN0007", "provider_type": "public", "relevant_service": "Family shelter",
         "official_url": "https://example.org/SYN0007", "min_age": 18, "max_age": 24,
         "age_criteria_text": "Young adults 18-24", "cost_eligibility_notes": None, "service_area": "Alameda County",
         "checked_on": "2026-11-14", "checked_by": "synthetic", "notes": "SYNTHETIC"},
    ]).to_csv(OUT / "service_verification.csv", index=False)
    pd.DataFrame([{"place_id": "SYN0001", "snippet": "Staff were kind and the wait was short.", "topic": "wait_time",
                   "review_date": "2025-01-15", "checked_by": "synthetic", "checked_on": "2026-11-14"}]
                 ).to_csv(OUT / "review_snippets.csv", index=False)
    return {"places": len(places), "reviews": len(reviews)}


if __name__ == "__main__":
    print(build())

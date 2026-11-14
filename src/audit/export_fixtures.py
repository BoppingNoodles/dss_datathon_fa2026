"""Write example request/response JSON for the frontend (Person 3) from the SYNTHETIC data.

    uv run python -m src.audit.export_fixtures
"""

from __future__ import annotations

import json
import os

from src.common import ROOT


def main() -> None:
    os.environ["PHOENIX_SOURCE"] = "synthetic"
    from fastapi.testclient import TestClient

    from backend.app.main import app

    client = TestClient(app)
    fx = ROOT / "backend" / "fixtures"
    profiles = json.loads((fx / "profiles.json").read_text())
    req = {k: v for k, v in profiles[0].items() if not k.startswith("_")}
    (fx / "recommendation_request.json").write_text(json.dumps(req, indent=2) + "\n")
    resp = client.post("/recommendations", json=req).json()
    (fx / "recommendation_response.synthetic.json").write_text(json.dumps(resp, indent=2) + "\n")
    hc = {"pay_min": 20, "pay_max": 24, "pay_period": "hour", "hours_per_week": None, "monthly_rent": 1650}
    (fx / "housing_comparison_request.json").write_text(json.dumps(hc, indent=2) + "\n")
    (fx / "housing_comparison_response.json").write_text(
        json.dumps(client.post("/housing-comparison", json=hc).json(), indent=2) + "\n")
    print("wrote fixtures to", fx)


if __name__ == "__main__":
    main()

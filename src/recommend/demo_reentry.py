"""Compare the three fictional reentry profiles through the existing API function.

Run `python -m src.recommend.demo_reentry --source synthetic` after make fixtures.
Real mode reuses installed organizer data; all people remain fictional.
"""
import argparse
import json
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["real", "synthetic"], default="synthetic")
    args = parser.parse_args()
    os.environ["PHOENIX_SOURCE"] = args.source
    from backend.app.main import recommendations
    from backend.app.schemas import RecommendationRequest
    from src.common import ROOT

    profiles = json.loads((ROOT / "backend/fixtures/reentry_profiles.json").read_text())
    results = []
    print(f"FICTIONAL PEOPLE. Data mode: {args.source}. No provider acceptance is assumed.")
    for profile in profiles:
        result = recommendations(RecommendationRequest(**{k: v for k, v in profile.items() if not k.startswith("_")}))
        results.append(result)
        plan = result["reentry_plan"]
        by_id = {task.task_id: task for task in plan.tasks}
        print(json.dumps({"profile": profile["_fixture"], "next_three": [
            {"task": by_id[key].title, "priority": by_id[key].priority,
             "stage": by_id[key].stage, "why": by_id[key].rationale,
             "resource_tab": by_id[key].resource_tab, "resource_need": by_id[key].resource_need,
             "prerequisites": by_id[key].prerequisites}
            for key in plan.next_task_ids],
            "dependencies": {task.task_id: task.prerequisites for task in plan.tasks if task.prerequisites},
        }, indent=2, ensure_ascii=False))
    assert all(results[0][key] == results[1][key] for key in ("jobs", "housing_areas", "services"))
    assert results[0]["reentry_plan"].next_task_ids[0] == "reentry:housing-now"
    assert results[1]["reentry_plan"].next_task_ids[0] == "reentry:job-review:browse"
    assert results[2]["reentry_plan"].next_task_ids[:2] == ["reentry:appointment", "reentry:transportation"]
    assert len({tuple(r["reentry_plan"].next_task_ids) for r in results}) == 3
    print("PASS: A needs housing/ID, B prioritizes work, C needs appointment/transport planning; A/B share discovery results.")


if __name__ == "__main__":
    main()

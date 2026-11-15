"""Evaluate a frozen classifier on independently reviewed held-out Indeed rows.

This module never fits a model or selects thresholds. Review labels must be made
from source text before opening predictions. Job-family groups are job contexts,
not demographic fairness or evidence of suitability for returning citizens.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np

from src.data.scrape_indeed import suggest_labels
from src.data.train_indeed import metrics, probabilities
from src.data.validate_indeed import LABELS, load_examples


def held_out(directory: Path, annotations: Path):
    csv.field_size_limit(16 * 1024 * 1024)
    with annotations.open(encoding="utf-8-sig", newline="") as file:
        reviewed = list(csv.DictReader(file))
    wanted = {}
    ids = set()
    for row in reviewed:
        index = int(row["row"])
        if row["split"] != "test" or index < 1 or index in wanted or row["jobid"] in ids:
            raise ValueError("Unique test-only annotation rows and job IDs are required")
        if set(row[k] for k in LABELS) - {"0", "1", "?"}:
            raise ValueError("Each label must be 0, 1, or ?")
        wanted[index] = row
        ids.add(row["jobid"])
    examples = []
    with (directory / "test.csv").open(encoding="utf-8-sig", newline="") as file:
        for index, row in enumerate(csv.DictReader(file), 1):
            if index not in wanted:
                continue
            annotation = wanted[index]
            if row["jobid"] != annotation["jobid"] or hashlib.sha256(row["description_text"].encode()).hexdigest() != annotation["description_sha256"]:
                raise ValueError(f"Source mismatch at test:{index}")
            examples.append((row["description_text"], annotation))
    if not examples or len(examples) != len(wanted):
        raise ValueError("Missing held-out source rows")
    return examples


def error_rates(truth, predicted):
    result = metrics(truth, predicted)
    for column, label in enumerate(LABELS):
        known = truth[:, column] != "?"
        expected, guesses = truth[known, column] == "1", predicted[known, column]
        tp, tn = int((expected & guesses).sum()), int((~expected & ~guesses).sum())
        fp, fn = int((~expected & guesses).sum()), int((expected & ~guesses).sum())
        result["labels"][label].update(tp=tp, tn=tn, fp=fp, fn=fn,
            false_positive_rate=fp / (fp + tn) if fp + tn else None,
            false_negative_rate=fn / (fn + tp) if fn + tp else None)
    return result


def evaluate(directory: Path, artifact_directory: Path, development: Path, annotations: Path):
    manifest = json.loads((artifact_directory / "manifest.json").read_text())
    artifact_path = artifact_directory / "tfidf.joblib"
    if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != manifest["model_sha256"]:
        raise ValueError("Artifact differs from the model frozen before test review")
    if hashlib.sha256(development.read_bytes()).hexdigest() != manifest["development_annotations_sha256"]:
        raise ValueError("Development annotations differ from frozen training inputs")
    examples = held_out(directory, annotations)
    truth = np.array([[row[label] for label in LABELS] for _, row in examples])
    texts = [text for text, _ in examples]
    artifact = joblib.load(artifact_path)  # Trusted, locally trained artifact only.
    scores = probabilities(artifact["heads"], artifact["vectorizer"].transform(texts))
    cutoffs = artifact.get("thresholds", [.5] * len(LABELS))
    train = load_examples(directory, [development])["train"]
    majority = np.array([sum(row[1][c] == "1" for row in train) > sum(row[1][c] == "0" for row in train) for c in range(len(LABELS))])
    rules = [suggest_labels(text) for text in texts]
    predictions = {"tfidf": scores >= cutoffs,
                   "majority": np.tile(majority, (len(texts), 1)),
                   "scraper": np.array([[r[f"{label}_suggested"] == "1" for label in LABELS] for r in rules])}
    families = sorted({row["job_family"] for _, row in examples})
    report = {"model_sha256": manifest["model_sha256"], "test_annotations_sha256": hashlib.sha256(annotations.read_bytes()).hexdigest(),
              "test_postings": len(texts), "thresholds": cutoffs, "models": {}, "errors": []}
    for name, guesses in predictions.items():
        groups = {}
        for family in families:
            indexes = [i for i, (_, row) in enumerate(examples) if row["job_family"] == family]
            groups[family] = {"postings": len(indexes), **error_rates(truth[indexes], guesses[indexes])}
        report["models"][name] = {"overall": error_rates(truth, guesses), "subgroups": groups}
        for i, (_, row) in enumerate(examples):
            errors = [label for c, label in enumerate(LABELS) if truth[i, c] != "?" and (truth[i, c] == "1") != guesses[i, c]]
            if errors:
                report["errors"].append({"model": name, "row": int(row["row"]), "jobid": row["jobid"], "job_family": row["job_family"], "incorrect_labels": errors})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split_directory", type=Path)
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument("development_annotations", type=Path)
    parser.add_argument("test_annotations", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.split_directory, args.artifact_directory, args.development_annotations, args.test_annotations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: round(v["overall"]["macro_f1"], 4) for k, v in report["models"].items()}))


if __name__ == "__main__":
    main()

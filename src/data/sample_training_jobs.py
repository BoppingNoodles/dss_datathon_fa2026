"""Prepare training annotations with scraper suggestions in separate columns."""

import argparse
import csv
import heapq
import random
import re
from pathlib import Path

from scrape_indeed import LABEL_PATTERNS, suggest_labels
from split_indeed import normalize


FAMILIES = {
    "logistics_warehouse": re.compile(r"\b(?:warehouse|forklift|order picker|material handler|shipping clerk)\b", re.I),
    "retail_customer_service": re.compile(r"\b(?:retail|cashier|sales associate|customer service|store associate)\b", re.I),
    "food_service_hospitality": re.compile(r"\b(?:restaurant|cook|chef|barista|food service|housekeeper|hospitality)\b", re.I),
}
PER_FOLD_FAMILY = 15


def sample(directory, output):
    csv.field_size_limit(16 * 1024 * 1024)
    with (directory / "pilot_annotations.csv").open(encoding="utf-8-sig", newline="") as stream:
        pilot_ids = {row["jobid"] for row in csv.DictReader(stream) if row["split"] == "train"}
    with (directory / "train_folds.csv").open(encoding="utf-8-sig", newline="") as stream:
        folds = {int(row["train_row"]): (int(row["fold"]), row["jobid"]) for row in csv.DictReader(stream)}

    rng = random.Random(42)
    buckets = {(fold, family): [] for fold in range(1, 6) for family in FAMILIES}
    with (directory / "train.csv").open(encoding="utf-8-sig", newline="") as stream:
        for index, row in enumerate(csv.DictReader(stream), 1):
            fold, job_id = folds[index]
            if job_id != row["jobid"]:
                raise ValueError(f"Training manifest mismatch at row {index}.")
            if not job_id or job_id in pilot_ids or not row["description_text"].strip():
                continue
            families = [key for key, pattern in FAMILIES.items() if pattern.search(row["job_title"])]
            if len(families) != 1:
                continue
            bucket = buckets[fold, families[0]]
            entry = (rng.random(), index, job_id, row["job_title"], row["company_name"], row["description_text"])
            if len(bucket) < PER_FOLD_FAMILY * 10:
                heapq.heappush(bucket, entry)
            else:
                heapq.heappushpop(bucket, entry)

    selected = []
    ids, reposts, descriptions = set(), set(), set()
    for (fold, family), bucket in buckets.items():
        count = 0
        for _, index, job_id, title, employer, text in sorted(bucket, reverse=True):
            repost = (normalize(title), normalize(employer)) if employer.strip() else None
            description = normalize(text)
            if job_id in ids or repost in reposts or description in descriptions:
                continue
            selected.append((index, job_id, fold, family, title, text))
            ids.add(job_id)
            if repost is not None:
                reposts.add(repost)
            descriptions.add(description)
            count += 1
            if count == PER_FOLD_FAMILY:
                break
        if count != PER_FOLD_FAMILY:
            raise ValueError(f"Only {count} unique training postings for fold {fold}, family {family}.")

    rng.shuffle(selected)
    fields = ["split", "row", "jobid", *LABEL_PATTERNS, "notes", "fold", "job_family", "job_title", "description_text"]
    suggestions = [f"{label}_{suffix}" for label in LABEL_PATTERNS for suffix in ("suggested", "evidence")]
    with output.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields + suggestions)
        writer.writeheader()
        for index, job_id, fold, family, title, text in selected:
            row = {"split": "train", "row": index, "jobid": job_id, "fold": fold, "job_family": family,
                   "job_title": title, "description_text": text, **suggest_labels(text)}
            # Protect free text when loading the annotation sheet in a spreadsheet program.
            for key, value in row.items():
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    row[key] = "'" + value
            writer.writerow(row)
    return len(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split_directory", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()
    print(f"Wrote {sample(args.split_directory, args.output_csv)} postings to {args.output_csv}")


if __name__ == "__main__":
    main()

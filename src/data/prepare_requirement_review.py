"""Prepare a reproducible, group-isolated annotation cohort from organizer Indeed.

No scraper predictions or labels enter the review files. Training alone is
enriched for credential wording; validation/test are hash-sampled within family.
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from src.data.split_indeed import split_csv
from src.phoenix.qualifications import redact_contacts

FAMILIES = {
    "logistics_warehouse": re.compile(r"\b(?:warehouse|forklift|order picker|material handler|shipping clerk)\b", re.I),
    "retail_customer_service": re.compile(r"\b(?:retail|cashier|sales associate|customer service|store associate)\b", re.I),
    "food_service_hospitality": re.compile(r"\b(?:restaurant|cook|chef|barista|food service|housekeeper|hospitality)\b", re.I),
}
CREDENTIAL_CUE = re.compile(r"\b(?:license|licensed|certification|certified|CDL|ServSafe|food handler|diploma|GED)\b", re.I)


def prepare(source: Path, output: Path, seed: int = 20261114):
    csv.field_size_limit(16 * 1024 * 1024)
    output.mkdir(parents=True, exist_ok=False)
    corpus = output / "corpus.csv"
    fields = ["jobid", "job_title", "company_name", "location", "description_text"]
    with source.open(encoding="utf-8-sig", newline="") as src, corpus.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=fields)
        writer.writeheader()
        for row in csv.DictReader(src):
            projected = {key: row.get(key, "") for key in fields}
            projected["description_text"] = redact_contacts(projected["description_text"])
            writer.writerow(projected)
    directory = output / "splits"
    counts, sizes = split_csv(corpus, directory, seed)
    with (directory / "train_folds.csv").open() as stream:
        folds = {int(r["train_row"]): int(r["fold"]) for r in csv.DictReader(stream)}
    selected_ids, selected_texts = set(), set()
    samples = {}
    for split in ("train", "validation", "test"):
        buckets = {}
        with (directory / f"{split}.csv").open(encoding="utf-8", newline="") as stream:
            for index, row in enumerate(csv.DictReader(stream), 1):
                text = row["description_text"]
                if not 250 <= len(text) <= 1500:
                    continue
                families = [key for key, pattern in FAMILIES.items() if pattern.search(row["job_title"])]
                if len(families) != 1:
                    continue
                fold = folds[index] if split == "train" else 0
                entry = {"split": split, "row": index, "jobid": row["jobid"], "fold": fold,
                         "job_family": families[0], "job_title": row["job_title"], "description_text": text}
                rank = hashlib.sha256(f"{seed}:{split}:{index}:{row['jobid']}".encode()).hexdigest()
                buckets.setdefault((fold, families[0]), []).append((rank, entry))
        chosen = []
        for key, entries in sorted(buckets.items()):
            entries.sort(key=lambda item: item[0])
            wanted = 4 if split == "train" else 5 if split == "validation" else 10
            # Deliberate training-only enrichment to expose sparse credentials.
            candidates = ([item for item in entries if CREDENTIAL_CUE.search(item[1]["description_text"])][:2]
                          + entries) if split == "train" else entries
            count = 0
            for _, entry in candidates:
                fingerprint = " ".join(entry["description_text"].lower().split())
                if entry["jobid"] in selected_ids or fingerprint in selected_texts:
                    continue
                chosen.append(entry)
                selected_ids.add(entry["jobid"])
                selected_texts.add(fingerprint)
                count += 1
                if count == wanted:
                    break
            if count != wanted:
                raise ValueError(f"Only {count}/{wanted} review candidates for {split}/{key}")
        expected = 60 if split == "train" else 15 if split == "validation" else 30
        if len(chosen) != expected:
            raise ValueError(f"Expected {expected} review rows in {split}, got {len(chosen)}")
        target = output / f"review_{split}.jsonl"
        target.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in chosen), encoding="utf-8")
        samples[split] = [{k: v for k, v in entry.items() if k != "description_text"} for entry in chosen]
    with source.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {"source_name": source.name, "source_sha256": checksum, "seed": seed, "splits": counts,
                "fold_sizes": sizes, "description_length_range": [250, 1500], "training_credential_enrichment": True,
                "review_samples": samples}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    deduplicate_reviews(output)


def deduplicate_reviews(output: Path):
    """Conservatively withhold near-duplicate review texts across folds/splits.

    Training is visited first, then validation, then test. This uses no labels or
    predictions. Short-description cohorts have repeated employer templates.
    """
    seen = []
    manifest = json.loads((output / "manifest.json").read_text())
    removed, samples = [], {}
    for split in ("train", "validation", "test"):
        path = output / f"review_{split}.jsonl"
        kept = []
        for line in path.read_text().splitlines():
            row = json.loads(line)
            words = set(re.findall(r"\w+", row["description_text"].lower()))
            duplicate = next((key for key, earlier in seen if len(words & earlier) / max(1, len(words | earlier)) >= .9), None)
            if duplicate is not None:
                removed.append({"split": split, "row": row["row"], "near_duplicate_of": duplicate})
                continue
            seen.append((f"{split}:{row['row']}", words))
            kept.append(row)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept))
        samples[split] = [{k: v for k, v in row.items() if k != "description_text"} for row in kept]
    manifest["review_samples"] = samples
    manifest["near_duplicate_jaccard_threshold"] = .9
    manifest["withheld_near_duplicates"] = list({(r["split"], r["row"]): r for r in [*manifest.get("withheld_near_duplicates", []), *removed]}.values())
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"split_counts": manifest["splits"], "review_counts": {k: len(v) for k, v in samples.items()}, "withheld_near_duplicates": len(removed)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--deduplicate-only", action="store_true")
    args = parser.parse_args()
    if args.deduplicate_only:
        deduplicate_reviews(args.output)
    else:
        prepare(args.source, args.output, args.seed)


if __name__ == "__main__":
    main()

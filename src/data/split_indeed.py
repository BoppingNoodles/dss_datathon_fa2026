"""Write group-isolated Indeed CSV splits and five training-fold assignments."""

import argparse
import csv
import hashlib
import random
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory


SPLITS = ("train", "validation", "test")
GROUP_COLUMNS = ("job_title", "company_name", "location")


def normalize(text):
    return " ".join(text.casefold().split())


def read_groups(source):
    parents = []
    sizes = []
    first_rows = {}

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        needed = {"jobid", "description_text", *GROUP_COLUMNS}
        if not needed.issubset(reader.fieldnames or []):
            raise ValueError(f"Expected input columns: {sorted(needed)}")
        for index, row in enumerate(reader):
            if None in row or None in row.values():
                raise ValueError(f"Unexpected number of fields at CSV line {reader.line_num}")
            parents.append(index)
            sizes.append(1)
            group = tuple(normalize(row[column]) for column in GROUP_COLUMNS)
            description = normalize(row["description_text"])
            keys = []
            if all(group):
                keys.append(("repost", group))
            if row["jobid"].strip():
                keys.append(("jobid", row["jobid"].strip()))
            if description:
                keys.append(("description", hashlib.sha256(description.encode()).digest()))
            for key in keys:
                other = root(first_rows.setdefault(key, index))
                current = root(index)
                if current == other:
                    continue
                if sizes[current] < sizes[other]:
                    current, other = other, current
                parents[other] = current
                sizes[current] += sizes[other]

    groups = defaultdict(list)
    for index in range(len(parents)):
        groups[root(index)].append(index)
    return list(groups.values()), len(parents)


def allocate(groups, targets, rng):
    """Place large groups first, then fill the remaining capacity with small groups."""
    groups = list(groups)
    rng.shuffle(groups)
    groups.sort(key=len, reverse=True)
    buckets = [[] for _ in targets]
    remaining = list(targets)
    for group in groups:
        index = max(range(len(targets)), key=remaining.__getitem__)
        buckets[index].append(group)
        remaining[index] -= len(group)
    return buckets


def split_csv(source, destination, seed):
    csv.field_size_limit(16 * 1024 * 1024)
    rng = random.Random(seed)
    groups, total = read_groups(source)
    if len(groups) < 7:
        raise ValueError("Need at least seven independent posting groups for three splits and five folds.")
    # Round cumulative boundaries so all target counts add up to the source count.
    train_target = round(total * 0.70)
    development_target = round(total * 0.85)
    partitions = allocate(groups, [train_target, development_target - train_target, total - development_target], rng)
    train_size = sum(map(len, partitions[0]))
    quotient, remainder = divmod(train_size, 5)
    folds = allocate(partitions[0], [quotient + (i < remainder) for i in range(5)], rng)
    if any(not bucket for bucket in [*partitions, *folds]):
        raise ValueError("Too few independent groups to populate every split and fold.")

    split_by_row = [None] * total
    for name, partition in zip(SPLITS, partitions):
        for group in partition:
            for row_index in group:
                split_by_row[row_index] = name
    fold_by_row = {row: fold for fold, bucket in enumerate(folds, 1) for group in bucket for row in group}

    if destination.exists():
        raise ValueError(f"Output directory already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as scratch:
        staged = Path(scratch) / "splits"
        staged.mkdir()
        counts = dict.fromkeys(SPLITS, 0)
        with ExitStack() as stack:
            stream = stack.enter_context(source.open(encoding="utf-8-sig", newline=""))
            reader = csv.DictReader(stream, strict=True)
            writers = {}
            for name in SPLITS:
                output = stack.enter_context((staged / f"{name}.csv").open("w", encoding="utf-8", newline=""))
                writers[name] = csv.DictWriter(output, fieldnames=reader.fieldnames)
                writers[name].writeheader()
            manifest = stack.enter_context((staged / "train_folds.csv").open("w", encoding="utf-8", newline=""))
            fold_writer = csv.writer(manifest)
            fold_writer.writerow(["train_row", "jobid", "fold"])
            for index, row in enumerate(reader):
                split = split_by_row[index]
                writers[split].writerow(row)
                counts[split] += 1
                if split == "train":
                    fold_writer.writerow([counts[split], row["jobid"], fold_by_row[index]])
        if sum(counts.values()) != total:
            raise ValueError("The source row count changed between passes.")
        staged.rename(destination)
    return counts, [sum(map(len, fold)) for fold in folds]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--seed", default=42, type=int)
    args = parser.parse_args()
    try:
        counts, folds = split_csv(args.source, args.destination, args.seed)
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, f"Error: {error}\n")
    for name, count in counts.items():
        print(f"{name}: {count:,} ({count / sum(counts.values()):.2%})")
    print("Training fold sizes:", ", ".join(f"{size:,}" for size in folds))


if __name__ == "__main__":
    main()

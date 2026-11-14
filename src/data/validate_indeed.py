"""Run pilot validation on annotated train and validation rows only."""

import argparse
import csv
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

if __package__:
    from .scrape_indeed import LABEL_PATTERNS, suggest_labels
else:
    from scrape_indeed import LABEL_PATTERNS, suggest_labels


LABELS = tuple(LABEL_PATTERNS)


def load_examples(directory, annotations):
    csv.field_size_limit(16 * 1024 * 1024)
    pending = {"train": {}, "validation": {}}
    for path in [annotations] if isinstance(annotations, Path) else annotations:
        with path.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                split, index = row["split"], int(row["row"])
                if split not in pending:
                    raise ValueError("Only train and validation annotations are accepted.")
                if index < 1 or index in pending[split]:
                    raise ValueError(f"Invalid or duplicate annotation row {split}:{index}")
                labels = tuple(row[label].strip() for label in LABELS)
                if all(not label for label in labels):
                    continue
                if set(labels) - {"0", "1", "?"}:
                    raise ValueError(f"Invalid or incomplete annotation labels at {split}:{index}")
                pending[split][index] = (row["jobid"], labels)
    with (directory / "train_folds.csv").open(encoding="utf-8", newline="") as file:
        folds = {int(r["train_row"]): int(r["fold"]) for r in csv.DictReader(file)}
    examples = {}
    for split, wanted in pending.items():
        if not wanted:
            raise ValueError(f"No annotations for {split}.")
        examples[split] = []
        with (directory / f"{split}.csv").open(encoding="utf-8", newline="") as file:
            for index, row in enumerate(csv.DictReader(file), 1):
                annotation = wanted.get(index)
                if annotation is None:
                    continue
                jobid, labels = annotation
                if jobid != row["jobid"]:
                    raise ValueError(f"Job ID mismatch at {split}:{index}.")
                fold = folds[index] if split == "train" else 0
                examples[split].append((row["description_text"], labels, fold))
                if len(examples[split]) == len(wanted):
                    break
        if len(examples[split]) != len(wanted):
            raise ValueError(f"Some annotated {split} rows were not found.")
    return examples


def model_predictions(fit, evaluate):
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
    train_matrix = vectorizer.fit_transform([text for text, _, _ in fit])
    eval_matrix = vectorizer.transform([text for text, _, _ in evaluate])
    predictions = []
    for column in range(len(LABELS)):
        known = [i for i, (_, labels, _) in enumerate(fit) if labels[column] != "?"]
        values = [fit[i][1][column] for i in known]
        classes = set(values)
        if len(classes) < 2:
            # A sparse pilot fold can contain only one observed class for a label.
            predictions.append([next(iter(classes), "review")] * len(evaluate))
            continue
        model = LogisticRegression(class_weight="balanced", max_iter=1000)
        model.fit(train_matrix[known], values)
        predictions.append(model.predict(eval_matrix))
    return list(zip(*predictions))


def score(name, examples, predictions):
    known = [(truth, prediction) for (_, labels, _), guesses in zip(examples, predictions)
             for truth, prediction in zip(labels, guesses) if truth != "?"]
    decided = [(truth, guess) for truth, guess in known if guess != "review"]
    correct = sum(truth == guess for truth, guess in decided)
    # Treat review as a missed positive for recall while still reporting coverage.
    positive_f1 = f1_score([truth == "1" for truth, _ in known],
                           [guess == "1" for _, guess in known], zero_division=0)
    print(f"{name}: {correct}/{len(known)} correct, {len(known) - len(decided)} review, "
          f"""{sum(truth == '1' for truth, _ in known)} positives, positive-label micro-F1 {positive_f1:.3f}""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split_directory", type=Path)
    parser.add_argument("annotations_csv", type=Path)
    args = parser.parse_args()
    examples = load_examples(args.split_directory, args.annotations_csv)
    train, validation = examples["train"], examples["validation"]
    out_of_fold, predictions = [], []
    for fold in range(1, 6):
        fit = [row for row in train if row[2] != fold]
        held = [row for row in train if row[2] == fold]
        if not fit or not held:
            raise ValueError(f"Need annotated training rows on both sides of fold {fold}.")
        guesses = model_predictions(fit, held)
        score(f"TF-IDF fold {fold}", held, guesses)
        out_of_fold.extend(held)
        predictions.extend(guesses)
    score("TF-IDF pooled out of fold", out_of_fold, predictions)
    score("TF-IDF validation", validation, model_predictions(train, validation))
    rule_predictions = [suggest_labels(text) for text, _, _ in validation]
    score("Rule labeler validation", validation,
          [tuple(result[f"{label}_suggested"] for label in LABELS) for result in rule_predictions])


if __name__ == "__main__":
    main()

"""Train, compare, and save job-requirement classifiers using development data."""

import argparse
import json
import re
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support

from .scrape_indeed import suggest_labels
from .validate_indeed import LABELS, load_examples


ENCODER = "sentence-transformers/all-MiniLM-L6-v2"
ENCODER_REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"


def minilm_features(texts):
    from sentence_transformers import SentenceTransformer

    encoder = SentenceTransformer(ENCODER, revision=ENCODER_REVISION, device="cpu")
    tokenizer = encoder.tokenizer
    limit = encoder.max_seq_length - tokenizer.num_special_tokens_to_add()
    chunks, counts = [], []
    for text in texts:
        start = len(chunks)
        pending = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            tokens = tokenizer.encode(sentence, add_special_tokens=False, verbose=False)
            if pending and len(pending) + len(tokens) > limit:
                chunks.append(tokenizer.decode(pending))
                pending = []
            for offset in range(0, len(tokens), limit):
                part = tokens[offset:offset + limit]
                if len(part) == limit:
                    chunks.append(tokenizer.decode(part))
                else:
                    pending.extend(part)
        if pending or len(chunks) == start:
            chunks.append(tokenizer.decode(pending))
        counts.append(len(chunks) - start)
    embeddings = encoder.encode(chunks, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    boundaries = np.cumsum(counts)[:-1]
    return np.stack([posting.mean(axis=0) for posting in np.split(embeddings, boundaries)])


def probabilities(heads, matrix):
    return np.column_stack([
        head.predict_proba(matrix)[:, 1] if isinstance(head, LogisticRegression)
        else np.full(matrix.shape[0], head)
        for head in heads
    ])


def fit_predict(kind, train, held, texts, labels, embeddings):
    vectorizer = None
    if kind == "tfidf":
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
        matrix = vectorizer.fit_transform([texts[i] for i in train])
        target = vectorizer.transform([texts[i] for i in held])
    elif kind == "minilm":
        matrix, target = embeddings[train], embeddings[held]
    else:
        matrix, target = np.empty((len(train), 0)), np.empty((len(held), 0))

    heads = []
    for column in range(len(LABELS)):
        values = labels[train, column]
        known = values != "?"
        observed = values[known] == "1"
        if kind == "majority" or len(set(observed)) < 2:
            heads.append(float(observed.mean() > 0.5) if observed.size else 0.0)
        else:
            heads.append(LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
                         .fit(matrix[known], observed))
    return {"kind": kind, "vectorizer": vectorizer, "heads": heads, "labels": LABELS}, probabilities(heads, target)


def metrics(truth, predictions):
    result = {}
    for column, label in enumerate(LABELS):
        known = truth[:, column] != "?"
        expected = truth[known, column] == "1"
        precision, recall, f1, _ = precision_recall_fscore_support(
            expected, predictions[known, column], average="binary", zero_division=0,
        )
        result[label] = {"precision": precision, "recall": recall, "f1": f1,
                         "positives": int(expected.sum()), "scored": int(known.sum())}
    known = truth != "?"
    _, _, micro_f1, _ = precision_recall_fscore_support(
        truth[known] == "1", predictions[known], average="binary", zero_division=0,
    )
    return {"macro_f1": float(np.mean([v["f1"] for v in result.values()])), "micro_f1": micro_f1, "labels": result}


def train_models(examples, use_minilm):
    train, validation = examples["train"], examples["validation"]
    texts = [row[0] for row in train + validation]
    labels = np.array([row[1] for row in train + validation])
    folds = np.array([row[2] for row in train])
    if set(folds) != set(range(1, 6)):
        raise ValueError("Provide labeled training examples in all five folds.")
    train_indices = np.arange(len(train))
    validation_indices = np.arange(len(train), len(texts))
    embeddings = minilm_features(texts) if use_minilm else None
    artifacts, scores = {}, {}
    for kind in ("majority", "tfidf", "minilm") if use_minilm else ("majority", "tfidf"):
        oof = np.empty((len(train), len(LABELS)))
        per_fold = {}
        for fold in range(1, 6):
            held = train_indices[folds == fold]
            _, scores_for_fold = fit_predict(kind, train_indices[folds != fold], held, texts, labels, embeddings)
            oof[held] = scores_for_fold
            per_fold[str(fold)] = metrics(labels[held], scores_for_fold >= 0.5)
        artifact, val_scores = fit_predict(kind, train_indices, validation_indices, texts, labels, embeddings)
        artifacts[kind] = artifact
        scores[kind] = {"folds": per_fold, "out_of_fold": metrics(labels[train_indices], oof >= 0.5),
                        "validation": metrics(labels[validation_indices], val_scores >= 0.5)}
    rules = [suggest_labels(text) for text in texts[len(train):]]
    scores["scraper"] = {"validation": metrics(labels[validation_indices], np.array([
        [row[f"{label}_suggested"] == "1" for label in LABELS] for row in rules
    ]))}
    return artifacts, scores


def predict(artifact, description):
    if not description.strip():
        raise ValueError("A nonempty job description is required.")
    matrix = (minilm_features([description]) if artifact["kind"] == "minilm"
              else artifact["vectorizer"].transform([description]))
    return {label: bool(score >= 0.5) for label, score in zip(artifact["labels"], probabilities(artifact["heads"], matrix)[0])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("split_directory", type=Path)
    train.add_argument("output_directory", type=Path)
    train.add_argument("annotations", type=Path, nargs="+")
    train.add_argument("--minilm", action="store_true")
    infer = commands.add_parser("predict")
    infer.add_argument("artifact", type=Path)
    infer.add_argument("description_file", type=Path)
    args = parser.parse_args()
    if args.command == "predict":
        print(json.dumps(predict(joblib.load(args.artifact), args.description_file.read_text(encoding="utf-8-sig")), indent=2))
        return
    examples = load_examples(args.split_directory, args.annotations)
    artifacts, scores = train_models(examples, args.minilm)
    args.output_directory.mkdir(parents=True, exist_ok=False)
    for kind, artifact in artifacts.items():
        if kind != "majority":
            joblib.dump(artifact, args.output_directory / f"{kind}.joblib")
    report = {"train_postings": len(examples["train"]), "validation_postings": len(examples["validation"]),
              "scikit_learn": sklearn.__version__, "threshold": 0.5,
              "encoder_revision": ENCODER_REVISION if args.minilm else None, "models": scores}
    (args.output_directory / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for kind, results in scores.items():
        print(f"{kind}: validation macro-F1 {results['validation']['macro_f1']:.3f}")


if __name__ == "__main__":
    main()

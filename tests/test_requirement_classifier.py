import csv
import hashlib

import numpy as np
import pytest

from src.data.evaluate_requirements import held_out, error_rates
from src.data.train_indeed import select_thresholds


def test_held_out_loader_requires_test_ids_and_source_checksum(tmp_path):
    fields = ["jobid", "description_text"]
    with (tmp_path / "test.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerow({"jobid": "fictional", "description_text": "A diploma is required."})
    path = tmp_path / "labels.csv"
    row = dict(split="test", row=1, jobid="fictional", education_required="1", experience_required="0", certification_required="?",
               description_sha256=hashlib.sha256(b"A diploma is required.").hexdigest(), job_family="warehouse")
    def write():
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row)); writer.writeheader(); writer.writerow(row)
    write()
    assert len(held_out(tmp_path, path)) == 1
    row["description_sha256"] = "changed"; write()
    with pytest.raises(ValueError, match="Source mismatch"): held_out(tmp_path, path)
    row["split"] = "train"; write()
    with pytest.raises(ValueError, match="test-only"): held_out(tmp_path, path)


def test_metrics_exclude_unresolved_labels_and_expose_false_positives():
    truth = np.array([["1", "0", "?"], ["0", "1", "0"]])
    predictions = np.array([[True, True, True], [True, False, False]])
    result = error_rates(truth, predictions)
    assert result["labels"]["certification_required"]["scored"] == 1
    assert result["labels"]["education_required"]["fp"] == 1
    assert result["labels"]["experience_required"]["fn"] == 1
    thresholds = select_thresholds(truth, np.array([[.8, .4, .9], [.1, .8, .1]]))
    assert thresholds == [.5, .5, .5]

# Requirement classifier v1 — reproducible pilot, 2026-11-14

The missing model artifact is now present at `models/requirements_v1/tfidf.joblib` (434,613 bytes). It is an actually fitted TF-IDF + logistic-regression classifier, not the scraper or an LLM. Its performance is insufficient for automatic qualification decisions. Existing evidence-bearing rules remain stronger evidence; the classifier only supports uncertain confirmation/preparation prompts.

## Data and reference labels

The source is the organizer's `indeed_job_listings.csv`: 140,816 postings. `prepare_requirement_review.py` projects the job ID, title, employer, location, and contact-redacted description, then calls the existing group-isolated splitter with seed 20261114. Linked posting IDs, normalized title/employer/location, and identical descriptions stay together. Counts are 98,571 train / 21,123 validation / 21,122 test, with five training folds.

The review cohort is deliberately small: **58 training, 15 validation, 29 test** postings. Descriptions are 250–1,500 characters and titles match exactly one of three keyword-defined job families. Training alone is enriched for credential wording; validation/test are hash-sampled within family. A token-Jaccard ≥0.90 filter withheld three near duplicates across the selected cohort. This is a length-filtered, family-balanced pilot, not a representative estimate for the full corpus or all occupations. Some employer templates remain similar, including test rows 5608 and 16158.

The checked-in reference CSVs contain IDs, split/row coordinates, labels, notes, family, and source-description SHA-256 values; raw descriptions remain ignored. All 102 source descriptions were reviewed by **Codex as a single reviewer** before opening their predictions. These are AI-reviewed reference labels, **not independent human gold labels**. No reviewed team handoff CSVs were found. A teammate should independently review disagreements and ambiguous cases before submission claims.

| Label | Positive reference means |
| --- | --- |
| education_required | A formal education qualification/pathway is mandatory |
| experience_required | Prior relevant experience is mandatory, not merely skills/duties |
| certification_required | A named formal certificate/license is mandatory, including a stated after-hire requirement |

`0` means absent, preferred, or optional; `?` means unresolved. Generic employer orientation is not a certificate. Alternatives do not make both paths mandatory. Two held-out experience cells remain unresolved and are excluded from that label's score (85 scored decisions overall). The model does not predict exact credential names, applicant eligibility, hiring outcomes, or reentry acceptance.

## Training and freeze

The existing training module fits word unigram/bigram TF-IDF with sublinear TF and a class-balanced logistic-regression head per label. Vocabulary and heads fit only within training folds; validation is never fitted. C=1/10/100 had identical fixed-0.5 training OOF macro-F1 (0.138), so C=1 was retained. A fixed cutoff grid 0.2/0.3/0.4/0.5/0.6 was then selected per label using training OOF F1, breaking ties nearest 0.5. Final cutoffs are **0.4 education / 0.4 experience / 0.3 certification**.

Threshold-selected training OOF macro-F1 is 0.442; this is optimistic after cutoff selection. Validation macro-F1 is 0.345, versus scraper 0.497 and majority 0.000. The final model and thresholds were frozen before reviewing held-out descriptions or predictions. They were not retuned after test evaluation. The manifest records the complete development metrics, cohort coordinates, source hash, annotation hash, and artifact SHA-256:

`c6c09fa307cf09e78f04abb4d57f042802622bd494bc6453df0345db7da3125a`

## Held-out results

Computed by `src.data.evaluate_requirements`; the evaluator checks source/annotation/model hashes, never fits or chooses thresholds, and reports every error without raw description text. Undefined precision/recall/F1 use zero; FPR/FNR without an eligible denominator are null. Scraper `review` counts as no positive detection. The majority baseline uses training labels only.

| Approach | Macro-F1 | Micro-F1 |
| --- | ---: | ---: |
| Trained TF-IDF + logistic regression | 0.428 | 0.471 |
| Existing scraper | **0.722** | **0.833** |
| Training-label majority | 0.000 | 0.000 |

| Job-family context | Test postings | Trained macro-F1 | Scraper macro-F1 |
| --- | ---: | ---: | ---: |
| Food service / hospitality | 10 | 0.378 | 0.303 |
| Logistics / warehouse | 9 | 0.544 | 0.630 |
| Retail / customer service | 10 | 0.320 | 1.000 |

**The scraper outperforms the trained pilot overall.** It must not be replaced by this classifier. Family macro-F1 includes labels with no positives; food-service education has zero positive references. Small denominators make family comparisons unstable; retail has only one positive certificate reference. Full per-label precision, recall, F1, TP/TN/FP/FN, FPR/FNR, supports and individual error IDs are in [requirement_classifier_v1.json](requirement_classifier_v1.json).

The classifier over-flags certificates: 24 false positives and FPR 1.00 on known certificate-negative test cases. Its experience FPR is 1.00 in food/logistics and 0.625 in retail; education has one missed positive in warehouse. Training enrichment and the tiny sample likely contribute, but this is an inference, not a measured causal result. False positives could burden users with unnecessary training; false negatives could omit preparation. Therefore runtime predictions cannot create mandatory checkboxes, gate applications, or assert exact credentials. They only add confirmation tasks when relevant source wording exists and stronger required/preferred evidence does not already resolve the label. The table evaluates the raw frozen classifier, not this guarded presentation policy.

## Source spot checks and fairness limits

- Test 14872: a food-handler card is explicitly required; the scraper missed it. A model flag can trigger confirmation when exact extraction is absent.
- Test 6775: the food-handler certificate may be obtained after hiring. A positive label must not imply the applicant is barred from applying now.
- Test 3784: barista experience is explicitly preferred. A generic model-positive flag must not override that evidence.
- Test 4630: forklift experience and a driver license are required, with ability to obtain forklift certification. Exact source qualifications remain authoritative.
- Tests 20074 and 14864: requested/conflicting experience wording remains `?`; no forced reference decision.

These are **job-family error slices, not demographic fairness certification**. There are no reliable race, gender, incarceration-history, applicant-outcome, or disability labels, and these attributes are not inferred. English descriptions, title filters, California coverage, short-description selection, single-reviewer bias, residual templates, and sparse positives limit generalization. Larger independent human review, adjudication, more representative labels, confidence intervals, and a new untouched test cohort are needed before stronger quality or fairness claims. Do not reuse this held-out cohort for further model selection.

## Runtime integration

`reentry_matching.model_flags` loads the trusted checked-in artifact and caches model/predictions locally. It runs on the five shortlisted jobs and selected jobs using the full source description. `PHOENIX_NLP_ARTIFACT` can point to another trusted local artifact. Missing/corrupt weights or unavailable ML dependencies retain rule evidence and return a warning. No LLM or encoder download is required.

Raw model flags are stored separately in recommendation details. A positive with a supporting source cue and no stronger required/preferred extraction becomes **uncertain model evidence**, never a newly verified mandatory requirement. Explicit source statements such as “no prior experience required” suppress contradictory model-only prompts. Selecting that job adds a stable `model-check:<job>:<label>` action asking the employer what is required, what can be learned after hire, and which proof/training they accept. Exact certificate paths and qualification checkboxes continue to use the existing extraction and user reports. Completing a prompt does not grant a certificate or mark eligibility confirmed.

A real-data integration check selected organizer posting `09032b43612bb145` (Host Hostess) and produced `reentry:model-check:09032b43612bb145:experience_required` from the saved classifier and source description. This verifies actual preparation influence. A confirmed exact qualification gap can then link a separate preparation action to compatible workforce resources; an employer posting is retained as context rather than mislabeled as a training provider.

## Reproduction

Use a fresh checkout/output directory and the identical organizer export. Raw and derived descriptions/splits stay ignored; do not commit them. Dependencies are locked in `uv.lock` and exported in `requirements.txt`.

```sh
uv sync --group dev
INDEED_CSV=/path/to/indeed_job_listings.csv
uv run python -m src.data.prepare_requirement_review "$INDEED_CSV" data/indeed_splits/reentry_review_v1
uv run python -m src.data.train_indeed train \
  data/indeed_splits/reentry_review_v1/splits data/indeed_splits/reproduced_model \
  data/resources/nlp_annotations_v1.csv --tune-thresholds
# With identical locked environment/inputs, compare against the frozen weights:
shasum -a 256 data/indeed_splits/reproduced_model/tfidf.joblib models/requirements_v1/tfidf.joblib
# Evaluate the shared frozen artifact with the held-out reference CSV:
uv run python -m src.data.evaluate_requirements \
  data/indeed_splits/reentry_review_v1/splits models/requirements_v1 \
  data/resources/nlp_annotations_v1.csv data/resources/nlp_test_annotations_v1.csv \
  reports/local/reproduced_requirement_metrics.json
uv run python -m src.data.train_indeed predict models/requirements_v1/tfidf.joblib /path/to/description.txt
```

Independent reproduction of the same fixed training configuration was run locally after freezing; it is a reproducibility check, not new model selection. Vocabulary, thresholds, coefficients and intercepts were identical; probability maximum difference was 0.0, with **306/306 identical decisions** across all 102 reviewed postings. Joblib byte hashes differed despite identical learned parameters/predictions (reproduction SHA-256 `e699778649db769174b6b20080c52f369570d7821656536bcf12794e2a1ca599`). Treat the frozen checksum as artifact identity, not a guarantee of canonical serialization across runs/platforms. The locked SciPy/NumPy stack emits an ignored-solver-option warning during fitting and a Joblib/NumPy deprecation during loading; execution succeeds. No MiniLM weights or results are claimed for this active pilot.

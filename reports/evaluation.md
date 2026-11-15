# Phoenix job-requirement NLP evaluation

> **Historical handoff — not the current model.** The 450-row annotation files and saved weights referenced below are absent from this checkout, so these figures were not reproduced here. The active checked-in pilot, its actual held-out metrics, labels, hashes, and reproduction steps are in [requirement_classifier_v1.md](requirement_classifier_v1.md). Do not present the historical figures as current runtime performance.

## Task and data

Phoenix extracts three independent flags from Indeed job descriptions: mandatory education, relevant prior work experience, and a certification or license. A positive flag signals language to verify in the posting. The task measures requirement detection. Applicant eligibility, hiring outcomes, and job-ranking quality require separate evaluation.

The 140,816-row Indeed snapshot was split into 98,571 training, 21,123 validation, and 21,122 test rows (70/15/15). The splitter keeps rows together when linked by posting ID, normalized title/employer/location, or identical normalized description. Five group-isolated folds live inside training. The two models compared below used the same 450 reviewed training postings and 110 validation postings. The training sample combined a pilot, a fold-balanced set drawn from three job families, and additional examples enriched for credential wording. The Codex-reviewed reference rubric uses `1` for mandatory, `0` for absent or optional, and `?` for unresolved requirements. Mandatory qualifications that may be obtained after hire can count as positive. Alternatives that leave a qualification optional are recorded accordingly.

## Methods and development results

- **TF-IDF baseline:** word unigrams and bigrams with sublinear term frequency, followed by a class-balanced logistic regression per label. The vocabulary and classifier fit within each training fold.
- **MiniLM candidate:** frozen `all-MiniLM-L6-v2` at `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`, followed by the same logistic regression setup. Long descriptions are chunked at sentence boundaries where possible and split by token count as needed. The classifier uses the mean of the normalized chunk embeddings.
- **Rules comparison:** the current scraper suggests a binary flag or returns `review`, with source text when available. The rules were tuned using 100 of the validation postings. The training report also records a per-label majority sanity baseline, which had validation macro-F1 of 0.000 on this run. The majority baseline was omitted from the held-out comparison.

At 450 training postings, pooled five-fold macro-F1 was **0.619 for TF-IDF** and **0.600 for MiniLM**. Validation macro-F1 was **0.685** and **0.743**, respectively. The 600-posting rerun scored 0.696 and 0.697 on validation. We kept the 450-posting MiniLM candidate based on its higher validation score and used the 450-posting TF-IDF model for a matched-training comparison. The scraper scored 0.972 on development validation, including examples that informed rule changes.

## Held-out comparison

We evaluated the saved models with a fixed threshold of 0.5 on 90 postings from the test split. The first 45 and the additional 45 were sampled separately, each with 15 postings per family. Sampling used seed 763 for the first batch and 764 for the second. Families were assigned by title keywords, and postings that matched multiple families were excluded. Codex labeled each batch from the descriptions before seeing its predictions. We excluded nine ambiguous reference cells, leaving 261 scored label decisions. For the scraper, a `review` prediction counted as a missed detection when the reference label was positive. Undefined precision, recall, and F1 are reported as zero by the scoring code.

| Approach | Macro-F1 | Micro-F1 | Macro-F1 on the additional 45 |
|---|---:|---:|---:|
| TF-IDF + logistic regression | 0.480 | 0.468 | 0.378 |
| MiniLM + logistic regression | 0.505 | 0.520 | 0.443 |
| Rule-based scraper | **0.703** | **0.696** | **0.673** |

| Requirement | Positive / scored | TF-IDF precision / recall / F1 | MiniLM precision / recall / F1 | Scraper precision / recall / F1 |
|---|---:|---:|---:|---:|
| Education | 23 / 89 | 0.533 / 0.348 / 0.421 | 0.515 / 0.739 / 0.607 | 0.750 / 0.652 / 0.698 |
| Experience | 34 / 83 | 0.542 / 0.382 / 0.448 | 0.600 / 0.441 / 0.508 | 0.750 / 0.618 / 0.677 |
| Certification or license | 16 / 89 | 0.667 / 0.500 / 0.571 | 0.368 / 0.438 / 0.400 | 0.786 / 0.688 / 0.733 |

### Job-family results

Counts in the support column are positive labels for education, experience, and certification, in that order. Each family contains 30 postings.

| Job family | Positive support | TF-IDF macro-F1 | MiniLM macro-F1 | Scraper macro-F1 |
|---|---:|---:|---:|---:|
| Logistics and warehouse | 11 / 12 / 9 | 0.559 | 0.580 | 0.724 |
| Retail and customer service | 7 / 13 / 3 | 0.407 | 0.485 | 0.771 |
| Food service and hospitality | 5 / 9 / 4 | 0.329 | 0.388 | 0.600 |

MiniLM caught only **2 of 9** explicit experience requirements in food service and hospitality (78% false-negative rate) and flagged certifications on **8 of 26** confirmed negative cases (31% false-positive rate). In logistics and warehouse, it caught **10 of 11** education requirements but flagged **8 of 18** confirmed negative education cases. Retail certification has only three positive references, so a single decision changes recall by 33 percentage points.

### Observed MiniLM errors

The row numbers refer to one-based data rows in the local test CSV. Scores are the saved model’s positive-class outputs, rounded to three decimals.

| Test row and role | Error | Posting interpretation | User impact |
|---|---|---|---|
| 13586, CFS Warehouse Manager | Education false positive, 0.664 | The bachelor’s degree is preferred. | May discourage someone without a degree. |
| 1830, Warehouse Specialist | Experience false positive, 0.554 | Solar and forklift experience are preferred. The driver’s license is a separate qualification. | Can turn preferences into apparent barriers. |
| 4487, Warehouse Specialist I | Certification false negative, 0.495 | Forklift and order-picker certification or the ability to obtain it is listed. | Hides a credential the applicant should check. |
| 22, Warehouse Associate | Certification false negative, 0.424 | The job requires completing the employer’s forklift certifications. | Hides a credential that can be completed on the job. |
| 19275, Retail Ambassador | Education false negative, 0.341 | High school diploma or GED is listed in the qualifications. | Can omit a stated education criterion. |
| 19696, Chef De Cuisine | Certification false positive, 0.536 | The Food Handler’s certificate is preferred. | May imply an applicant needs the certificate before applying. |

## Limitations and product decision

- The test represents three title-filtered families, with equal sample sizes that do not reflect their prevalence in the full export. The sample is small, especially for credentials. Treat score differences as descriptive. The two evaluations reuse the same locked models, and the final combined score includes the original 45 postings.
- Reference labels came from one Codex review pass per batch. Ambiguous qualifications, flattened text, alternative pathways, and experience versus training can lead to annotation errors. For example, the Retail Ambassador posting lists retail experience as preferred, a potential disagreement with its stored experience annotation. The published scores retain the frozen annotations. Independent double review would improve confidence.
- Grouping catches exact description repeats and specified repost keys. Near-identical templates and employers can still cross splits. The test did not quantify near-duplicate overlap, statistical uncertainty, or demographic fairness. Job-family differences measure performance across posting types only.
- A posting-level flag cannot identify the exact degree, number of years, or credential needed. The trained classifiers do not return an evidence span. Indeed postings are snapshot records with unverified current availability.

**Keep the rule-based extractor where Phoenix already uses it.** It had the highest held-out macro-F1 in all three sampled families and provides evidence for the user to check. The personalized matcher uses its existing rules and credential hints. MiniLM stays an experimental classifier and was not integrated into ranking. Any model revision motivated by these test results needs a fresh held-out sample for a new final estimate.

## Reproduction

The README documents the split, sampler, and `src.data.train_indeed` commands. The 450-posting run uses `pilot_annotations.csv`, `training_review.csv`, `training_review_batch2.csv`, and `validation_review_labeled.csv` under the local `data/indeed_splits/` directory. Use `--minilm` to reproduce the candidate and baseline together. The trained models, annotation CSVs, and score files are local artifacts excluded from Git. Reproducing these exact figures requires authorized access to those files.

The test reference is `test_review_annotated_90.csv`. Run the saved `tfidf.joblib` and `minilm.joblib` from `nlp_450/` on the same descriptions, threshold at 0.5, and apply the `metrics` function in `src/data/train_indeed.py` overall and within each `job_family`. Compare with `suggest_labels` in `src/data/scrape_indeed.py`, treating only `1` as detected. The local `nlp_450/test_predictions_90.csv` has the reference and scores keyed by test row and label, and `nlp_450/test_metrics_90.json` holds the aggregate results. The MiniLM artifact SHA-256 is `d52cb3956809931e2bb4c2313cc4157e66e7b7f37b6b82c3e94d3f2a059e66b5`.

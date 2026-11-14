# Phoenix — DSS Datathon Fall 2026

Phoenix helps people returning from incarceration find relevant **jobs**, **neighborhood rental costs**, and **highly rated public or community services** in Oakland and nearby East Bay cities. One five-question form leads to three result tabs. See [Phoenix.md](Phoenix.md) for the full plan.

> Phoenix shows information from datasets that may be out of date. It does not guarantee a job, housing approval, or service eligibility.

## Status by workstream

| Workstream | Owner | Status |
| --- | --- | --- |
| Places/Reviews cleaning, service taxonomy, rating ranker, API, audits | Person 4 | Implemented and run on the real exports (this README) |
| Indeed/Zillow cleaning, job ranking, housing summaries, selected-job/interim preparation plan | Person 1 (Max) | Integrated through the API adapters; [run instructions](docs/person1_integration.md) |
| Requirement classifier, evaluation, subgroup analysis | Person 2 | Annotation, split, and pilot validation scripts included; final trained model and evaluation pending |
| Frontend and demo | Person 3 | MVP in [frontend/](frontend/): form, three tabs, service cards, rent calculator |

## Setup

You need **Python 3.12** for the backend and data pipeline, and **Node.js 20 or newer** for the frontend.

**With pip:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # pipeline + API
pip install -r requirements-dev.txt  # tests (pytest, httpx)
```

**With [uv](https://docs.astral.sh/uv/)** (what the Makefile uses):

```bash
uv sync --group dev --frozen
```

Both install the same pinned versions. `requirements.txt` and `requirements-dev.txt` are exported from `uv.lock`; after changing dependencies in `pyproject.toml`, regenerate them with `make requirements`.

With pip, the `make` targets won't work unless uv is installed. Run the modules directly from the activated environment, for example:

```bash
python -m src.data.places --source real
python -m src.data.reviews --source real
python -m src.recommend.build_index --source real
PHOENIX_SOURCE=real uvicorn backend.app.main:app --port 8000
pytest -q
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev                          # http://localhost:3000
```

## Raw data

Raw exports are not committed (size, and redistribution is not established). Download them from the organizer-provided **DSS FA26 Datathon** Google Drive folder (linked from the official event guide) and place them at:

| File in the Drive folder | Local path | SHA-256 of the copy used (2026-11-14) |
| --- | --- | --- |
| `google_maps.csv` | `data/raw/places/google_maps.csv` | `47cdc7f87edf37ed6b61b6e0fcb0d4472cc03e9a2b9cd3b2eb1c7cb5774e597b` |
| `google_maps_reviews.csv` | `data/raw/reviews/google_maps_reviews.csv` | `1787435e1efbaddd88256efe38d481cec2b442e754bbe3d6b9e9e03d7a8674d0` |
| `indeed_job_listings.csv` | `data/raw/indeed/` (Person 1) | — |
| `Zillow_part1.csv`, `zillow_part2.csv`, `zillow_part3.csv` | `data/raw/zillow/` (Person 1) | — |

Check headers before trusting the field map: `uv run python -m src.data.inspect_headers --source real`.

## Reproduce (Places/Reviews → services → audits)

```bash
make all SOURCE=real        # clean services, export prepared Indeed/Zillow, run audits and tests
make api SOURCE=real        # http://localhost:8000/docs
```

The local integration includes Person 1's normalized real inputs under ignored `data/processed/real/`. For a fresh checkout, prepare the Indeed/Zillow inputs using [docs/person1_integration.md](docs/person1_integration.md) before `make all SOURCE=real`. `make services SOURCE=real` remains available for the service pipeline on its own. `make fixtures` now includes fictional jobs/housing as well as fictional services; synthetic mode never falls back to real records.

Individual steps (each writes to `data/processed/real/` or `reports/`):

```bash
uv run python -m src.data.places              --source real   # places_target.parquet, places_stats.json
uv run python -m src.data.reviews             --source real   # reviews_target.parquet, review_aggregates.parquet
uv run python -m src.recommend.build_index    --source real   # service_candidates.parquet, area_reference_points.parquet
uv run python -m src.audit.coverage_report    --source real   # reports/places_reviews_coverage.json
uv run python -m src.audit.data_audit         --source real   # reports/data_audit.csv (hand-review columns blank)
uv run python -m src.audit.service_ranking_audit --source real # reports/service_ranking_audit.csv, ranking_sensitivity.csv
uv run python -m src.audit.worklists          --source real   # taxonomy spot check, verification worklist, snippet candidates
uv run python -m src.audit.privacy_check      --source real   # reports/privacy_check.json
uv run pytest -q
```

## Frontend

```bash
make api SOURCE=real     # terminal 1
make web                 # terminal 2: http://localhost:3000
```

Details are in [frontend/README.md](frontend/README.md).

No downloads? `make fixtures` builds a clearly labeled **synthetic** dataset and writes example API JSON to `backend/fixtures/`. `make api SOURCE=synthetic` serves it.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Data source and candidate count |
| `POST /recommendations` | Five onboarding inputs → `jobs`, `housing_areas`, `services`, `data_coverage`, `next_steps` |
| `POST /housing-comparison` | Selected job pay + area rent → hypothetical rent-burden range |

Schemas: [backend/app/schemas.py](backend/app/schemas.py). Contract and integration hooks: [docs/api_contract.md](docs/api_contract.md).

Optional `selected_job_id` and `selected_interim_job_id` fields on `/recommendations` produce a source-linked 30-day preparation plan and explicitly labeled income/rent scenarios. Missing credentials do not disable target-job selection. Interim options still need employer and schedule confirmation, and certification/hiring within 30 days is not guaranteed. The response keeps the existing grouped jobs, housing, and service sections.

## Layout

```
configs/        columns.yaml (raw field map), services.yaml (area + ranking settings),
                service_taxonomy.yaml (category -> family -> need), audit.yaml
src/data/       places.py, reviews.py, make_synthetic.py, inspect_headers.py
src/recommend/  taxonomy.py, build_index.py, services.py (ranker), housing_math.py
src/audit/      data_audit.py, service_ranking_audit.py, worklists.py, privacy_check.py, coverage_report.py
backend/app/    main.py (FastAPI), schemas.py;  backend/fixtures/ (fictional profiles + example JSON)
data/resources/ service_verification.csv, review_snippets.csv (hand-curated, committed)
docs/           data_decisions.md, service_ranking.md, api_contract.md, reproduction_log.md
reports/        generated coverage, audit, and ranking outputs
slides/         deck outline and assembly checklist
```

## Indeed annotation suggestions

The labeler defaults to the team's shared Drive folder and looks for `indeed_job_listings.csv`.
Drive input requires `python -m pip install "google-auth[requests]"` and Google
Application Default Credentials with the `drive.readonly` scope. The account
must have access to the folder and permission to download the CSV. The local
script uses those credentials independently of the connected Codex account.

To process a small sample from Drive and write the result locally, run:

```powershell
python src/data/scrape_indeed.py indeed_sample_labeled.csv --limit 20
```

Pass a folder URL as the first argument to use a different Drive folder, or
pass a downloaded CSV path to run locally with the Python standard library:

```powershell
python src/data/scrape_indeed.py indeed_job_listings.csv indeed_labeled.csv
```

## Indeed splits and pilot validation

```powershell
python src/data/split_indeed.py "$env:USERPROFILE/Downloads/indeed_job_listings.csv" data/indeed_splits --seed 42
python -m pip install scikit-learn==1.6.1
python src/data/validate_indeed.py data/indeed_splits data/indeed_splits/pilot_annotations.csv
```

The split command preserves all source columns and rows. Groups linked by
posting ID, normalized title/company/location, or identical normalized
description stay together. The one-based `train_row` in `train_folds.csv`
identifies each data row in `train.csv`. Each CV iteration fits TF-IDF and the
classifier on four training folds and scores the remaining training fold.
`validation.csv` is used for development decisions. Reserve `test.csv` for the
final run after locking the model and rules. The generated directory is local
and Git-ignored.

The local pilot annotations contain 25 training and 10 validation postings
reviewed by Codex. The annotation columns are `split`, one-based `row`, `jobid`,
`education_required`, `experience_required`, and `certification_required`.
Use `1` or `0` for observed labels and `?` for unresolved requirements. Replace
the pilot annotations with a larger independently reviewed sample for the final
evaluation. The pilot deliberately used shorter descriptions to make review
tractable, and its validation examples informed the rule changes.

### Train the NLP classifier

From the repository root, generate a training review CSV with 225 postings:

```powershell
python src/data/sample_training_jobs.py data/indeed_splits data/indeed_splits/training_review.csv
```

There are 15 postings per fold in each of three title-based job families. Fill
the three blank requirement columns with `1`, `0`, or `?` after checking the
description. The scraper suggestions and evidence are separate columns. Keep
`split`, `row`, and `jobid` intact. Entirely blank rows are skipped and partially
filled rows are rejected.

Run a comparison using the existing validation references and completed
training annotations. Omit `training_review.csv` to reproduce the 25-posting
pilot. Choose a fresh output directory for each run.

```powershell
python -m pip install scikit-learn==1.6.1 sentence-transformers==3.4.1 transformers==4.49.0
python -m src.data.train_indeed train data/indeed_splits data/indeed_splits/nlp_run data/indeed_splits/pilot_annotations.csv data/indeed_splits/validation_review_labeled.csv data/indeed_splits/training_review.csv --minilm
python -m src.data.train_indeed predict data/indeed_splits/nlp_run/tfidf.joblib job_description.txt
```

Omit `--minilm` for the TF-IDF and majority baselines only. MiniLM uses a
pinned frozen encoder and averages normalized chunk embeddings per posting.
Metrics include five training folds, pooled out-of-fold scores, and development
validation scores at a fixed 0.5 threshold. The command only reads train and
validation. Load Joblib artifacts from trusted local runs. Jobs uses the scraper
while evaluation of the trained models is pending.

## Oakland Jobs data handoff

### Personalized Jobs from Indeed only

If Indeed is the only local dataset, prepare normalized listings and start the API:

```powershell
python -m src.phoenix prepare --indeed "$env:USERPROFILE/Downloads/indeed_job_listings.csv" --data-mode full --output data/processed/indeed
python -m uvicorn backend.app.main:app --port 8000
```

Start the frontend as usual. Enter a city and select **Work** to see real
Indeed snapshot listings matched to your profile. The API defaults to real
mode when these files are present. Housing and Services need their own datasets.
Set `PHOENIX_SOURCE=synthetic` explicitly when running the fictional demo.

Run `python src/data/export_jobs.py` from the repository root. It reads
`indeed_job_listings.csv` from Downloads and writes `data/jobs/oakland_jobs.json`.
Pass a local CSV path as the first argument to use a different copy and use
`--output` to choose a different output path. The generated data is Git-ignored.

With normalized Person 1 inputs installed, real mode uses the full local job
matcher and housing summaries. If those inputs are absent, `make api SOURCE=real`
retains the Oakland export as a jobs-only fallback; enter `Oakland` and select
`Work`. Synthetic mode uses fictional jobs, housing, and services together.
The Jobs tab reads through `POST /recommendations` and shows dataset posting
dates and source links. Export-only installations need the normalized Person 1
inputs before they can generate a selected-job preparation plan.

Load the top-level `jobs` array directly. Listings are ordered newest first,
with missing dates last and ties ordered by job ID. Use `job_id` as the card key.
Show `salary_text` as advertised. `annual_pay_low` and `annual_pay_high` are
numeric gross USD per year or `null` for unavailable bounds. Apply the hourly
assumptions in `metadata` when describing an estimated annual equivalent.
`posted_date` is `YYYY-MM-DD` or `null`. Missing employer, URL, and salary text
are also `null`. Link to `source_url` when present so users can verify availability.

Each requirement contains `status` and `evidence`. Display `detected` as
**Detected**, `not_detected` as **Not detected in the posting**, and `unknown`
as **Unknown**. Render the evidence as plain text when present.

Synthetic example:

```json
{
  "metadata": {
    "source": "Indeed dataset export",
    "availability_verified": false,
    "hourly_pay_assumptions": {"hours_per_week": 40, "weeks_per_year": 52},
    "counts": {
      "source_rows": 1,
      "oakland_rows": 1,
      "expired_rows": 0,
      "incomplete_rows": 0,
      "eligible_rows": 1,
      "duplicates_removed": 0,
      "exported_rows": 1,
      "with_annual_pay": 1
    },
    "review_counts": {"education_required": 0, "experience_required": 1, "certification_required": 0}
  },
  "jobs": [
    {
      "job_id": "example-1",
      "title": "Warehouse Associate",
      "employer": "Example Employer",
      "city": "Oakland",
      "state": "CA",
      "posted_date": "2026-11-01",
      "source_url": null,
      "salary_text": "$25 an hour",
      "annual_pay_low": 52000,
      "annual_pay_high": 52000,
      "requirements": {
        "education_required": {"status": "detected", "evidence": "High school diploma required."},
        "experience_required": {"status": "unknown", "evidence": "Warehouse experience."},
        "certification_required": {"status": "not_detected", "evidence": null}
      }
    }
  ]
}
```

# Phoenix — DSS Datathon Fall 2026

Phoenix helps people returning from incarceration find relevant **jobs**, **neighborhood rental costs**, and **highly rated public or community services** in Oakland and nearby East Bay cities. One five-question form leads to three result tabs. See [Phoenix.md](Phoenix.md) for the full plan.

> Phoenix shows information from datasets that may be out of date. It does not guarantee a job, housing approval, or service eligibility.

## Status by workstream

| Workstream | Owner | Status |
| --- | --- | --- |
| Places/Reviews cleaning, service taxonomy, rating ranker, API, audits | Person 4 | Implemented and run on the real exports (this README) |
| Indeed/Zillow cleaning, job ranking, housing summaries | Person 1 (Max) | Plugs into the API via [docs/api_contract.md](docs/api_contract.md) |
| Requirement classifier, evaluation, subgroup analysis | Person 2 | Not yet in repo |
| Frontend and demo | Person 3 | Build against [backend/fixtures/](backend/fixtures/) |

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`; dependencies are locked in `uv.lock`.

```bash
uv sync --group dev --frozen
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
make all SOURCE=real        # ~7 s: clean Places, clean+aggregate Reviews, build index, audits, tests
make api SOURCE=real        # http://localhost:8000/docs
```

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

No downloads? `make fixtures` builds a clearly labeled **synthetic** dataset and writes example API JSON to `backend/fixtures/`. `make api SOURCE=synthetic` serves it.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Data source and candidate count |
| `POST /recommendations` | Five onboarding inputs → `jobs`, `housing_areas`, `services`, `data_coverage`, `next_steps` |
| `POST /housing-comparison` | Selected job pay + area rent → hypothetical rent-burden range |

Schemas: [backend/app/schemas.py](backend/app/schemas.py). Contract and integration hooks: [docs/api_contract.md](docs/api_contract.md).

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

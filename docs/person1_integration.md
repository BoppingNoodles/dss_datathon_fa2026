# Person 1 integration

Person 1's normalized data, ranking, housing aggregates, credential planning, and tests are integrated with the existing backend. The backend's grouped public API remains the frontend contract; the internal library is under `src/phoenix/`. Raw and processed datasets stay local and are ignored by Git.

## What is connected

- `src/recommend/jobs.py`: maps the existing five-input API request to the Person 1 matcher and returns `JobsSection` groups. It preserves nullable pay, evidence, suitability, location precision, and the agreed comparable-pay ranking.
- `src/recommend/housing.py`: returns city/ZIP aggregates with quartiles and bedroom/property-type distributions, plus aggregate proximity to Person 4's candidate services. No individual property identifiers, addresses, or coordinates are public.
- Optional target/interim job selection returns `thirty_day_plan` and separately labeled income/rent scenarios. Missing credentials never disable selecting a target job.
- `src/recommend/prepare_person1.py`: exports normalized inputs to source-specific audit tables. Real and synthetic data use separate directories and cannot silently fall back to each other.
- The team's Oakland export remains supported by `src/recommend/oakland_jobs.py` when normalized real inputs are absent. Its annotation/export/split scripts and UI changes are preserved. Synthetic requests never load that real export.

The existing Places/Reviews cleaning, taxonomy, rating ranking, service cards, verification files, and dependencies/lockfile are retained. Backend schema changes are additive and recorded in [api_contract.md](api_contract.md). Independent audit inputs now use `data/processed/{source}/` so a synthetic audit cannot inspect real records by accident.

## Local data

The original Person 1 workspace remains at `/Users/maxli/Documents/ChatGPT/Phoenix`. The normalized full inputs were copied into this checkout; the original raw Indeed/Zillow exports remain there rather than duplicating roughly 9.6 GB. Raw and processed files are ignored by Git.

| Dataset/output | Local path | Records |
| --- | --- | ---: |
| Normalized Indeed snapshots | `data/processed/real/jobs.jsonl` | 46,776 |
| Normalized Zillow rental candidates | `data/processed/real/rentals.jsonl` | 66,570 |
| Coverage/checksums | `data/processed/real/person1_coverage.json` | 140,816 Indeed / 148,005 Zillow source rows |
| Public housing aggregates | `data/processed/real/housing_areas.parquet` | 280 overlapping city/ZIP groups |
| Job audit table | `data/processed/real/jobs_clean.parquet` | 46,776 |
| Internal rental audit table | `data/processed/real/zillow_rentals_clean.parquet` | 66,570 |

City and ZIP populations overlap; never add their listing counts. Small public groups are suppressed below five distinct properties. The API exposes aggregate service-access metrics rather than falsely treating an area median as a point count at a user's home. Rents combine bedroom types unless a separate comparison filters them; the returned distributions make that limitation inspectable.

Latest retained parsed job posting date: September 20, 2026. Source not-expired flags and FOR_RENT status do not confirm a current vacancy or available home. The sample recommendation and credential pathway must begin with confirmation.

## Run

```sh
uv sync --group dev --frozen
make fixtures
uv run pytest -q
make api SOURCE=synthetic
```

`make fixtures` creates fictional services plus three fictional jobs and six fictional internal rental records. It regenerates the grouped frontend response without downloading data.

For the already integrated local full data:

```sh
make person1 SOURCE=real
make audits SOURCE=real
make api SOURCE=real
```

The service raw files needed by `make services` are under the ignored paths documented in the main README. They were downloaded from the supplied Drive folder and match Person 4's recorded SHA-256 values.

To reproduce Person 1 cleaning from raw exports in a fresh checkout, put authorized source files in the ignored raw paths (or pass their actual local paths), then run:

```sh
uv run python -m src.phoenix prepare \
  --indeed data/raw/indeed/indeed_job_listings.csv \
  --zillow data/raw/zillow/Zillow_part1.csv \
  --zillow data/raw/zillow/zillow_part2.csv \
  --zillow data/raw/zillow/zillow_part3.csv \
  --data-mode full --output data/processed/real
make person1 SOURCE=real
```

The export step copies the cleaner's `coverage.json` into the namespaced `person1_coverage.json` manifest. It does not modify service outputs. Real data needs full inputs; a sample manifest is rejected.

## Selection request for the frontend

The request remains flat, using the backend's existing names (`health_care`, `high_school_or_ged`, `education.credentials`). Exact degree matching is left unknown for the broad `graduate` choice instead of inventing a master's or doctorate.

```json
{
  "age": 35,
  "location": "Oakland",
  "priority_need": "work",
  "experience": {"skills": ["warehouse", "inventory"], "years": 2},
  "education": {"level": "high_school_or_ged", "credentials": []},
  "selected_job_id": "286f8e707701f4a1",
  "selected_interim_job_id": "1649d79113832b8e",
  "scenario_hours_per_week": 40,
  "scenario_weeks_per_year": 52
}
```

This selects the snapshot ABF Freight CDL-A/forklift role as a target and Allied Fluid Products' $25/hour warehouse role as provisional interim work. The plan uses official requirement/provider/support links, asks about costs and shift compatibility, and keeps certification completion uncertain. Housing uses the selected interim job's hypothetical $52,000 annual gross income, not future target-job pay. No application, enrollment, booking, or employer/provider contact is performed.

Before job selection, `thirty_day_plan` is null. Invalid target/interim IDs return HTTP 422. If Person 1 data is not installed for the configured source, housing shows `not_integrated` and plan selection fails explicitly. Real mode may still show the team's Oakland jobs-only export; synthetic mode never substitutes real records.

## Limits and next work

The job matcher remains a transparent rule baseline. It now extracts explicit degree levels and experience amounts from posting text, retaining required/preferred/alternative/uncertain wording and short evidence excerpts. Curated or model-supplied structured fields remain authoritative. These rules are not the Advanced Track trained model, and partial extraction never establishes that every requirement has been checked.

Experience requirements retain their work scope. Warehouse work does not establish equipment-repair or tractor/trailer experience. Forklift/equipment repair technician roles require relevant reported repair experience to enter a warehouse user's matching results. Unreported experience stays unknown; an explicitly insufficient total number of years or degree level creates a visible qualification gap. Interim options omit unconfirmed required experience, while target jobs with known gaps remain selectable. Preferred requirements and trainee/equivalent-experience alternatives do not become mandatory filters. Age and company-history numbers do not become experience amounts. Contact emails are omitted from public evidence excerpts.

Enrichment happens when relevant jobs are ranked; normalized source files remain unchanged. The frontend supports target/interim selection and the 30-day checklist. Model inference integration, official provider verification, and the independent human audit remain with their owners; the ML teammate's reported evaluation is in `reports/evaluation.md`.

Before submission, the ML owner needs a fitted model, baseline comparison, untouched test metrics, at least three meaningful subgroup/error analyses, and reproducibility evidence. The project can use dated dataset snapshots if they are labeled honestly; the event guide has no live-listing requirement.

# API contract

The source of truth is [backend/app/schemas.py](../backend/app/schemas.py). Interactive docs are at `http://localhost:8000/docs` once `make api` is running. Freeze this contract after first integration, and log any change below.

## Example payloads (synthetic, fictional)

| File | What |
| --- | --- |
| `backend/fixtures/profiles.json` | Six fictional onboarding profiles, including skipped answers and an out-of-area location |
| `backend/fixtures/recommendation_request.json` / `recommendation_response.synthetic.json` | A full request and response |
| `backend/fixtures/housing_comparison_request.json` / `_response.json` | Rent-burden scenario |
| `backend/fixtures/job_selection_request.synthetic.json` / `job_selection_response.synthetic.json` | Fictional target/interim selection and preparation-plan response |

Regenerate them with `make fixtures`.

## Request: `POST /recommendations`

Only `location` and `priority_need` are required. Unknown fields are rejected (HTTP 422), so nobody can send conviction details, an SSN or an exact address by accident.

```json
{
  "age": 34,                          // nullable; used only for verified service age criteria
  "location": "Oakland",              // city or ZIP
  "priority_need": "housing",         // work | housing | food | health_care | transportation | community_support
  "experience": {"skills": [], "text": null, "years": null, "no_experience_yet": false},
  "education": {"level": null, "credentials": []},
  "service_sort": "highly_rated",     // or "nearest"
  "job_sort": "highest_pay"           // or "nearest"
}
```

## Response sections

- `open_tab`: `jobs` for work, `housing` for housing, `services` otherwise.
- `services` (Person 4): `groups[]` → `items[]` of `ServiceCard`. Overall rating and count are kept separate from `review_evidence` (the sample), along with verification status, an age-eligibility note, distance with its reference point, closure and hours, and public business contact details.
- `jobs` (Person 1/2): `JobsSection` with `groups[]` of `JobCard` (suitability tier, requirement evidence, pay with conversion basis, location precision, rank explanation).
- `housing_areas` (Person 1): `HousingSection` with `HousingArea` aggregates only. The schema forbids extra fields, so `zpid`, street addresses and coordinates cannot be returned.
- `data_coverage`: data mode (real or synthetic), per-source counts and status, and plain-language coverage notes.
- `next_steps`: deterministic checklist templates.
- Optional selection fields: send `selected_job_id`, optional `selected_interim_job_id`, and explicit `scenario_hours_per_week` / `scenario_weeks_per_year`. The response adds nullable `thirty_day_plan`, `selected_job_id`, `housing_income_job_id`, `housing_income_stage`, and `housing_comparisons`. No job is automatically selected. Invalid/out-of-search selections return HTTP 422.
- Job cards add `selectable`, `is_selected`, and `credential_summary`. Requirement evidence can include the extracted `value` and original required/preferred/alternative/uncertain kind. Credential gaps stay selectable for a preparation pathway; no identified credential is not proof that none is required.
- A selected interim job determines the `interim_job_scenario` housing comparison. Target pay remains a separately labeled `target_job_scenario`, not income during training. Neither scenario establishes actual income or rental approval.

Frontend states to handle:
- `status: "not_integrated" | "no_results"`
- empty `groups`
- `null` pay, rating, distance or hours
- `eligibility.age_status = "eligibility_needs_confirmation"`
- `review_evidence.sampled_review_count = 0` (the common case)

## Jobs and Housing integrations

The Jobs adapter uses Person 1's normalized `data/processed/<source>/jobs.jsonl` with the matching coverage manifest. It ranks relevant roles within suitability and comparable-pay groups, using verified distance only when supplied. Each group returns up to 12 cards and its full matching count. Housing uses the matching rental inputs and publishes aggregates only.

The team's Oakland export adapter is preserved in `src/recommend/oakland_jobs.py`. If normalized **real** Person 1 data is unavailable, real mode can still load `data/jobs/oakland_jobs.json`, including Oakland ZIP resolution, source links, rule evidence, advertised-period groups, and up to 12 cards per group. That export's Nearest order remains newest first until worksite coordinates exist. The full preparation plan requires the normalized Person 1 inputs.

Synthetic mode uses fictional jobs, housing, and services together; it never falls back to the real Oakland export. `data_coverage.sources.jobs.source` identifies the job source.

```python
# src/recommend/jobs.py
def rank_jobs(request: dict, sort: str, *, source: str = "real", area_city: str | None = None) -> dict:
    ...

# src/recommend/housing.py
def housing_areas(location: str, services: pd.DataFrame, *, source: str = "real") -> dict:   # validates as schemas.HousingSection
    ...
```

For housing-to-service proximity, `services` is the service candidate table with `place_id`, `family`, `family_label`, `lat`, `lon` and closure flags. Distances use internal property coordinates and only city/ZIP aggregates are published. `NearbyServiceSummary` adds `median_count_within_1_mile`, `share_of_properties_with_service`, `properties_with_coordinates`, and `measurement`. Legacy single-point `count_within_1_mile` and `nearest_miles` stay null: an area median is not a count or distance from one user's home.

The audit expects Person 1's cleaned files at the paths in `configs/audit.yaml`. Edit the column names there to match.

## `POST /housing-comparison`

```json
{"pay_min": 20, "pay_max": 24, "pay_period": "hour", "hours_per_week": null, "monthly_rent": 1650}
```

- The response gives `annual_gross_min/max` and `rent_burden_min/max`, using `rent_burden = 12 * monthly_rent / annual_gross_pay`.
- When hours aren't stated for hourly pay, the 40-hour assumption is labeled in `assumptions`.
- Missing inputs give `status: "unknown"` with null values, never 0.
- Plan example: `12 * 1200 / 48000 = 0.30` (tested).

## Change log

| Date | Change |
| --- | --- |
| 2026-11-14 | Initial contract (Person 4) |
| 2026-11-14 | Person 1 adapters integrated; source-specific audit inputs; additive job selection, credential/interim-work plan and area-level proximity fields. Existing onboarding names and service schema/ranking retained. |

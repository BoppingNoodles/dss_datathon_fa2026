# API contract

The source of truth is [backend/app/schemas.py](../backend/app/schemas.py). Interactive docs are at `http://localhost:8000/docs` once `make api` is running. Freeze this contract after first integration, and log any change below.

## Example payloads (synthetic, fictional)

| File | What |
| --- | --- |
| `backend/fixtures/profiles.json` | Six fictional onboarding profiles, including skipped answers and an out-of-area location |
| `backend/fixtures/recommendation_request.json` / `recommendation_response.synthetic.json` | A full request and response |
| `backend/fixtures/housing_comparison_request.json` / `_response.json` | Rent-burden scenario |

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

Frontend states to handle:
- `status: "not_integrated" | "no_results"`
- empty `groups`
- `null` pay, rating, distance or hours
- `eligibility.age_status = "eligibility_needs_confirmation"`
- `review_evidence.sampled_review_count = 0` (the common case)

## Jobs and Housing integrations

The Jobs adapter loads `data/jobs/oakland_jobs.json`. It accepts Oakland city searches and ZIPs mapped to Oakland by the current area reference table. It groups listings by advertised hourly pay, annual pay, or pay to confirm. Highest pay sorts by the lower bound within each comparable group. Nearest uses newest-first ordering while worksite distances are unavailable. Up to 12 listings are returned per group. All cards ask users to confirm fit while personalized qualification matching is pending.

The Jobs data can be real while the Services data uses synthetic fixtures. `data_coverage.sources.jobs.source` identifies when listings come from the Indeed snapshot. Housing returns `not_integrated` until its adapter is available.

```python
# src/recommend/jobs.py
def rank_jobs(request: dict, sort: str, *, area_city: str | None = None) -> dict:
    ...

# src/recommend/housing.py
def housing_areas(location: str, services: pd.DataFrame) -> dict:   # must validate as schemas.HousingSection
    ...
```

For housing-to-service proximity, `services` is the service candidate table with `place_id`, `family`, `family_label`, `lat`, `lon` and `permanently_closed`. Compute distances against internal property coordinates and publish only ZIP-level summaries (`NearbyServiceSummary`).

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

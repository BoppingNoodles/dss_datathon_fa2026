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
- `jobs` (Person 1/2): `JobsSection` with `groups[]` of `JobCard` (suitability tier, requirement evidence, pay with conversion basis, location precision, rank explanation), plus `other_groups[]` for local roles outside reported work areas.
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


### Compact listing UI additions (November 14, 2026)

`JobCard.description` is an optional plain-text source description. It appears only
in an expanded job card. Older/export-only records may leave it null.

`HousingArea.nearby_places` is an additive list of at most ten public business
summaries (`place_id`, `name`, `family_label`, nullable `maps_url`). Candidates must
be within two straight-line miles of the median public-business location in that
ZIP/city. Known permanently or temporarily closed places are excluded. Verified
public/community providers and assistance services sort first, followed by review-adjusted rating
`(n*r + 20*3.5)/(n+20)`, distance, and place ID. The shortlist includes distinct
service families when available, then fills remaining slots in ranked order. Duplicate IDs are removed. Missing
ratings use the 3.5 prior, not a fabricated displayed rating. No rental address or
coordinate is used as the reference or published. Areas with no reference or usable
place data return an empty list. These names describe nearby places, not verified
eligibility, free services, or current opening hours.

The UI now has a separate 30-day calendar tab and no interim-work selection. Existing
API interim fields remain available for backward compatibility. `ThirtyDayPlan.daily_actions`
supplies exactly 30 relative days with `action_id`, `day`, `title`, `action`, `phase`, and
`links`. Activities use the selected role, reported education and experience, required
versus preferred credentials, and any known or unconfirmed qualification gap. Existing
credentials trigger verification instead of automatic repeat enrollment. Education and
experience gaps trigger accepted-equivalent or trainee-route questions; the schedule
does not imply those gaps can be closed in 30 days. A selected API interim job is named
only conditionally, without assuming an offer, schedule, or income. The frontend dates
these actions from the local current date and retains the older fixture fallback.
Task IDs remain stable across sorting/date changes and change with job/task content.
The UI's additional `plan` tab is local navigation; API `open_tab` is unchanged.

### Role relevance and qualification checkboxes (November 14, 2026)

`JobCard.matches_reported_role` is true when the conservative title/work-area matcher
finds overlap, false for another role, and null when there is no positive experience
context to assess. It is a keyword baseline, not a calibrated similarity score or a
qualification decision. `groups` contains related or unassessed roles; `other_groups`
contains other roles in the same resolved city/search area. Both preserve suitability,
pay-period, availability, and distance rules, with at most 12 cards and the full count
per group. Other roles remain selectable for a personalized plan. They are not included
automatically in the more conservative interim-work shortlist. No experience supplied
means roles are unassessed, not rejected or duplicated in the other-role list.

`JobCard.qualification_checks` lists specific extracted requirements, such as
“High school diploma or GED”, “Class-A CDL”, and “2 years of warehouse experience”.
Each row has a stable `key`, `field`, `label`, `requirement_kind`, `status`, and
supporting `detail`. Status is `reported_met`, `gap`, `needs_confirmation`, or
`preferred`. A checked row is a self-report, not employer verification. No extracted
requirements means an empty checklist and a prompt to confirm the full posting.

Optional `qualification_answers` maps job IDs to requirement keys and boolean
self-reports. Answers affect only that job's qualification assessment and plan;
they do not rewrite global education, experience duration, or certificates. Unknown
keys cannot establish a qualification. Edited/selected jobs stay in their result
group even beyond the usual 12-card cap. The frontend updates immediately without disabling the screen. Rapid clicks are
batched for 300 ms; only the latest response can update the result. Failed updates
restore the last server-confirmed state. The listed/mandatory progress count makes
remaining requirements visible. A positive job-specific experience report updates
relevance for that role without rewriting global work history. “Clear match” means every **listed mandatory**
item is reported met. Preferred items do not block it. “Needs preparation” is the lower level when
no listed mandatory qualification is reported met and at least one is explicitly
missing. Skipped answers alone do not trigger that label. Matching onboarding
diplomas, certificate aliases, and scoped experience prefill the relevant rows,
including criteria marked alternative or uncertain; their acceptance still needs
confirmation. Evidence completeness, employer acceptance, and vacancy remain
separate checks.

`GET /job-certificates` returns recognized certificate/license labels actually
mentioned in the loaded Indeed data, with posting counts and coverage notes.
The cached list refreshes when the source job file changes. Onboarding renders 17
standardized presets immediately without waiting for this endpoint. These labels
were checked against the loaded Indeed data. The picker supports multiple
selections, an unlisted credential entry, or `education.no_credentials`.
The explicit none option cannot accompany credential names. Mentioned credentials
may be preferred or optional; this catalog is not exhaustive. No extra mandatory
onboarding question is added.

Daily activities use short, plain instructions, normally one to three sentences.
The detailed posting evidence and official pathway links remain available beside
the calendar rather than being repeated in each day's task.

`Pay.needs_confirmation` identifies ambiguous source pay. USD hourly amounts of
$1,000 or more at either endpoint are flagged for review, with the raw source text
retained and an explicit note. This is a conservative sanity threshold, not proof
of an error. Such amounts are excluded from comparable-pay ranking and income/rent
scenarios until confirmed; they are never automatically reinterpreted as annual pay.
The job remains selectable, with “Pay needs confirmation” in the UI.

`RecommendationResponse.service_map_points` contains `{place_id, lat, lon}` for
the public service/business IDs named in the housing shortlists. These locations
come exclusively from the public Places dataset. Invalid coordinates and duplicate
IDs are removed. Coordinates are kept outside `housing_areas`; the housing property
privacy contract and audit remain unchanged. The frontend joins by `place_id` to
draw up to ten numbered nearby-place pins on a zoomable street map. Housing cards
keep a compact preview of the first three places, and selecting any part of a card
updates its map. Public-place links remain separate actions.

### Housing recommendations and selected-job pin (November 14, 2026)

`HousingArea.recommendation` adds `rank`, `recommended` (the first three), short
`reasons`, optional gross-pay rent-burden bounds, and the income-scenario stage.
`HousingSection.ranking_note` explains the policy. Compare ZIP areas when present,
otherwise cities; do not compare overlapping city/ZIP populations together.
Suppressions and the five-property minimum remain in force. All areas stay available.

Without a usable income scenario, work/housing priorities use lower median rent
first; other priorities first prefer measured access to a relevant service type,
then lower rent. Service metrics refer to sampled properties and straight-line
proximity, not travel time, confirmed availability, or eligibility. Unknown access
is not zero. When an existing selected-job income scenario is usable, areas within
the 30% lower-gross-pay guide rank first, followed by pay ranges that might meet it;
relevant service access and rent order those groups. Remaining areas use lower rent
first. Hourly pay does not silently assume hours/weeks. Age, education, and inferred
personal characteristics do not rank housing. This is an explainable comparison
policy, not a trained rental-approval or affordability model.

Job `location` adds nullable `latitude`/`longitude`, `map_precision`, and `map_note`.
Only supplied worksite points are labeled `worksite`. A city/ZIP reference point
is labeled `approximate_area`; city fallback resolves the **job city**, never the
user's home location. No usable point means `unavailable`. These are job-area/public
worksite coordinates, never rental-property coordinates. They do not change the
rule that job distances require supplied worksite coordinates.

The housing map shows the selected target job as a green **J** pin, alongside the
numbered public-place pins and selected ZIP boundary. Its legend and popup disclose
approximate job areas. Fit-area bounds include the job pin. Missing coordinates
produce a note instead of a fabricated worksite. Existing housing selections,
street-map controls, and browser persistence remain in place.

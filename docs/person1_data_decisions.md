# Person 1 data decisions and validation

This records Person 1 implementation choices, source coverage, and pending handoffs. Integration and run instructions are in [person1_integration.md](person1_integration.md).

## Inputs inspected

The completed [team Drive folder](https://drive.google.com/drive/folders/1iGJ511t7Enpj9ShRZmMOkOH0FvRjpSut) lists Indeed, all three Zillow parts, Google Maps Places, and Google Maps Reviews. The full Indeed/Zillow/Places files exceed the connector's 256 MiB download limit. Initial implementation used the organizer samples while the uploads completed. After the user explicitly requested a full run, the four publicly shared Indeed/Zillow files were downloaded through Drive's normal download endpoint, with byte counts checked against metadata. They total 9,583,264,953 bytes. SHA-256 checksums computed during downloading match pipeline hashes. Raw downloads remain in ignored local storage; Places/Reviews were not downloaded for this Person 1 run.

The organizer-provided [Indeed sample](https://drive.google.com/file/d/1kOPq2hqftTUb1M8XvzgTV9QESCpX9LAg/view) and [Zillow sample](https://drive.google.com/file/d/1-QWqAOXDJ2S4mxOn_YO960XGok2qTcV5/view) were downloaded locally and each contains 1,000 logical CSV records. Checksums and exact count outputs are in [sample_coverage.json](../reports/sample_coverage.json). Those samples are not treated as a representative sample of the filtered populations described in the READMEs.

| Source | Observed sample finding | Consequence |
| --- | --- | --- |
| Indeed | Includes statewide locations and out-of-state jobs, including California, Maryland. 937/1,000 rows are marked expired. | Require recognizable local geography; preserve actual expiration flag; exclude explicitly expired snapshots by default. |
| Indeed | After geography and exact-duplicate handling: 156 jobs, only 8 not marked expired; none of those 8 are in Oakland. | An empty default Oakland search is an honest sample result; unexpired flags still do not establish a live vacancy. |
| Zillow | Only 22/1,000 are `FOR_RENT`; source includes properties outside the nine Bay Area counties. | Filter state/county/status before any rent calculation. |
| Zillow | Four retained Bay Area rental candidates, one each in Oakland, Daly City, Santa Clara, and Vacaville. Each selected `price` matches `base_rent`. | No city or ZIP group reaches the five-property publication threshold; no public rental summary is generated from this sample. Matching base rent is a unit cross-check, not independent current-listing verification. |

## Field mapping and grain

Indeed grain is a posting. Actual sample fields include `jobid`, `job_title`, `company_name`, `location`, `region`, `description_text`, `salary_formatted`, `date_posted_parsed`, `url`, and `is_expired`. The cleaner emits a typed `Job`. It does not create requirements or worksite coordinates when the source lacks them. Relative dates such as 30+ days ago are not converted into invented calendar dates.

Geography uses state-aware, longest-city-name matching to a conservative explicit allowlist; e.g. South San Francisco must not become San Francisco. A street named California does not imply the state, and the word California alone does not identify a Bay Area city. Santa Cruz-area cities are explicitly recognized as nearby coverage, not counted as nine-county Zillow geography. Unincorporated/unknown locations and statewide remote records are not automatically assigned to Oakland.

Job IDs and exact normalized description/title/employer/city keys are deduplicated in SQLite. A duplicate preference favors an explicitly unexpired snapshot, then a parsed posted date; absent source capture timestamps, this is not a claim of latest scrape state. Related title/employer/city records share `duplicate_group` so the ML owner can keep potential repost/template groups within a split. Exact normalization does not establish full semantic near-duplicate detection. Duplicates across input files are handled by the same store.

Zillow grain is a property identified by `zpid`. Actual sample fields include `county`, `state`, `homeStatus`, `price`, `base_rent`, `currency`, `isOffMarket`, `isRentalListingOffMarket`, and coordinates. Reject sale/sold/other records, invalid prices, non-USD or unknown currency, and explicitly off-market rentals. Default monthly-rent candidates require numeric `price == base_rent`; ambiguous rows are withheld or explicitly opted into as unverified. Neither `zestimate` nor `rentZestimate` becomes a listed rent. Address, owner/contact, photos, histories, and other bulky nested fields are not copied into normalized output.

Normalized rental IDs/coordinates stay in ignored internal files. Public area results contain no property identifiers, street addresses, or exact property pins. Aggregate city and ZIP populations overlap and must not be summed. Groups with fewer than five distinct properties are suppressed, including proximity summaries when fewer than five properties have usable coordinates.

## Compensation and ranking

Parse one advertised period and one amount/range. English and observed Spanish hourly/yearly wording are supported. Upper-only pay has no conservative lower endpoint. Missing pay, reversed ranges, mixed periods, ambiguous numeric separators/currencies, estimates, and variable-compensation strings require confirmation rather than silently producing a comparable salary. For US source records, dollar-denominated pay defaults to USD; no currency conversion is performed.

Only pay with the same basis is numerically compared. Annual salary becomes hourly pay only with supplied stated hours and working weeks; missing hours are not imputed for ranking. Housing income scenarios may use a separately selected, visible hypothetical schedule. `$1,200 * 12 / $48,000 = 0.30`, a gross-income ratio, not rental approval or disposable income.

The ranking is a transparent lexical baseline plus requirement evidence and the agreed pay-first policy within suitability/pay groups. It is not the Advanced Track trained model. Full-data validation revealed unrelated roles mentioning warehouse/inventory in descriptions. When experience is supplied, main recommendations now require a compatible title or configured role family, not description-only overlap. This conservative relevance filter may miss unfamiliar titles and is not an eligibility determination. Missing education/credentials do not become negative labels. Preferred qualifications are not mandatory filters. Known gaps remain visible; age does not influence ranking. Sources with only city-level locations have no precise distance; a radius filter cannot exclude a location-unknown job. Unresolvable locations do not trigger a nationwide fallback.

## Spatial pairing and other-team boundaries

The housing/service join accepts typed `ServiceLocation` inputs from Person 4; it does not collect or rank services. It uses a geographic grid to shortlist candidates, then haversine distance, avoiding a full property-by-service Cartesian join. Radius defaults to one mile and is a configurable scenario assumption. Output reports median nearby service count and the share of internal rental properties with a candidate in range. It is straight-line proximity, not walking/transit time, eligibility, or verified service capacity.

The backend integration now supplies mapped service families, deduplicated IDs, ratings/reviews, verification status, and eligibility metadata from Person 4's pipeline. Official provider verification remains pending. Caden can supply evidence-backed requirements and verified worksite coordinates through the keyed enrichment contract. Training and reporting the final Advanced Track model is not implemented in this Person 1 work.

## Checks performed and still pending

The source samples were inspected for headers, geography, expiration/status, currency, price/base-rent agreement, and salary formats. The local cleaner has been run on both complete sample files. Synthetic fixtures verify the response shape without pretending they are measured live data.

Automated domain checks cover double pay versus half-mile distance, monotonic pay ordering, incomparable schedules, sort preference, unknown fields, age invariance, qualification gaps, geographic false positives, source deduplication, reproducible sample processing, small-cell protection, correct record-ID enrichment, and proximity aggregation.

The subsequent full run read 140,816 Indeed rows and 148,005 Zillow rows, retaining 46,776 unique local jobs and 66,570 rental candidates. Of the jobs, 46,762 are not marked expired in the snapshot. Oakland has 1,540 jobs not marked expired and 5,976 rental candidates. Housing summaries contain 82 city groups and 198 overlapping ZIP groups; 27 smaller groups were suppressed. The current fictional warehouse-profile example returns 19 provisional Oakland job matches. Detailed exclusions and hashes are in ignored `data/processed/real/person1_coverage.json`, and local run notes are in `reports/local/full_run_summary.md`.

Full-source verification cross-checked 20 retained jobs and 20 retained rentals from each Zillow part against raw fields (80 checks total), verified unique normalized IDs, and validated the generated response. These are scripted source checks, not completed human review or model evaluation. The integrated test suite includes 61 Person 1 domain tests and 11 adapter/API regression tests.

Actual current job/rental availability, source-reported hours, job-requirement extraction accuracy, near-duplicate leakage, service-review join rates, and manual official provider checks remain pending. The latest parsed retained job posting date is September 20, 2026, so not-expired source flags must not be presented as proof of current vacancies on November 14. No trained model metrics or fairness results have been generated. The original event evidence checklist remains incomplete until those owners deliver their artifacts.

## Selected-job preparation and interim-work update

Local response schema 1.1 supports explicit target-job selection, a source-linked 30-day preparation plan, and optional interim-job selection. Credentials and known qualification gaps do not disable selecting a target. The interim shortlist omits known gaps and required/uncertain credentials not reported held, while keeping all other requirements, current availability, and work/training schedules subject to confirmation. Absence of an identified credential is not proof of credential-free work.

A small evidence-preserving fallback identifies common CDL-A, forklift, driver's-license, and guard-card mentions; it is not a full requirement parser or training-label creation process. Existing supplied structured requirements take precedence. Operator-role checks are marked uncertain and distinguished from posting quotations. Partial hints do not imply all qualifications have been extracted. Preferred credentials are not automatically prerequisites to application, and a short course does not replace required trade experience.

The real Oakland example selects ABF Freight's CDL-A/forklift role as the target and Allied Fluid Products' shipping/receiving role as provisional interim work. The explicitly hypothetical interim-income scenario uses $25/hour × 40 hours/week × 52 weeks/year = $52,000, separately from target-job pay. It is saved in ignored `reports/local/oakland.target-and-interim.plan.json`; no course booking, employer contact, or job application was made.

Official California DMV, FMCSA, California DIR, and CareerOneStop pathway/finder pages were checked November 14, 2026. Specific training providers, prices, available seats, eligibility, funding, and completion within 30 days are not verified. The dated datasets are still suitable for a labeled hackathon prototype: the event guide requires supplied data and reproducibility but has no live-listing requirement. Production would need ongoing source refresh and opportunity verification.

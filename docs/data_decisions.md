# Data decisions

The four sources share one record. Person 4 owns the Places and Reviews sections; Person 1 adds the Indeed and Zillow sections. Numbers come from `reports/places_reviews_coverage.json` (run on 2026-11-14). Regenerate that file rather than editing figures here by hand.

## Google Maps Places (`google_maps.csv`)

**File.** SHA-256 `47cdc7f8…597b`. The export has 147,429 rows and 147,429 unique `place_id`s; the README says "about 100,000". The real header has 41 columns.

**Field map** (confirmed against the real header, recorded in `configs/columns.yaml`):

| Logical field | Source column | Note |
| --- | --- | --- |
| place_id, name, category, all_categories, address, lat, lon, rating, reviews_count | same names | |
| phone | `phone_number` | |
| website | `open_website` | |
| hours | `open_hours` | JSON by weekday; `{}` means no hours listed |
| permanently/temporarily closed | same names | `"true"`/`"false"` strings |
| maps_url | `url` | public Google Maps link to the place, not a reviewer link |
| city, ZIP | — | **No column exists.** Both are parsed from `address` (`…, City, CA 94612, United States`). |

Columns that are **never read**: `top_reviews`, `reviews_snippets`, `people_also_search`, `photos_and_videos`, `questions_answers` (they can contain reviewer content).

**Cleaning rules**
- **Unrated placeholder.** `rating = 0` with `reviews_count = 0` means *no rating*. It does not mean zero stars. In the target area, 13,645 places carry this placeholder; they get `rating = NA`. Another 14 places have a rating but zero reviews and are also treated as unrated. A rating outside 1–5 becomes NA.
- **Closure flags.** These are normalized to true, false or unknown. Anything uninterpretable is *unknown*, never false. Permanently closed places are excluded from recommendations (1,679 in the target area). Temporarily closed places (455) appear only in a collapsed "temporarily closed" group.
- **Duplicates.** Duplicates by `place_id` keep the row with the most reviews, then the most filled fields. None were found in the target area.
- **Target area.** Twelve cities, listed in `configs/services.yaml`, leave **22,502 places**: Oakland 9,433, Berkeley 3,905, Hayward 2,124, San Leandro 1,496, Richmond 1,396, Alameda 1,279, and smaller cities. No expansion was needed.
- **Fill rates in the target area.** Usable rating 39.3%, hours listed 30.1% (the README says ~53% filled; `{}` counts as filled there but not here), phone 72.5%, website 42.7%, ZIP parsed 99.0%, coordinates 100%.

## Google Maps Reviews (`google_maps_reviews.csv`)

**File.** SHA-256 `1787435e…74d0`. The export has 213,536 rows across 6,108 unique `place_id`s, with review dates from 2024-01-02 to 2025-04-30.

**Columns read.** `place_id`, `review_id`, `review`, `review_rating`, `review_date`, `place_general_rating` and `overall_place_riviews` (sic). Only these are read, via `usecols`. A guard refuses any mapped column whose name contains `reviewer`, `profile`, `avatar`, `photo`, `url` or `response_of_owner`.

**Never read.** `reviewer_name`, `reviewer_url`, `profile_pic_url`, `reviews_by_reviewer`, `photos_by_reviewer`, `local_guide`, `response_of_owner` (owners often address reviewers by name), `photos`, and the review `url`.

**Cleaning rules**
- **Stars.** A `review_rating` outside 1–5 (including 0) is treated as missing.
- **Empty text.** A review whose text is only the template `Positive: "" Negative: ""` counts as having no text.
- **Duplicates.** Exact duplicates are removed by (`place_id`, `review_id`). Content duplicates (same text, stars and date at the same place) are also removed; rows without text are never content-deduplicated.
- **Overall fields on review rows.** These are deduplicated per place, and any conflict is flagged. They are **never** added to the Places `reviews_count`, and the overall rating is never replaced by a sampled mean.

### Join finding: the Reviews sample barely overlaps Places

| Measure | Value |
| --- | --- |
| Review rows whose `place_id` exists anywhere in Places | 1.4% (2,985 of 213,536) |
| Review rows for target-area places | 513 (no duplicates found) |
| Target-area places with ≥1 sampled review | **18 of 22,502** |
| Service candidates with ≥1 sampled review | 14 of 17,588 |

The Reviews export is a national random sample (the first rows are in Indiana). The documented `place_id` join works, but the overlap with Bay Area Places is too small to support review-based features at scale.

Consequences:
1. All joins from service candidates to reviews are **left joins**, so a service never disappears for lacking a sampled review.
2. Ranking uses the **Places overall rating and count**.
3. Sampled-review evidence (star distribution, date range, checked snippets) appears on very few cards and is labeled as a sample.
4. The deck must state this limitation.

## Service taxonomy

`configs/service_taxonomy.yaml` maps each category tag to one of 15 families. Each family maps to one or more of the six onboarding needs. **Assistance** families are candidate public or community support. **Ordinary essentials** (grocery stores, pharmacies, banks, private medical providers) are never described as free assistance.

Fixes made after spot checks on the real data (2026-11-14):
- `bart` matched "Bartending school". It was removed, and `school` was added as a transit exclusion.
- "Social security attorney" matched government offices, so `attorney` and `lawyer` were added as exclusions.
- 3,942 "Bus stop" and 831 "Transport hub" places were unmapped and now map to transit.
- Private doctors, dentists, therapists and hospitals had no family. They now form `medical_providers`, an ordinary essential with cost and insurance unknown.
- "Medical clinic" (801 places) is mostly private. The family is labeled "Clinics and community health centers" and remains *unverified*.
- Generic "Non-profit organization" places (883) were being shown for housing and work needs. `social_services` now serves **community_support only**.

`reports/taxonomy_spot_check.csv` holds 10 random places per family for a relevance review (y/n). Record the outcome here once it is reviewed.

Candidates by family (active, rated): medical providers 7,732 / 1,999; transit 4,465 / 1,053; social services 1,103 / 690; community health 825 / 347; behavioral health 658 / 299; grocery 515 / 471; government 480 / 237; banking 206 / 186; employment 154 / 77; pharmacy 151 / 115; food assistance 70 / 41; libraries 44 / 42; housing assistance 15 / 13; legal aid 3 / 3.

## Verification layer (`data/resources/service_verification.csv`)

One row per `place_id`. A row counts as **verified** only when it has an `official_url` (the provider's own page or a government or agency page) and a `checked_on` date. `provider_type` is one of `public`, `nonprofit_community`, `private` or `unknown`.

Age is used only from `min_age`, `max_age` and `age_criteria_text` copied from that official source. Unknown stays blank. Do not infer anything from a provider's name or from a review.

**Status (2026-11-14): 0 rows verified.** Work from `reports/verification_worklist.csv`, which lists the top unverified assistance candidates per family and city. Prioritize food, housing, legal aid, employment and reentry or social services in Oakland.

## Area reference points

City and ZIP centers are the **median coordinate of Places records** in that city or ZIP, and require at least 5 records. The result is 12 city centers and 44 ZIP centers. Distances are straight-line miles from that area center, never from the user's home, and are labeled as such. An unresolvable ZIP falls back to its most common city, and otherwise to matching by city or ZIP without distances.

# Service selection and rating logic

Implements Phoenix.md section 6. The code is in [src/recommend/services.py](../src/recommend/services.py) and the settings are in [configs/services.yaml](../configs/services.yaml). Every number below is a **product assumption**, not a measured optimum.

## Decision order

1. **Need relevance.** The priority need selects its service families from the taxonomy. A highly rated place that does not provide the needed service is never shown for that need.
2. **Geography.** Candidates must lie within **10 miles** (straight line) of the city or ZIP center. If the location can't be resolved, the ranker matches by city or ZIP and shows no distances. Locations outside the 12-city area get a coverage message.
3. **Availability and eligibility evidence.**
   - Permanently closed places are removed, and the number removed is stated.
   - Temporarily closed places go to their own collapsed group.
   - Age is checked only against verified, official-source criteria. Anything else shows "Eligibility needs confirmation".
4. **Rating and distance**, applied within each group.

## Groups

Each place appears in exactly one group, assigned in this order:

| Group | Rule | Sort (default) |
| --- | --- | --- |
| `temporarily_closed` | dataset flag is true | nearest |
| `essential_services` | ordinary-essential family (grocery, pharmacy, bank, private medical) | score |
| `verified_support` | `verified_public_community` in service_verification.csv | nearest |
| `highly_rated` | overall rating ≥ **4.0** and overall reviews ≥ **10** | score, then distance |
| `other_rated` | rated with ≥ 10 reviews, below 4.0 (neutral label, never "poor") | score, then distance |
| `limited_review_evidence` | no usable rating, or < 10 reviews ("not a judgment of quality") | nearest |

Verified support is always shown. For urgent needs (housing, food), if nothing is verified yet, a note says so and the unverified candidates stay visible.

**The threshold is never relaxed silently.** When fewer than 3 places meet the highly rated threshold, the response says how many do and that the threshold was not lowered. Places below the threshold remain visible in their own groups.

## Count-aware score

```
score = (n * r + m * C) / (n + m)
```

- `r` is the Places overall rating and `n` the Places overall review count.
- `m = 10`.
- `C` is the mean overall rating of rated candidates in the same service family. A family with fewer than 10 rated places uses the all-family mean (4.16) instead; legal aid is the only such family, with 3 rated places.

Sampled-review counts are **never** added to `n`, and an overall rating is never replaced by a mean of a few sampled reviews.

**Ties.** Scores within **0.02** of each other count as tied (bucketed), and the nearer place comes first. The remaining ties fall back to `place_id`, so the order is deterministic. The user can switch any group to **Nearest**.

Family means used for C (real data, 2026-11-14): public library 4.59, social services 4.37, medical providers 4.29, behavioral health 4.27, grocery 4.26, transit 4.12, food assistance 4.14, community health 4.02, housing assistance 3.88, employment 3.86, government 3.61, pharmacy 3.53, banking 3.37.

## Sensitivity (reports/ranking_sensitivity.csv)

This compares the top-10 overlap with the m=10 ranking within each family × city group that has at least 10 rated assistance candidates.

| m | mean top-10 overlap with m=10 |
| --- | --- |
| 0 (raw stars) | 0.60 |
| 5 | 0.96 |
| 25 | 0.96 |
| 50 | 0.93 |

The ranking is stable for any reasonable prior weight. Ranking by raw stars changes 40% of the top 10, because places with one or two 5-star reviews jump to the top. That instability is why a count-aware score is used.

## Descriptive ranking audit (reports/service_ranking_audit.csv)

The audit reports, for each family × city:
- active candidates and rated count
- missing-rating rate
- review-join rate
- highly rated, limited-evidence and verified counts
- how many places a "highly rated only" view would hide

Key observations from the real data:
- **Low-review areas would lose most services under a highly-rated-only view.** Transit (76% missing ratings, 6 of 4,465 highly rated) and medical providers (74% missing) would almost vanish. That is why limited-evidence places stay visible.
- **Food assistance has 60 active candidates** (31 rated, 8 highly rated). **Housing assistance has only 15** (5 highly rated). For housing, the verification layer matters more than ratings.
- **The review-join rate is under 1% in every family** (see data_decisions.md).

This audit describes coverage. It is **not** a recommendation-accuracy measure: no labeled relevance judgments exist.

## What a rating does not mean

A Google rating is an experience signal. It is not evidence of clinical quality, safety, free service, reentry suitability or current capacity. Cards show the original rating and count, label sampled reviews separately, and always include "confirm with the provider".

# Deck outline and assembly checklist

Person 4 assembles the deck and checks access. Each owner drafts their own slides. The required topics are problem, data, methods, findings, impact, subgroup failures and limitations.

| # | Slide | Owner | Source of truth |
| --- | --- | --- | --- |
| 1 | Problem: reentry means jobs, housing and services all at once | Person 1 | Phoenix.md §1 |
| 2 | A fictional user and four-step onboarding | Person 3 | backend/fixtures/reentry_profiles.json |
| 3 | Demo: task progress, Resources, situation update and replan | Person 3 | Running Phoenix app; video still to record |
| 4 | Four datasets and how they join | Person 1 + 4 | docs/data_decisions.md |
| 5 | Services: need → location → verification → count-aware rating | **Person 4** | docs/service_ranking.md |
| 6 | Services data findings and limits | **Person 4** | reports/places_reviews_coverage.json, service_ranking_audit.csv |
| 7 | NLP requirement classifier: labels and training | Person 2 | reports/requirement_classifier_v1.md |
| 8 | Baseline vs model on the held-out test set | Person 2 | reports/requirement_classifier_v1.json; pilot macro-F1 0.428, scraper 0.722 |
| 9 | Three job-family error slices and reviewed failures | Person 2 (Person 4 reviews) | reports/requirement_classifier_v1.md and .json; not demographic fairness claims |
| 10 | Housing support, ZIP rent estimates and editable budget | Person 1 | Housing and Finances in Resources; docs/reentry_planner.md |
| 11 | Privacy and safety choices | **Person 4** | reports/privacy_check.json |
| 12 | Limitations, and what we do *not* claim | All | below |
| 13 | Social-good value, reproducibility, next steps | Person 1 + 4 | README, docs/reproduction_log.md |

## Person 4 slide content (real numbers from 2026-11-14)

**Slide 5: How services are chosen**
- Order: need relevance → within 10 miles of the area center → closure and verification → count-aware rating, with distance breaking ties.
- Score: `(n·r + m·C)/(n+m)`, m = 10, C = family mean. "Highly rated" means 4.0+ stars with 10+ reviews, and the threshold is never silently lowered.
- Groups: Verified support · Highly rated · Other rated · Limited review evidence · Essential services (not free assistance) · Temporarily closed.

**Slide 6: What the data showed**
- 147,429 places in the full export; **22,502** in 12 East Bay cities; **17,567** mapped to 15 service families (22 off-topic spa/massage/skin-care places removed).
- **61% of East Bay places had a "0 stars, 0 reviews" placeholder** (13,645 of 22,502), meaning *unrated*. Reading it as a zero would have buried thousands of places.
- **The Reviews sample barely overlaps Places**: 1.4% of review rows match any place, and only **18** East Bay places have sampled reviews. Ranking therefore uses Google's overall rating, and cards show Google's overall star breakdown (available for every rated place). Sampled reviews appear on very few cards. Separately, 56% of review rows are outside California and 20% have 0 stars, both contrary to the Reviews README.
- Sensitivity: ranking by raw stars changes **40%** of the top 10 versus the count-aware score, while m between 5 and 50 changes ≤ 7%.
- A "highly rated only" view would hide nearly all transit (6 of 4,465 qualify) and most medical providers, so lower-evidence places stay visible and labeled.
- Housing assistance: only 15 active East Bay candidates. Verification against official pages matters more than ratings here.

**Slide 11: Privacy and safety**
- No conviction details, SSN, exact address or account. Unknown request fields are rejected.
- Reviewer names, profile URLs and owner responses are never loaded; a guard enforces this in code.
- Housing is shown only as ZIP or neighborhood aggregates; the schema forbids property IDs, addresses and coordinates.
- An automated privacy scan of every API response runs in the tests.

## Claims we do NOT make (slide 12)
- Not hiring success, housing approval, service safety or clinical quality, or reduced recidivism.
- A Google rating is not proof that a service is free, public, reentry-friendly or currently open.
- Service-ranking audits are descriptive. There are no labeled relevance judgments, so there is no "recommendation accuracy".
- Distances are straight-line from an area center, not travel time.
- Rent burden is a scenario based on advertised pay, not affordability or eligibility.

## Assembly checklist (Person 4)
- [ ] Every number on a slide matches a file in `reports/` from the final rerun
- [ ] Model metrics appear only as measured on the frozen test set (no illustrative scores)
- [ ] Subgroup slide shows ≥ 3 job families and ≥ 5 reviewed failures
- [ ] Deck, repo and video links open while signed out
- [ ] Video ≤ 5:00 (target 4:45) and playable
- [ ] Synthetic data never appears in slides or video as if it were real

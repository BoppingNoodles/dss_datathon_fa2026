# Adaptive Reentry Plan — implementation and verification

This feature branch makes a persistent reentry plan the desktop homepage. Onboarding materially changes priorities and resources, and confirmed user updates regenerate future actions while preserving completed work. Existing jobs, Zillow area summaries, Places/Reviews services, native qualification checks, map pins, and job preparation calendar remain in use.

## Architecture and API

The existing POST /recommendations endpoint now accepts a validated ReentryProfile, previous PhoenixSession, and optional UserEvent. Legacy requests continue working. No duplicate plan/replan API, database, authentication service, or LLM dependency was added.

1. Pydantic validates profile/session/event; the profile adapter fills existing request fields.
2. The event applies to a deep copy. User status/outcomes never mutate shared datasets.
3. Existing job, housing, and service pipelines run in their original real/synthetic modes.
4. reentry_matching normalizes evidence and explanations into shared recommendations.
5. generate_plan reuses existing barrier and qualification logic, merges history, and orders the dependency graph.
6. The response includes the canonical phoenix_session plus existing response sections. The browser saves a confirmed state locally.

Backend/TypeScript domain models separate source verification, availability, raw NLP flags, user qualifications/outcomes, derived scores, task progress, notes, and events. No criminal-history details, officer contacts, case numbers, eligibility guarantees, or inferred supervision rules are collected/generated.

## Required onboarding and updates

Four required steps cover:

- Release phase and optional date; intended city or ZIP.
- Stable/temporary/no confirmed/unknown housing, optional end date/budget; ID, transport, phone and internet.
- Employment status, optional job interests, skills/years, education, preset certificates, none or uncertainty.
- Separate checkbox choices for immediate support and 30-day goals, with examples, Not sure/none options, and an optional personal goal. General appointment labels/dates/locations remain optional.

Sensitive questions offer unknown/privacy responses. No release date, qualification, appointment or restriction is fabricated. All four steps must be completed before viewing a personalized dashboard. Older saved sessions retain their old progress and return to onboarding for review (onboarding version 3).

View / update my situation opens the full prefilled editable form directly. Quick Update and the text-entry chooser are no longer shown. A separate speech-bubble button opens a side chat for describing housing, work, food or transportation changes. It uses the existing conservative local interpreter; ambiguous/unsupported facts require structured answers, and relative housing dates require an entered date or explicit unknown answer. Raw text is not sent to an LLM or saved as an event. Before-and-after previews show circumstances, priorities, tasks, opportunities and preserved completion/selections. Applying saves; editing retains proposed inputs; cancel/discard keeps the original state. A proposal based on an older session must be refreshed before applying.

## Recommendation behavior

Jobs reuse the existing Indeed adapter and qualification reports. Up to five available displayed candidates are ranked by heuristic weights: qualification 0.40, preference 0.25, location 0.20, comparable wage 0.15. Unknown dimensions use an explicit neutral 0.5; unknown mandatory checks each contribute 0.5 rather than silently counting as met. Limited transport steepens the distance penalty and adds route/shift/cost confirmation. Distance remains a straight-line area reference, not commute time. Wage uses a fixed logarithmic scale, log(1 + hourly pay / 20) / log(9), capped at 1; those constants are design choices, not learned parameters or a living-wage claim. A regression verifies $20 → $40 at 0.5 mile farther ranks higher even with an unrelated $500/hour outlier and limited transport. Scores apply to the existing adapter's candidate pool, not an exhaustive reranking of every raw posting.

Exact required/preferred qualifications and onboarding autofill remain stronger evidence than a model prediction. Multiple jobs may be selected. The last active target also drives the existing detailed job calendar and green job-location map pin; approximate locations stay labeled. Dismissed/rejected jobs leave active suggestions; the shortlist refills where candidates exist. History can explicitly restore dismissed items.

Housing has two distinct sections. Immediate/temporary assistance uses existing Places candidates and a small official-source scope registry. A verified organization is not a verified bed, current capacity, or personal eligibility. All recommendations default to contact to confirm. Long-term area costs retain Zillow aggregate-only privacy handling and the interactive ZIP map. Selecting an area adds a cost-research task, never a rental application or approval claim. The old pay/rent comparison controls are removed from job and housing cards; selected-option budget estimates now live in Finances.

Services retain the existing taxonomy, review ranker and source cards, supplemented by candidates related to reported needs/barriers. Reviews do not establish eligibility or availability. A broad map category is explicitly unverified for the requested assistance.

Every normalized resource shows only Selected for Plan, Interested, and Not Interested. These map to the existing selected/saved/dismissed statuses and preserve earlier status history. Selected opportunities create linked tasks and appear under the current situation as plan targets. Selection/contact does not silently claim a secured home or job. Richer status/unavailability events remain supported by the domain/API for compatibility and preserve earlier contact history.

### Root causes and corrected resource joins

The original join used broad housing/employment barriers rather than explicit capabilities. Consequently urgent housing could receive Zillow areas, and job-related preparation could receive unrelated organizations. A shared organization's first deduplicated row also lost its other service capabilities. Referral locations incorrectly reused the requested city instead of the source city.

The transport examples were actual Google Places bus stops/stations, not area_reference_points records. Rating-first selection and missing subtype/locality context made a Berkeley bus stop read like an Oakland assistance provider. The geographic reference table remains a distance reference only.

Recommendation now declares resourceType, supportedResourceTypes and serviceEvidence. PlanTask declares allowedResourceTypes, primary relatedRecommendationIds, per-match resourceMatchReasons, contextual referenceLinks and an honest resourceEmptyState. reentry_resources.py validates every primary join, checks documented service areas/local distance where available, excludes geographic-reference-only records, rejects wrong-specialty training, and favors compatible user selections. Broad categories alone cannot establish ID assistance or training. Shared organizations retain their independently sourced capabilities and show the capability relevant to the task.

| Task purpose | Allowed primary resource types |
| --- | --- |
| Immediate/temporary housing | transitional_housing, housing_assistance |
| Long-term cost comparison | rental_market |
| Job review/application/employer requirement confirmation | job_posting |
| Certificate/diploma preparation | workforce_training |
| Transportation | transportation_assistance, public_transit |
| Identification | identification_assistance |
| Food / health | food_assistance / healthcare |
| Own work information or private arrangements | No external resource required |

Required qualification gaps can add a separate training task after employer-route confirmation; the posting remains contextual evidence, not a training provider. A forklift requirement cannot attach phlebotomy training, nor can CPR preparation attach a forklift course. Exact course availability, accepted credentials, costs and eligibility remain unconfirmed. Incompatible resources are excluded in Python rather than hidden by the frontend.

## Planner rules and persistence

| Reported information | Derived behavior |
| --- | --- |
| No confirmed housing | Critical safe-place planning; tonight's need comes first after release |
| Temporary housing | Housing-continuity task; critical within seven days of entered end date |
| Previously completed housing preparation, end now close | New end-date-specific follow-up, without resetting the earlier completed action |
| Missing ID | ID assistance, independent of job applications |
| Unknown ID/access | Confirmation task; absence is not assumed |
| No transport / limited communication | Specific route/access arrangements and relevant candidates |
| Entered appointment | Stable per-appointment task; real entered date controls urgency |
| Appointment details unknown | Confirmation without invented date or legal obligation |
| Selected job | Job review, exact qualification gaps, uncertain NLP prompts, and application/training steps |
| Employed | General searches archived; work arrangements added with transition-specific ID |
| Multiple selected providers | Individual contact/follow-up actions |
| Provider unavailable | Personal rejected/unavailable state and alternatives; contact history remains |
| Entered goals | Stable user-goal actions; no invented external requirements |

Tasks have stable semantic IDs, explicit prerequisites, priorities, statuses, notes and related recommendation IDs. A topological sort orders eligible tasks by urgency/date/stage and rejects missing prerequisites/cycles. ID help is not a universal gate to applying for work. Only an actual task dependency blocks completion.

Replanning retains completed actions and notes; obsolete incomplete actions become archived/skipped instead of disappearing. User events and selected resources remain. A completed action does not assert that the underlying barrier is solved. Current uncertainty/verification is regenerated from source; resources absent from current results become inactive historical snapshots.

Plan and Resources are separate tabs. Plan has one compact Tasks list: each header shows its title, status symbol and Urgent/Not urgent; completed rows are green. Multiple tasks can stay open. Row order stays stable across status updates, open cards retain their working height after an action, actions do not force focus/scroll, and new tasks append. A live completion count and progress bar sit above Housing, Food, Employment, Identification and Transportation. The three planning stages remain in the task model. Expanded tasks show a short action, relevant resources, optional rationale/notes and status controls. Completed work remains in the list and history is preserved.

The submission pass shortened repeated copy across onboarding, cards, the budget, calendar and update previews. Qualifications, provider descriptions, budget assumptions and sources remain available in disclosures. Job pay headlines use structured English units. An official-scope food referral now prioritizes the Alameda County Community Food Bank helpline / FoodNow, with a [provider source](https://www.accfb.org/about-us/food-distribution/), contact number and documented county coverage. It is general food referral support, not a reentry-specific eligibility claim or a warehouse pickup instruction; weaker category-only Places candidates remain labeled unverified.

ZIP cards use a visible map-selection button and a clickable card background; nearby-place links and preference controls retain their own actions. This replaces an invisible full-card button whose center could activate a nearby-place link. Production uses a same-origin `/api` proxy with a 30-second request timeout and retry messages. A branded recovery boundary handles rendering errors. Standard Tailwind PostCSS and a licensed local Geist font remove the production build's runtime font-download dependency.

Start/Complete/Blocked/Skip/notes are saved through the existing API. Relevant need tasks offer explicit completion results: Housing arranged, Food secured, Transportation arranged. These update reported access; research-only completion is also available and does not imply an outcome. Older completed searches can record the actual result later. Housing arranged defaults to temporary, never long-term stability. Contacting a provider or reviewing a job does not report admission/hiring. Reopening a task does not revoke real access. An unresolved crisis can retain a confirmation follow-up without resetting prior completion.

Resources are ordered Finances, Jobs, Housing, Services, Calendar. Finances uses one selected job and housing option at a time, never adding alternative salaries. Pay defaults to the lower advertised amount, stated weekly hours or an explicitly labeled 40-hour assumption (8-hour days for daily pay), 52 weeks/year, and an editable 80% kept after estimated deductions. Rent uses the selected area's median or range midpoint; a provider with no price stays unknown. User-entered amounts override estimates. Food defaults to $886.08/month ($10,633/year) and other goods/utilities to $730.92/month (utilities $4,931 + supplies $844 + clothing $2,010 + personal care $986 per year, divided by 12), from [BLS Consumer Expenditures 2025](https://www.bls.gov/news.release/cesan.nr0.htm), released October 29, 2026. These are U.S. household averages, not a one-person minimum; transport, healthcare, debt and other bills may need adding. Calculation uses income less listed costs. Phoenix's own planning targets flag housing above 30% of take-home or listed spending at least 80%; actual deficits are costs exceeding income. A reviewed budget can add relevant cost, income, food and housing tasks/resources after confirmation, preserving completed work and estimate provenance. It does not assert that a selected opportunity is secured.

Calendar, rightmost in Resources, retains both reentry and selected-job views. Reentry calendar days are flexible slots, distinct from entered deadlines; idle review days do not create mandatory tasks or show a false prerequisite warning. Completed calendar assignments remain in place; pending/new work moves to the current or future portion. After a 30-day window, a new window starts while task/event history remains. Plan updates show a spinning circle and orange-gradient “Phoenix is thinking” text, with reduced-motion support and no animated dots.

PhoenixSession schema version 1 is stored inside the existing browser session envelope; legacy job-calendar progress remains separate and preserved. An older open tab cannot overwrite newer event history saved by another tab. Failed API updates roll back to the last confirmed state. Damaged canonical state is exposed for download/recovery; before replacement, its raw saved value is backed up under phoenix-session:recovery. Clear saved data removes both active and recovery data. This is device-local demo storage without account sync; use fictional profiles, avoid sensitive details and clear shared devices.

## Trained NLP status

The previously referenced MiniLM/450-row artifacts were absent. They were not invented or claimed reproduced. This branch includes a new fitted TF-IDF pilot, source-reviewed annotation metadata, frozen manifest, baseline comparison, held-out test metrics, and error slices for three job families.

See [the complete modeling report](../reports/requirement_classifier_v1.md) and [computed metrics](../reports/requirement_classifier_v1.json). The 58/15/29 cohort has single-reviewer Codex labels and substantial sampling limits. Held-out macro-F1: trained pilot 0.428, scraper 0.722, majority 0.000. The model over-flags and is unsuitable for automatic qualification decisions.

The trusted local artifact informs uncertain confirmation/preparation tasks only when source wording supports the predicted category and stronger required/preferred evidence is absent. Explicit source statements such as no experience required suppress contradictory model-only prompts. It cannot invent exact licenses/diplomas/years or block applications. Missing/corrupt weights retain rule evidence and return warnings. The planner, ranking weights, and text-update extractor are deterministic supporting logic, not trained ML.

Advanced Track evidence now includes an organizer dataset, a fitted predictive artifact, baselines, untouched held-out evaluation, three job-family error slices, documented source decisions/spot checks, and reproduction commands. Independent human adjudication, more representative labels and a new untouched evaluation cohort remain necessary for stronger submission claims. Job-family slices do not establish demographic fairness.

## Verification — actual results

Commands run from the feature worktree:

- .venv/bin/python -m pytest -q -p no:cacheprovider — **287 passed**, 14 dependency deprecation warnings (FastAPI/httpx and Joblib/NumPy), 26.58 seconds.
- cd frontend && npm test — **70 passed, 0 failed**, including request timeout/error handling and normalized pay headlines; final run completed in 582.88 milliseconds.
- cd frontend && ./node_modules/.bin/tsc --noEmit --incremental false — **passed**.
- PHOENIX_BUILD_DIR=.next-production PHOENIX_API_URL=http://localhost:8002 npm run build — **passed** using Next.js Webpack and standard Tailwind PostCSS, with TypeScript and static prerendering checks enabled. The earlier Turbopack worker-port failure was isolated; fonts are now bundled locally rather than fetched during the build. No build/type checks were disabled.
- Frozen held-out evaluator — **completed**, actual metrics above. Fixed-configuration reproduction was also run; hashes are recorded in the model report/manifest.
- Existing Jobs/Housing/Services tests and the earlier 625 barrier-combination graph checks — included in the passing backend suite.

Stateful acceptance tests in tests/test_adaptive_reentry.py cover:
A crisis housing + transport with ID present; B stable/employment-focused + model preparation; C two jobs → employed → housing deadline, preserving completion/notes; D unavailable provider and personal-only outcomes, preserving contact; E unknowns without invented dates. They also cover stable IDs, duplicate/cycle checks, prerequisite validation, pure preview, idempotent events, actual saved-model inference, corrupt-model fallback, neutral uncertainty and small distance/pay tradeoffs.

Isolated headless desktop browser checks (1440×1000) verified:
required four-step onboarding → Your Reentry Plan; crisis housing first; completion after refresh; natural-language interpretation → preview → cancel and confirm; two selected jobs and qualification updates; both existing calendar views; immediate housing provider selection/contact/unavailability/history/alternatives; Jobs, Housing and Services rendering. A pre-release appointment/transport profile prioritized its entered appointment; an unknown-information profile generated no deadlines. Damaged state showed a recovery/download notice and retained the original saved value.

Earlier task-list checks verified Start → refresh → Done and saved counts. The current browser checks verified separate Plan/Resources tabs, multiple tasks expanded together, the live task count/progress, Finances-first/Calendar-last ordering, selected-job pay changes, honest missing provider rent, U.S. cost defaults, a budget shortfall producing four new steps in a before/after preview with completed tasks preserved, cancel without saving, and side-chat housing/food/transport interpretation with discard. Pending previews showed “Phoenix is thinking.” Support/goal selection, onboarding Back/Continue, refresh persistence and the direct prefilled edit form were also checked during this work. An earlier 390×844 plan smoke check found no horizontal overflow. Desktop remains the design focus; this is not a comprehensive mobile/accessibility audit.

The final production acceptance pass used isolated localhost ports 3002/8002 and a fictional Oakland profile. At 390×844, unfinished onboarding answers survived refresh and appointment fields fit without horizontal overflow. Completing explicit housing, food and transportation outcomes updated the current situation to temporary housing / food available / transport available. Three completions survived reload and later budget and employment replanning. Measurements of six task rows around food completion showed zero changes in top position or height. At 1280×900, selected job income and area rent populated Finances; reviewing/applying the budget added three relevant steps with completed work retained. Unchecking/rechecking a job qualification updated its match immediately. ZIP selection changed the map boundary/title; zoom and pin details worked. Both November 2026 calendar scopes rendered. “I got a job” required a preview, then confirmed employment, added work-arrangement/routine tasks and archived unfinished job-search tasks while preserving all three completed steps. Direct editing opened the updated prefilled information. Light and dark Finances views were inspected.

After the final rebuild, refresh retained the three completions, updated circumstances, two selected opportunities and all four financial amounts. Multi-task calendar days no longer repeat a combined description above the task list. The production preview reported no console errors or warnings. Desktop and mobile screenshots were saved with the review artifacts. No external form, job application or housing request was submitted.

## Files changed

- Backend contract/orchestration: backend/app/{schemas,main}.py.
- Domain/matching/planner and earlier compatibility: src/recommend/reentry_{domain,matching,models,planner,resources}.py; jobs.py selected-job retention; demo_reentry.py; fictional fixtures.
- Desktop UI: frontend/app/page.tsx; OnboardingForm, AdaptivePlan, PlanTaskCard, SituationUpdate, SituationChat, FinancesTab, PhoenixThinking, PlanPreview, ResourceActions, ResourceCandidates; existing JobsTab/HousingTab/ServicesTab/JobPlan and compatibility ReentryPlan/QuickUpdate helpers.
- Client types, adaptation/persistence/calendar: frontend/lib/{domain,finances,onboarding,onboarding-choices,reentry,saved-session,types,plan,plan-view,quick-update,results-cache}.ts.
- NLP preparation/training/evaluation: src/data/{prepare_requirement_review,train_indeed,validate_indeed,evaluate_requirements}.py; two annotation CSVs; models/requirements_v1; reports/requirement_classifier_v1.{md,json}.
- Tests: new stateful/planner/model Python tests and onboarding/adaptive/reentry/persistence Node tests.
- Existing official-scope supplement: data/resources/reentry_services.json.
- Dependency/ignore/docs: pyproject.toml, uv.lock, requirements.txt, .gitignore, README, API contract, this report and historical evaluation clarification. Raw data and local candidate models remain ignored.

## Git and remaining limitations

Worktree: /Users/maxli/Documents/ChatGPT/Phoenix/reentry-planner
Branch: codex/reentry-planner

The user authorized publication to main on 2026-11-14, with separate commits for each major change. The commits group NLP evaluation, adaptive planning, saved state, resource discovery, finances, dashboard updates, build reliability and submission documentation. The shared checkout was clean before integration; teammate source/data pipelines were preserved.

Before final event submission: finish/check the deck, playable video and accessible project link described in Phoenix.md; have teammates review this feature branch and validate their processed-bundle setup. A fresh raw-data rebuild has not been claimed by this pass. Independently reviewed model labels and a new untouched cohort remain model-quality follow-ups. Sources are snapshots, provider verification coverage is small, current capacity/acceptance is unknown, and commute estimates are not route calculations. Browser storage and the limited text extractor are demo features, not a production sensitive-data system.

# Phoenix frontend

Next.js 16, React 19, Tailwind 4 and shadcn/ui. Four-step onboarding opens a persistent reentry dashboard with **Plan** and **Resources** tabs.

## Run

```bash
# Terminal 1, repository root
make api SOURCE=real          # SOURCE=synthetic uses fictional fixtures

# Terminal 2
cd frontend
npm ci
npm run dev                   # http://localhost:3000
```

The browser calls the frontend's `/api` proxy. The API defaults to `http://localhost:8000`; set `PHOENIX_API_URL` when starting development or building production to use another address. An existing `NEXT_PUBLIC_API_URL` overrides the proxy. No LLM API key is needed.

```bash
npm test
npm run typecheck
npm run build
npm start
```

Production uses Webpack, standard Tailwind PostCSS and a bundled licensed Geist font. To build and run production alongside development, set `PHOENIX_BUILD_DIR=.next-production` for both build and start. The build output directory defaults to `.next`.

## Main flow

- **Onboarding:** About you, Daily needs, Work and Goals. Required groups allow uncertainty or privacy choices; dates and extra details are optional. Incomplete answers save as a draft on each change.
- **Plan:** One stable task list with independent expansion, status indicators, green completion and live progress. Explicit housing, food and transportation outcomes update reported access; completing research alone does not claim success.
- **Resources:** Finances, Jobs, Housing, Services and Calendar, in that order. Each opportunity offers Selected for Plan, Interested and Not Interested. Selection adds relevant plan tasks without claiming a job offer or housing placement.
- **Finances:** Uses one selected job and housing option, editable estimates and labeled U.S. household-cost defaults. Review and confirm a proposed budget before it changes future tasks.
- **Situation updates:** View / update my situation opens prefilled answers. The speech-bubble side chat interprets limited changes locally. Both require a before-and-after preview and confirmation, preserving completed work and history.
- **Calendar:** Flexible reentry steps and a separate selected-job preparation view. Suggested dates are not guaranteed appointments, hiring or training outcomes.

Job qualifications and descriptions expand on demand. Housing support is separate from aggregate rental costs. ZIP cards highlight the area's Census boundary on a detailed street map with zoom and up to ten nearby-place pins. The first three pins match each card's nearby-place list. Place coordinates are public services, never rental property locations. Public boundaries are bundled in `public/maps/`; OpenStreetMap tiles require network access. Service hours, source evidence and uncertainty remain available in disclosures.

## Persistence and recovery

Confirmed answers, qualifications, selections, task outcomes, history, budget and calendar progress save in versioned browser storage. Refresh restores the state and refreshes recommendations. Unfinished edits remain separate from the confirmed plan. Recent matching results are cached in the tab for up to 15 minutes; stale or incompatible results are fetched again. An older open tab cannot overwrite newer saved history.

Clear saved data removes the draft, session, recovery backup and cached results while keeping the theme preference. Storage is local to this browser and does not sync across devices. Storage failures show a notice; malformed canonical state offers recovery. Use fictional profiles for the demo and avoid sensitive personal details on shared devices. Sample fallback results are clearly labeled and never saved as a personalized plan.

## Key files

| File | Purpose |
| --- | --- |
| `app/page.tsx` | Page state, API integration, persistence and dashboard tabs |
| `components/OnboardingForm.tsx` | Four-step onboarding and direct situation editing |
| `components/AdaptivePlan.tsx`, `components/PlanTaskCard.tsx` | Current situation, progress, tasks and outcomes |
| `components/ResourceActions.tsx`, `components/ResourceCandidates.tsx` | Three resource choices and relevant support cards |
| `components/JobsTab.tsx`, `components/HousingTab.tsx`, `components/ServicesTab.tsx` | Resource discovery |
| `components/FinancesTab.tsx`, `lib/finances.ts` | Selected-option budget estimates and review |
| `components/JobPlan.tsx`, `lib/plan.ts` | Calendar and daily actions |
| `components/AreaMap.tsx` | Census ZIP map, zoom and nearby pins |
| `components/SituationUpdate.tsx`, `components/SituationChat.tsx`, `components/PlanPreview.tsx` | Confirmed replanning |
| `lib/api.ts`, `lib/domain.ts`, `lib/saved-session.ts` | API client, canonical types and saved-state validation |

The [implementation and verification report](../docs/reentry_planner.md) records exact checks, recommendation rules, model limitations and remaining submission artifacts.

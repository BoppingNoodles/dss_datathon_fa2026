# Phoenix frontend (MVP)

Next.js 16 + React 19 + Tailwind 4 + [shadcn/ui](https://ui.shadcn.com) (Radix, "nova" preset). One page: the five-question form, then Jobs / Housing / Services / 30-day plan tabs.

```bash
# terminal 1, from the repo root: the API
make api SOURCE=real          # or SOURCE=synthetic if you don't have the raw data

# terminal 2
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

- The API address comes from `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
- Demo deep link, which skips the form: `http://localhost:3000/?location=Oakland&need=food&age=34`
- Light and dark mode: the toggle is in the top right. The page follows the device setting until someone picks one, and the choice is remembered in the browser. Add `&theme=dark` or `&theme=light` to a link to force one. Colors are defined once in `app/globals.css` as shadcn theme tokens (`--primary`, `--card`, `--muted` and so on), with a light set and a `.dark` set.
- If the API is unreachable, the form offers sample results from `lib/sample-response.json`. That file is a copy of `backend/fixtures/recommendation_response.synthetic.json` (made-up places); refresh it with `make fixtures` and copy it again.

In Jobs, choose **Make a plan** to open a separate **30-day plan** tab. The monthly
calendar starts today and continues for 30 calendar days, with month navigation
when needed. Select a date to read its action and source links, then mark that day
complete. Daily actions adapt to the target role and whether a credential is missing
or already held. This is a preparation schedule, not a promised hiring or training
date. Submitted answers (including job qualification reports), selected goal, plan start
date, checked days, next-step checkboxes, and active tab are saved in versioned browser
storage. Refreshing reloads current recommendations and restores progress; a saved session
takes precedence over demo link parameters. New goals or submitted onboarding answers
start fresh progress. **Clear saved data** removes the saved session and returns to the
form, keeping the theme preference. Sample results are never saved. Storage is local to
this browser, does not sync between devices, and is removed if site data is cleared.
Storage failures show a notice without interrupting the current session. Onboarding answers also save locally on each change, including incomplete input.
Refreshing an unfinished form returns to that draft; successful submission or
**Back to my results** clears it. Drafts do not overwrite the submitted profile or plan.
The last matching results response is cached in this tab's session storage for up to
15 minutes, shown immediately on refresh, and refreshed in the background without
disabling the page. Clearing saved data removes the draft, session, and cached results. Interim-work selection is no longer part of the UI.
The offline sample does not generate a plan.

Job descriptions and requirements expand on demand. Housing cards show the middle
50% of snapshot rents and up to three real nearby public places. Select a housing card
to highlight the ZIP's Census ZCTA boundary on a detailed Leaflet street map. Use
the +/− buttons, keyboard, or pinch to zoom; drag to pan, and **Fit area** to reset.
The map shows up to ten nearby places. The first three numbered pins match the
card preview; select any pin for its name and directions.
The map fits both the boundary and the nearby pins, including places outside the ZIP.
Public boundaries are served locally from `public/maps/`; see its README for the
source and simplification settings. Street tiles load from OpenStreetMap and need
an internet connection. Place pins use public service coordinates from the API's
`service_map_points`; they never use a rental property location.
No rental property locations are published. Service cards use the same compact
layout, with hours, eligibility, and review evidence behind a disclosure.

The pay-versus-rent calculator is available under an expandable **Compare pay with
rent** section. Choosing a job's pay comparison opens that section automatically.

Validation: `node --test tests/*.test.mjs`, `npx tsc --noEmit`, and `npm run build`.

shadcn components live in `components/ui/` and are generated code: button, card, badge, tabs, input, label, checkbox, toggle-group, alert and native-select. Add more with `npx shadcn@latest add <name>`. Shared Phoenix pieces built on them (status badge, notes, empty state, sort toggle) are in `components/shared.tsx`.

| File | What |
| --- | --- |
| `app/page.tsx` | Page state, tabs, next steps, error and sample-data handling |
| `components/OnboardingForm.tsx` | The five questions (only location and need are required) |
| `components/ServicesTab.tsx` | Service groups and cards: verification, rating, star breakdown, sampled reviews |
| `components/JobsTab.tsx` | Job cards, target-job selection, sorting, and pay comparison |
| `components/JobPlan.tsx` | Monthly calendar, daily actions, credentials, and source links |
| `components/HousingTab.tsx` | Compact rent and nearby-place cards, ZIP map, and the pay-versus-rent calculator (`/housing-comparison`) |
| `components/AreaMap.tsx`, `lib/plan.ts` | Census ZIP map and 30-day calendar/action helpers |
| `components/ThemeToggle.tsx` | Light/dark switch |
| `lib/types.ts`, `lib/api.ts`, `lib/jobs.ts` | API types/client and shared job-pay formatting |

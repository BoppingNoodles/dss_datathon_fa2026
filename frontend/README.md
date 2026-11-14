# Phoenix frontend (MVP)

Next.js 16 + React 19 + Tailwind 4. One page: the five-question form, then Jobs / Housing / Services tabs.

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
- If the API is unreachable, the form offers sample results from `lib/sample-response.json`. That file is a copy of `backend/fixtures/recommendation_response.synthetic.json` (made-up places); refresh it with `make fixtures` and copy it again.

| File | What |
| --- | --- |
| `app/page.tsx` | Page state, tabs, next steps, error and sample-data handling |
| `components/OnboardingForm.tsx` | The five questions (only location and need are required) |
| `components/ServicesTab.tsx` | Service groups and cards: verification, rating, star breakdown, sampled reviews |
| `components/JobsTab.tsx` | Job cards per the API contract; shows "not connected yet" until job matching lands |
| `components/HousingTab.tsx` | Area rent cards and the pay-versus-rent calculator (`/housing-comparison`) |
| `lib/types.ts`, `lib/api.ts` | Types mirroring `backend/app/schemas.py`, and the API client |

# Reproduction log

Person 4 reruns from raw data to the reported results in a fresh environment before submission (Phoenix.md section 13). Add one row per rerun. Note any nondeterminism or manual step.

## Procedure (fresh clone)

```bash
git clone <repo> phoenix-rerun && cd phoenix-rerun
uv sync --group dev --frozen
# place raw files per README "Raw data"; verify SHA-256:
shasum -a 256 data/raw/places/google_maps.csv data/raw/reviews/google_maps_reviews.csv
# Prepare raw Indeed/Zillow per docs/person1_integration.md before make all.
make all SOURCE=real
# Person 2 training/evaluation commands remain pending.
git status --porcelain reports/   # any diff vs committed reports must be explained
```

**Deterministic by design.** Cleaning has no randomness. Audit sampling uses `seed: 20261114` (configs/audit.yaml), and worklist samples use seed 11. Ranking ties fall back to `place_id`.

**Manual inputs.** These are committed and hand-curated: `data/resources/service_verification.csv` and `data/resources/review_snippets.csv`. The reviewer columns in `reports/data_audit.csv` are preserved across reruns.

## Runs

| Date | Who | Environment | Scope | Result |
| --- | --- | --- | --- | --- |
| 2026-11-14 | Person 4 (dev machine, not fresh) | macOS arm64, Python 3.12.16, uv lock at commit time | Places → Reviews → index → audits → tests | `make all SOURCE=real` ran in ~7 s; 36 tests passed; privacy check passed on 6 fictional profiles |
| 2026-11-14 | Person 1 integration | Synced through 78c0854, Python 3.12.5, unchanged uv lock and frontend sources | Existing backend + 61 Person 1 tests + 11 adapter/API regression tests; real Places/Reviews rebuilt; full normalized Indeed/Zillow connected; Oakland export fallback retained | 114 tests passed; real-data privacy check passed on 6 profiles; live API returned the Oakland target/interim plan with 14 steps; frontend production build passed; browser form → 19 jobs / 14 housing areas / services, pay/rent comparison, and theme controls worked at desktop/mobile sizes. No final trained model evaluation claimed. |
| | | **fresh clone** | full pipeline incl. Persons 1–2 | pending |
| 2026-11-14 | Person 1 qualification fix | Main through 598353c plus concurrent backend listing changes, Python 3.12.5, unchanged dependency lock | Degree/experience extraction, role-specific matching, interim eligibility, and public evidence handling | 172 tests passed in the shared checkout, including 39 new qualification/API regression cases; all six real-data privacy profiles passed; the live Oakland API excludes Forklift Technician and returns the 15-step selected target/interim preparation flow |

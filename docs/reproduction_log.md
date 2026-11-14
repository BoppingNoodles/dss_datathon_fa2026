# Reproduction log

Person 4 reruns from raw data to the reported results in a fresh environment before submission (Phoenix.md section 13). Add one row per rerun. Note any nondeterminism or manual step.

## Procedure (fresh clone)

```bash
git clone <repo> phoenix-rerun && cd phoenix-rerun
uv sync --group dev --frozen
# place raw files per README "Raw data"; verify SHA-256:
shasum -a 256 data/raw/places/google_maps.csv data/raw/reviews/google_maps_reviews.csv
make all SOURCE=real
# Person 1 / Person 2 steps: append their commands here once they exist
git status --porcelain reports/   # any diff vs committed reports must be explained
```

**Deterministic by design.** Cleaning has no randomness. Audit sampling uses `seed: 20261114` (configs/audit.yaml), and worklist samples use seed 11. Ranking ties fall back to `place_id`.

**Manual inputs.** These are committed and hand-curated: `data/resources/service_verification.csv` and `data/resources/review_snippets.csv`. The reviewer columns in `reports/data_audit.csv` are preserved across reruns.

## Runs

| Date | Who | Environment | Scope | Result |
| --- | --- | --- | --- | --- |
| 2026-11-14 | Person 4 (dev machine, not fresh) | macOS arm64, Python 3.12.16, uv lock at commit time | Places → Reviews → index → audits → tests | `make all SOURCE=real` ran in ~7 s; 36 tests passed; privacy check passed on 6 fictional profiles |
| | | **fresh clone** | full pipeline incl. Persons 1–2 | pending |

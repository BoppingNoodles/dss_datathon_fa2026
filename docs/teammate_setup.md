# Run Phoenix with the same data as the team

The data is intentionally Git-ignored. Pulling `main` updates code, not jobs,
rentals, or services. Different local data directories explain why teammates see
different working tabs. `not_integrated` can mean missing normalized files; it
does not necessarily mean the integration code is absent.

## Download once; no raw-data processing required

Download [phoenix-real-runtime-v1.tar.gz](https://drive.google.com/file/d/1ydyOiYhcBZcHrhqEHBYXTQYuFVTvQIVR/view?usp=drivesdk)
from the existing [team Drive folder](https://drive.google.com/drive/folders/1iGJ511t7Enpj9ShRZmMOkOH0FvRjpSut).
Its existing sharing was preserved. Keep this handoff with the team; do not commit
datasets to Git or republish them elsewhere.

- Compressed size: **90,833,382 bytes** (90.8 MB / 86.6 MiB).
- SHA-256: `7b0612e94cd1015b970ada0301b92ef495e550fbb732d26ffeb263d250ab9da4`.
- Contents: **46,776 jobs**, **66,570 rental candidates**, **17,567 service
  candidate rows**, city/ZIP reference points, coverage and service statistics.
- Eight runtime files plus a checksum manifest; no raw CSVs, user profiles,
  SQLite intermediates, or build/audit caches.
- These are provided snapshots, not confirmation of current availability or eligibility.

## Quick start (works on current main, even before the setup fixes are shared)

Use your actual team checkout. On Max's Mac it is `/Users/maxli/dss_datathon_fa2026`;
the saved Phoenix project can point at the older `/Users/maxli/Documents/ChatGPT/Phoenix`
workspace. On another machine, replace the first path with your own clone path.
If you have local code changes, preserve them before syncing with the team.

```sh
cd /Users/maxli/dss_datathon_fa2026
git rev-parse --show-toplevel
git status --short
uv sync --group dev --frozen
```

Assuming the browser downloaded the archive into `~/Downloads`:

```sh
shasum -a 256 "$HOME/Downloads/phoenix-real-runtime-v1.tar.gz"
# Compare the output with the SHA-256 above before extracting.
mkdir -p data/processed/real
tar -xzf "$HOME/Downloads/phoenix-real-runtime-v1.tar.gz" -C data/processed/real
make api SOURCE=real
```

The archive has flat filenames: `jobs.jsonl`, `rentals.jsonl`,
`person1_coverage.json`, `service_candidates.parquet`,
`area_reference_points.parquet`, `places_stats.json`, `reviews_stats.json`, and
`index_stats.json`, plus `runtime_manifest.json`. They must end up directly inside
`data/processed/real/`, without another nested directory. Extraction replaces
those runtime files; it leaves other processed/raw files alone. Stop the API
before installing/replacing data, then restart it to clear process caches.

When the setup changes in this chat have been shared, use the verified installer
instead of the `mkdir`/`tar` commands. It validates the file list, sizes, checksums,
and real-mode manifest before replacing runtime files:

```sh
make data-install BUNDLE="$HOME/Downloads/phoenix-real-runtime-v1.tar.gz"
make data-check SOURCE=real
make api SOURCE=real
```

In a second terminal, from the same checkout:

```sh
cd frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev -- --port 3000
```

Open `http://localhost:3000`. The backend is `http://localhost:8000/docs`.
Restart the frontend after changing `NEXT_PUBLIC_API_URL`. If Next offers port
3001 because 3000 is occupied, stop your previous dev server and reuse 3000, or
explicitly include the new frontend origin in `PHOENIX_CORS_ORIGINS` when starting
the backend. The default backend CORS origin is `http://localhost:3000`.

## Verify before debugging the UI

```sh
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/recommendations \
  -H 'Content-Type: application/json' \
  -d '{"location":"Oakland","priority_need":"work"}' \
  | uv run python -c 'import json,sys; d=json.load(sys.stdin); print({k:d[k]["status"] for k in ("jobs","housing_areas","services")}); print(d["data_coverage"]["mode"])'
```

Expected for Oakland: `jobs`, `housing_areas`, and `services` are all `ok`, with
coverage mode `real`. Health has `source: real` and `service_candidates: 17567`.
With this chat's health fix, it also shows the exact `project_root`,
`data_directory`, and separate `ready` / `missing` / `invalid` diagnostics for each
section. The older health endpoint checks only services: `status: ok` there is
not proof that jobs or housing are installed. HTTP 200 from health alone is not
proof of full data readiness either; inspect its JSON status.

| Local data state | Expected result |
| --- | --- |
| Services only | Services can work; jobs/housing may say `not_integrated`. |
| `data/processed/indeed/jobs.jsonl` + full `coverage.json` only | Jobs can work; housing/services are absent. This is intentionally a jobs-only path. |
| Full normalized jobs/rentals, no services | Jobs/housing work after the loader fix; services have no results. Older code can reject the whole request. |
| Runtime bundle installed in `real/` | All three sections work for a covered city such as Oakland. |
| Fictional fixtures, API explicitly set to synthetic | All three sections use fictional data; coverage mode is `synthetic`. |

Other locations can legitimately have `no_results` because coverage is limited.
If health is correct but the UI is stale, confirm its API URL and restart both
dev servers. If health shows the wrong root, restart the backend from the actual
team clone. Check existing listeners with `lsof -nP -iTCP:8000 -iTCP:3000 -sTCP:LISTEN`
on macOS; stop your old processes in their terminals rather than starting a second
copy over them.

## Fictional demo or raw-data rebuild

For an explicitly fictional demo with no downloads:

```sh
make fixtures
make api SOURCE=synthetic
```

`make fixtures` does **not** install real jobs, rentals, or services. Synthetic
requests never fall back to real data. Conversely, `make api SOURCE=real` does
not create or download missing data.

Do not run `make all`, `make services`, or `make person1` just to use the runtime
bundle: those are processing/export commands, and some need raw inputs or audit
intermediates that this runtime-only handoff deliberately excludes. Raw-data
reproduction remains documented in `docs/person1_integration.md` and the README.
The minimal bundle supports the API, not all offline audits.

To regenerate the handoff from a complete, verified real setup:

```sh
make data-bundle
```

It creates ignored `data/processed/phoenix-real-runtime-v1.tar.gz` and a sibling
`.sha256` file. Share the archive and checksum together through the existing team
handoff. A newly generated archive can have a different outer checksum; use its
own `.sha256` file. Its internal manifest checks each of the eight runtime files.

## Verification in this chat

On 2026-11-14, the downloaded-data workflow was reproduced in a fresh temporary
checkout with no raw data. The bundle installer verified all files; loading
returned exactly 46,776 jobs and 66,570 rental candidates. An Oakland
`POST /recommendations` returned HTTP 200, all three sections `ok`, 14 housing
areas, and 64 job cards. The synthetic tests also cover missing/partial data,
jobs-only mode, source selection, invalid source labels, and bundle corruption,
links, duplicate members, and path traversal. Existing frontend/qualification
work was preserved; no dataset was added to Git.

"""Print header, fill rate, and one example per column for the raw Places/Reviews exports.

    uv run python -m src.data.inspect_headers --source real [--rows 2000]

Use before trusting configs/columns.yaml. Example values from reviewer-identity columns
are suppressed so they never end up in logs or notes.
"""

from __future__ import annotations

import argparse

import pandas as pd

from src.common import load_config, source_files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["real", "synthetic"], default="real")
    ap.add_argument("--rows", type=int, default=2000)
    args = ap.parse_args()
    sensitive = load_config("columns")["reviews"]["never_read_fragments"] + ["reviewer", "top_reviews", "snippets"]
    files = source_files(args.source)
    for key in ("places_file", "reviews_file"):
        path = files[key]
        if not path.exists():
            print(f"\n== {path}: MISSING")
            continue
        df = pd.read_csv(path, nrows=args.rows, dtype=str)
        print(f"\n== {path.name}: {len(df.columns)} columns (first {len(df)} rows)")
        for c in df.columns:
            s = df[c].dropna()
            hidden = any(f in c.lower() for f in sensitive)
            ex = "<suppressed>" if hidden else (repr(str(s.iloc[0])[:80]) if len(s) else "")
            print(f"  {c:32} fill={len(s) / max(len(df), 1):.2f}  {ex}")


if __name__ == "__main__":
    main()

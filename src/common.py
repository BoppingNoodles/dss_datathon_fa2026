"""Shared helpers: paths, config loading, parsing, and geometry.

Nothing here invents values. Every parser returns None/NaN when the input cannot be
interpreted, so missing information stays visibly missing downstream.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"
REPORTS = ROOT / "reports"
EARTH_RADIUS_MILES = 3958.7613


# --------------------------------------------------------------------------- config / paths


@lru_cache(maxsize=None)
def load_config(name: str) -> dict[str, Any]:
    with open(CONFIGS / f"{name}.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def processed_dir(source: str) -> Path:
    if source not in ("real", "synthetic"):
        raise ValueError(f"source must be 'real' or 'synthetic', got {source!r}")
    d = ROOT / "data" / "processed" / source
    d.mkdir(parents=True, exist_ok=True)
    return d


def source_files(source: str) -> dict[str, Path]:
    cfg = load_config("columns")["sources"][source]
    return {k: resolve(v) for k, v in cfg.items()}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o.relative_to(ROOT)) if o.is_relative_to(ROOT) else str(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


# --------------------------------------------------------------------------- value parsing

_TRUE = {"true", "t", "yes", "y", "1", "1.0"}
_FALSE = {"false", "f", "no", "n", "0", "0.0"}


def to_bool(value: Any) -> bool | None:
    """Normalize closure-style flags. Anything uninterpretable is None (unknown), not False."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    s = str(value).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    return None


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def parse_categories(*values: Any) -> list[str]:
    """Split category / all_categories cells into unique, trimmed tags (order preserved).

    Handles JSON / Python list literals ("['Food bank', 'Charity']") and delimited strings.
    """
    tags: list[str] = []
    for value in values:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        if isinstance(value, (list, tuple, np.ndarray)):
            parts: Iterable[Any] = value
        else:
            s = str(value).strip()
            if not s:
                continue
            parts = None  # type: ignore[assignment]
            if s[0] in "[(":
                for loader in (json.loads, ast.literal_eval):
                    try:
                        loaded = loader(s)
                        if isinstance(loaded, (list, tuple)):
                            parts = loaded
                            break
                    except (ValueError, SyntaxError, json.JSONDecodeError):
                        continue
            if parts is None:
                parts = re.split(r"\s*[;|,]\s*", s.strip("[]()"))
        for p in parts:
            t = str(p).strip().strip("'\"").strip()
            if t and t.lower() not in {x.lower() for x in tags}:
                tags.append(t)
    return tags


_ZIP_RE = re.compile(r"\b(?:CA|California)\s+(\d{5})(?:-\d{4})?\b", re.IGNORECASE)
_ZIP_FALLBACK_RE = re.compile(r"\b(9[0-6]\d{3})(?:-\d{4})?\b")


def parse_zip(address: Any) -> str | None:
    """Extract a California ZIP from a business address; None when not unambiguous."""
    if not isinstance(address, str) or not address.strip():
        return None
    m = _ZIP_RE.search(address)
    if m:
        return m.group(1)
    found = _ZIP_FALLBACK_RE.findall(address)
    return found[-1] if len(found) == 1 else None


def parse_city(address: Any) -> str | None:
    """'123 Main St, Oakland, CA 94612' -> 'Oakland'. None when the pattern is not present."""
    if not isinstance(address, str):
        return None
    parts = [p.strip() for p in address.split(",") if p.strip()]
    for i, part in enumerate(parts):
        if re.match(r"^(CA|California)\b", part, re.IGNORECASE) and i > 0:
            return normalize_city(parts[i - 1])
    return None


def normalize_city(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = re.sub(r"\s+", " ", value).strip()
    if not s or any(ch.isdigit() for ch in s):
        return None
    return s.title()


def normalize_location_input(value: str) -> tuple[str, str]:
    """User onboarding location -> ('zip', '94612') or ('city', 'Oakland')."""
    s = value.strip()
    m = re.fullmatch(r"(\d{5})(?:-\d{4})?", s)
    if m:
        return "zip", m.group(1)
    s = re.sub(r",?\s*(CA|California)\.?$", "", s, flags=re.IGNORECASE)
    return "city", normalize_city(s) or s


# --------------------------------------------------------------------------- geometry


def haversine_miles(lat1: Any, lon1: Any, lat2: Any, lon2: Any) -> np.ndarray:
    """Great-circle (straight-line) distance in miles. Not a walking, transit, or driving time."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype=float)) for x in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def none_if_nan(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, np.generic):
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v

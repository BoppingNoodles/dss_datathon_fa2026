"""Map Places category tags to the reviewed service taxonomy (configs/service_taxonomy.yaml)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from src.common import load_config


@dataclass(frozen=True)
class Family:
    key: str
    label: str
    needs: tuple[str, ...]
    assistance: bool
    include: re.Pattern[str]
    exclude: re.Pattern[str] | None


def _compile(terms: list[str]) -> re.Pattern[str] | None:
    if not terms:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")", re.IGNORECASE)


@lru_cache(maxsize=1)
def families() -> tuple[Family, ...]:
    cfg = load_config("service_taxonomy")["families"]
    return tuple(
        Family(
            key=k,
            label=v["label"],
            needs=tuple(v["needs"]),
            assistance=bool(v["assistance"]),
            include=_compile(v["include"]),  # type: ignore[arg-type]
            exclude=_compile(v.get("exclude") or []),
        )
        for k, v in cfg.items()
    )


def family_by_key() -> dict[str, Family]:
    return {f.key: f for f in families()}


def need_labels() -> dict[str, str]:
    return load_config("service_taxonomy")["need_labels"]


def classify(tags: list[str]) -> tuple[list[str], str | None]:
    """Return (matched family keys in taxonomy order, 'family:tag' evidence for the primary match).

    A tag is ignored for a family when it matches that family's exclude pattern.
    """
    matched: list[str] = []
    evidence: str | None = None
    for fam in families():
        for tag in tags:
            if fam.exclude is not None and fam.exclude.search(tag):
                continue
            if fam.include.search(tag):
                matched.append(fam.key)
                if evidence is None:
                    evidence = f"{fam.key}:{tag}"
                break
    return matched, evidence


def families_for_need(need: str) -> tuple[list[str], list[str]]:
    """(assistance families, ordinary-essential families) serving a need, in taxonomy order."""
    assist = [f.key for f in families() if need in f.needs and f.assistance]
    ordinary = [f.key for f in families() if need in f.needs and not f.assistance]
    return assist, ordinary

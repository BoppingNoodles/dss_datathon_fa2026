"""A cached picker of recognized credentials actually mentioned in loaded jobs."""

from collections import Counter
from functools import lru_cache

import re

from src.common import processed_dir
from src.phoenix.credentials import _PATTERNS, credential_key
from src.recommend import person1_data
from src.recommend.person1_data import Person1DataUnavailable

_TRIGGERS = {
    "Class-A CDL": ("cdl", "commercial"), "Class-B CDL": ("cdl", "commercial"),
    "Driver's license": ("driver",), "Security guard card": ("guard", "bsis"),
    "Basic Life Support (BLS)": ("bls", "basic life"),
    "Advanced Cardiovascular Life Support (ACLS)": ("acls", "advanced cardiovascular"),
    "Registered nurse (RN) license": ("rn", "registered nurse"),
    "Licensed vocational nurse (LVN) license": ("lvn", "vocational nurse"),
    "Certified nursing assistant (CNA)": ("cna", "nursing assistant"),
    "EPA Section 608 certification": ("608",),
}
_MATCHERS = [(label, re.compile(pattern, re.I), _TRIGGERS.get(label, (label.split()[0].casefold(),)))
             for label, pattern in _PATTERNS]


def credentials_in_jobs(jobs):
    counts, labels = Counter(), {}
    for job in jobs:
        found = {credential_key(str(req.value)): str(req.value) for req in job.requirements if req.field == "certification"}
        text = job.description.casefold()
        for label, pattern, triggers in _MATCHERS:
            if any(trigger in text for trigger in triggers) and pattern.search(job.description):
                found[credential_key(label)] = label
        for key, label in found.items():
            counts[key] += 1
            labels[key] = label
    return [{"label": labels[key], "posting_count": counts[key]} for key in sorted(counts, key=lambda key: labels[key].casefold())]


@lru_cache(maxsize=4)
def _catalog(source, revision):
    try:
        jobs, _, _ = person1_data.load_person1(source)
    except Person1DataUnavailable:
        if source != "real":
            raise
        jobs, _ = person1_data.load_indeed_jobs()
    return {"status": "ok", "certificates": credentials_in_jobs(jobs),
            "notes": ["Recognized certificates and licenses mentioned in this Indeed snapshot. Mentions may be optional; the list is not exhaustive."]}


def certificate_catalog(source):
    paths = [processed_dir(source) / name for name in ("jobs.jsonl", "rentals.jsonl", "person1_coverage.json")]
    if source == "real":
        paths.extend(person1_data.INDEED_DIR / name for name in ("jobs.jsonl", "coverage.json"))
    revision = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths if path.exists())
    try:
        return _catalog(source, revision)
    except (Person1DataUnavailable, OSError, ValueError):
        return {"status": "not_integrated", "certificates": [], "notes": ["The certificate list is unavailable until the jobs dataset is loaded."]}

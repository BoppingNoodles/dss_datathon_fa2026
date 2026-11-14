"""Conservative credential hints for planning, backed by exact posting evidence.

Not a complete requirement parser. Unrecognized/unstated credentials are never
treated as verified absent; Caden's structured requirements remain authoritative.
"""

from __future__ import annotations

import re

from .models import Job, Requirement, UserProfile

_PATTERNS = [
    ("Class-A CDL", r"\b(?:class[ -]*a\s+(?:cdl|commercial\s+driver[’']?s?\s+licen[sc]e)|cdl[ -]*a)\b"),
    ("Forklift operator training and evaluation", r"\bforklift(?:\s+operator)?\s+certif(?:ication|ied)\b"),
    ("Driver's license", r"\b(?:valid|current)\s+(?:(?:ca|california)\s+)?driver[’']?s?\s+licen[sc]e\b"),
    ("Security guard card", r"\b(?:guard\s+card|bsis\s+(?:card|registration))\b"),
]


def credential_key(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    if text in {"cdl a", "class a cdl", "class a commercial driver s license"}:
        return "class a cdl"
    if text in {"forklift", "forklift certification", "forklift operator certification", "forklift operator training and evaluation"}:
        return "forklift"
    if text in {"driver license", "drivers license", "driver s license", "ca driver s license", "california driver s license"}:
        return "drivers license"
    return text


def credential_reported_held(value: str, profile: UserProfile) -> bool:
    key = credential_key(value)
    return any(credential_key(c) == key for c in profile.education.certifications)


def with_credential_evidence(job: Job) -> Job:
    requirements = list(job.requirements)
    known = {credential_key(str(r.value)) for r in requirements if r.field == "certification"}
    # Keep sentences small enough that 'preferred' for another credential does not
    # automatically change a required credential elsewhere in the posting.
    sentences = re.split(r"(?<=[.!?])\s+|(?=Certifications:|Requirements:)", job.description)
    for label, pattern in _PATTERNS:
        if credential_key(label) in known:
            continue
        for sentence in sentences:
            match = re.search(pattern, sentence, re.I)
            if not match:
                continue
            before = sentence[max(0, match.start()-45):match.start()]
            after = sentence[match.end():match.end()+55]
            context = before + match.group() + after
            if re.search(r"\b(?:no|not)\s+(?:\w+\s+){0,2}$", before, re.I) or re.match(r"\s+(?:is\s+)?not\s+required\b", after, re.I):
                continue
            if re.search(r"\b(?:or|either|equivalent)\b", context, re.I):
                kind = "alternative"
            elif re.match(r"\s+(?:is\s+)?preferred\b", after, re.I) or re.search(r"\bpreferred\s*$", before, re.I):
                kind = "preferred"
            elif re.search(r"\b(?:required|must|valid|current)\b|\bcertifications\s*:", context, re.I) or label == "Driver's license":
                kind = "required"
            else:
                kind = "uncertain"
            evidence = sentence[max(0, match.start()-80):min(len(sentence), match.end()+150)].strip()
            requirements.append(Requirement(field="certification", value=label, kind=kind,
                                            evidence=evidence, source="posting_credential_hints_v1"))
            known.add(credential_key(label))
            break
    if "forklift" not in known and re.search(r"\bforklift\b.*\boperator\b|\boperator\b.*\bforklift\b", job.title, re.I):
        requirements.append(Requirement(field="certification", value="Forklift operator training and evaluation",
            kind="uncertain", evidence=f"Role title: {job.title}. Confirm the employer's operator training and evaluation pathway.",
            source="operator_role_check:https://www.dir.ca.gov/title8/3668.html"))
    return job.model_copy(update={"requirements": requirements})


def credential_summary(requirements: list[Requirement], profile: UserProfile) -> str:
    required = [r for r in requirements if r.field == "certification" and r.kind == "required"]
    unconfirmed = [str(r.value) for r in required if not credential_reported_held(str(r.value), profile)]
    if unconfirmed:
        return "Credential to confirm or work toward: " + "; ".join(unconfirmed) + ". Selectable for a preparation plan."
    if required:
        return "Required credentials reported held; confirm employer acceptance and validity."
    if any(r.field == "certification" and r.kind in {"uncertain", "alternative"} for r in requirements):
        return "Credential details or alternatives need employer confirmation; selectable for a preparation plan."
    return "No required certification identified in available structured/hinted requirements; confirm the full posting with the employer."

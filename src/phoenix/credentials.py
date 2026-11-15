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
    ("Class-B CDL", r"\b(?:class[ -]*b\s+(?:cdl|commercial\s+driver[’']?s?\s+licen[sc]e)|cdl[ -]*b)\b"),
    ("ServSafe certification", r"\bservsafe\b"),
    ("Food handler card", r"\bfood[ -]handler(?:[’']?s)?\s+(?:card|certificat(?:e|ion)|permit)\b"),
    ("CPR certification", r"\bCPR\s*(?:(?:and|/|&)\s*first aid\s*)?(?:certificat(?:e|ion)|certified)\b"),
    ("First aid certification", r"\bfirst[ -]aid\s+(?:certificat(?:e|ion)|certified)\b"),
    ("Basic Life Support (BLS)", r"\b(?:BLS\s+(?:certificat(?:e|ion)|certified)|basic life support)\b"),
    ("Advanced Cardiovascular Life Support (ACLS)", r"\b(?:ACLS\s+(?:certificat(?:e|ion)|certified)|advanced cardiovascular life support)\b"),
    ("Registered nurse (RN) license", r"\b(?:RN\s+licen[sc]e|registered nurse\s+licen[sc]e)\b"),
    ("Licensed vocational nurse (LVN) license", r"\b(?:LVN\s+licen[sc]e|licensed vocational nurse)\b"),
    ("Certified nursing assistant (CNA)", r"\b(?:CNA\s+(?:certificat(?:e|ion)|certified)|certified nursing assistant)\b"),
    ("OSHA 10 training", r"\bOSHA[ -]*10\b"),
    ("OSHA 30 training", r"\bOSHA[ -]*30\b"),
    ("EPA Section 608 certification", r"\b(?:EPA\s+(?:section\s+)?608|section\s+608\s+certificat(?:e|ion))\b"),
]

_ALIASES = {
    "servsafe": {"servsafe", "servsafe certification"},
    "food handler": {"food handler", "food handler card", "food handlers card", "food handler certification"},
    "cpr": {"cpr", "cpr certification", "cpr certified"},
    "first aid": {"first aid", "first aid certification", "first aid certified"},
    "bls": {"bls", "bls certification", "basic life support", "basic life support bls"},
    "acls": {"acls", "acls certification", "advanced cardiovascular life support", "advanced cardiovascular life support acls"},
    "rn": {"rn", "rn license", "registered nurse license", "registered nurse rn license"},
    "lvn": {"lvn", "lvn license", "licensed vocational nurse lvn license"},
    "cna": {"cna", "cna certification", "certified nursing assistant", "certified nursing assistant cna"},
    "security guard card": {"security guard card", "guard card", "bsis guard card", "bsis registration"},
    "osha 10": {"osha 10", "osha 10 training", "osha 10 card"},
    "osha 30": {"osha 30", "osha 30 training", "osha 30 card"},
    "epa 608": {"epa 608", "epa section 608", "epa section 608 certification", "section 608 certification"},
}


def credential_key(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    for key, names in _ALIASES.items():
        if text in names:
            return key
    if text in {"cdl a", "class a cdl", "class a commercial driver s license"}:
        return "class a cdl"
    if text in {"cdl b", "class b cdl", "class b commercial driver s license"}:
        return "class b cdl"
    if text in {"forklift", "forklift certification", "forklift operator certification", "forklift operator training and evaluation"}:
        return "forklift"
    if text in {"driver license", "drivers license", "driver s license", "ca driver s license", "california driver s license"}:
        return "drivers license"
    return text


def credential_reported_held(value: str, profile: UserProfile, *, job_id: str | None = None,
                             requirement: Requirement | None = None) -> bool:
    if job_id and requirement and requirement.key in profile.qualification_answers.get(job_id, {}):
        return profile.qualification_answers[job_id][requirement.key]
    key = credential_key(value)
    return any(credential_key(c) == key for c in profile.education.certifications)


def with_credential_evidence(job: Job) -> Job:
    requirements = list(job.requirements)
    known = {credential_key(str(r.value)) for r in requirements if r.field == "certification"}
    # Keep sentences small enough that 'preferred' for another credential does not
    # automatically change a required credential elsewhere in the posting.
    text = re.sub(r"(?<![A-Z])(?=(?:Experience|Education|License/Certification|Ability to Commute|Work Location):)", "\n", job.description)
    sentences = re.split(r"\n|(?<=[.!?])\s+|(?=Certifications:|Requirements:)", text)
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


def credential_summary(requirements: list[Requirement], profile: UserProfile, *, job_id: str | None = None) -> str:
    required = [r for r in requirements if r.field == "certification" and r.kind == "required"]
    unconfirmed = [str(r.value) for r in required if not credential_reported_held(str(r.value), profile, job_id=job_id, requirement=r)]
    if unconfirmed:
        return "Credential to confirm or work toward: " + "; ".join(unconfirmed) + ". Selectable for a preparation plan."
    if required:
        return "Required credentials reported held; confirm employer acceptance and validity."
    if any(r.field == "certification" and r.kind in {"uncertain", "alternative"} for r in requirements):
        return "Credential details or alternatives need employer confirmation; selectable for a preparation plan."
    return "No required certification identified in available structured/hinted requirements; confirm the full posting with the employer."

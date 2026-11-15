"""Evidence-backed qualification rules for matching; not the trained classifier.

Extract only stated education/experience criteria. Preserve curated/model inputs,
negation, preferences, and alternatives. Unstated qualifications stay unknown.
"""

from __future__ import annotations

import re
from functools import lru_cache

from src.data.scrape_indeed import NON_APPLICANT, NON_REQUIRED_CONTEXT, description_segments

from .credentials import credential_reported_held, with_credential_evidence
from .models import Job, QualificationCheck, Requirement, UserProfile

SOURCE = "posting_qualification_rules_v1"
LEVELS = {"none": 0, "high_school": 1, "some_college": 2, "associate": 3, "bachelor": 4, "master": 5, "doctorate": 6}
SKILL_FAMILIES = {
    "warehouse": ["warehouse", "forklift", "logistics", "inventory", "shipping", "receiving", "fulfillment", "stockroom", "stock clerk", "package handler", "material handler", "order picker"],
    "customer service": ["customer service", "customer support", "call center", "retail", "cashier", "sales associate"],
    "food service": ["food service", "restaurant", "cook", "kitchen", "barista", "dishwasher", "food preparation"],
    "construction": ["construction", "carpentry", "carpenter", "laborer", "labourer"],
    "cleaning": ["cleaning", "janitor", "janitorial", "custodian", "housekeeping"],
    "driving": ["delivery driver", "truck driver", "driving", "courier", "tractor/trailer", "tractor trailer", "commercial driving", "truck driving"],
    "administration": ["administrative", "administration", "data entry", "receptionist", "office assistant", "office work"],
    "landscaping": ["landscaping", "landscaper", "groundskeeper", "groundskeeping", "gardening", "gardener"],
    "caregiving": ["caregiving", "caregiver", "personal care aide", "home health aide"],
    "equipment repair": ["mechanic", "mechanical repair", "equipment repair", "industrial maintenance", "forklift maintenance", "forklift repair", "service technician", "field service technician", "maintenance technician", "equipment technician", "forklift technician", "hydraulics", "diesel technician", "automotive technician"],
}
_REPAIR_TITLE = re.compile(r"\b(?:forklift|industrial|equipment|diesel|automotive|maintenance|field service)\b.*\b(?:technician|mechanic|engineer)\b|\b(?:technician|mechanic)\b.*\b(?:forklift|industrial|equipment|diesel|automotive)\b", re.I)
_NUMBERS = {"zero":0, "one":1, "two":2, "three":3, "four":4, "five":5, "six":6, "seven":7, "eight":8, "nine":9, "ten":10}
_NUMBER = r"(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten)"
_DURATION = re.compile(rf"\b(?P<minimum>{_NUMBER})(?:\s*\(\d+\))?(?:\s*(?:[-–]|to)\s*{_NUMBER})?\s*(?:\+|or more)?\s*(?P<unit>years?|yrs?|months?)\b", re.I)
_EDUCATION = [
    ("doctorate", re.compile(r"\b(?:doctorate|doctoral degree|Ph\.?D\.?)\b", re.I)),
    ("master", re.compile(r"\bmaster(?:['’]s|s)?(?=\s+(?:degree|in\b|required|preferred|or\s+bachelor))\s*(?:degree|in\b)?", re.I)),
    ("bachelor", re.compile(r"\b(?:bachelor(?:['’]s|s)?\s+of\s+(?:science|arts)|(?:bachelor(?:['’]s|s)?|B\.?S\.?|B\.?A\.?)(?=\s+(?:degree|in\b|required|preferred|or\s+master))\s*(?:degree|in\b)?)", re.I)),
    ("associate", re.compile(r"\bassociate(?:['’]s|s)?\s+(?:degree|in\b)", re.I)),
    ("high_school", re.compile(r"\b(?:high[ -]school\s+(?:diploma|education|degree|graduate)|HS diploma|G\.?E\.?D\.?)\b", re.I)),
]
_REQUIRED = re.compile(r"\b(?:required|requires?|must|minimum|at least|mandatory)\b", re.I)
_PREFERRED = re.compile(r"\b(?:preferred|desired|optional|a plus|nice to have)\b", re.I)
_CROSS_ALTERNATIVE = re.compile(r"\bor\s+(?:equivalent\s+)?(?:[\w'-]+\s+){0,4}experience\b|\bin lieu of\b|\bexperience\b.{0,50}\bor\b.{0,40}\bdegree\b", re.I)
_TRAINING_ALTERNATIVE = re.compile(r"\b(?:less|fewer) than\b.{0,100}\b(?:training|trainee)\b|\b(?:without|no)\b.{0,50}\bexperience\b.{0,50}\b(?:training|trainee)\b", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


def redact_contacts(text: str) -> str:
    return _EMAIL.sub("[contact omitted]",text)


def _excerpt(text: str, start: int, end: int) -> str:
    return redact_contacts(text[max(0,start-45):min(len(text),end+180)].strip())


def contains(text: str, term: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", text.casefold()) is not None


def experience_text(profile: UserProfile) -> str:
    # A reported certificate does not establish work experience. Ignore plainly
    # negated free-text claims; selected skill chips remain positive statements.
    statements = re.split(r"[,.;\n]|\bbut\b", profile.experience.text, flags=re.I)
    positive = [s for s in statements if not re.search(r"\b(?:no|not|never|without|lack)\b", s, re.I)]
    return " ".join(profile.experience.skills + positive).casefold()


def repair_experience_reported(text: str) -> bool:
    return any(contains(text, term) for term in SKILL_FAMILIES["equipment repair"])


def title_scope_matches(title: str, text: str) -> bool:
    return not _REPAIR_TITLE.search(title) or repair_experience_reported(text)


def _kind(text: str, start: int, end: int, section: str, field: str) -> str | None:
    before, after = text[max(0,start-55):start], text[end:end+100]
    if re.search(r"\b(?:no|without|not)\s+(?:\w+\s+){0,3}$", before, re.I) or re.match(r"\s*(?:is\s+|are\s+)?not\s+(?:required|needed|necessary)\b", after, re.I):
        return None
    if re.match(r"\s*(?:is\s+|are\s+)?(?:preferred|desired|optional|a plus)\b", after, re.I) or re.search(r"\b(?:preferred|desired|optional)\s*$", before, re.I):
        return "preferred"
    if field == "experience_years" and re.search(r"\bno\s+(?:\w+\s+){0,4}experience\b|\bexperience\s+(?:is\s+)?not\s+(?:required|needed|necessary)\b",text,re.I):
        return None
    if _PREFERRED.search(before+after) and not _REQUIRED.search(before+after):
        return "preferred"
    if section == "optional":
        return "uncertain" if _REQUIRED.search(before+after) else "preferred"
    if _CROSS_ALTERNATIVE.search(text) or (field == "experience_years" and _TRAINING_ALTERNATIVE.search(text)):
        return "alternative"
    if _REQUIRED.search(before+after) or section in {"required", "qualifications"}:
        return "required"
    if _PREFERRED.search(text):
        return "preferred"
    return "uncertain"


def _scope(text: str, duration_end: int) -> str | None:
    tail = text[duration_end:]
    match = re.search(r"\bexperience\b", tail, re.I)
    if not match:
        scope = re.sub(r"^\s*(?:in|as|with)\s+", "",tail,flags=re.I).strip(" .:")
    else:
        before = re.sub(r"^\W*(?:of\s+)?(?:(?:relevant|verifiable|prior|previous|professional|related)\s+)*", "", tail[:match.start()], flags=re.I).strip()
        after = re.sub(r"^\s*(?:in|as|with)\s+(?:(?:a|an|the)\s+)?", "", tail[match.end():], flags=re.I)
        scope = before or after
    scope = re.split(r"(?<=[a-z])(?=[A-Z][A-Za-z]+[®™])", scope, maxsplit=1)[0]
    scope = re.split(r"[.;()]|\b(?:required|preferred|desired|is required|are required)\b", scope, maxsplit=1, flags=re.I)[0].strip(" ,:-")
    if not scope:
        # Indeed's flattened form fields also use "Experience: clinical: 2 years".
        duration = _DURATION.search(text[:duration_end])
        prefix = text[:duration.start()] if duration else ""
        field = re.fullmatch(r"\s*Experience:\s*([^:]+):\s*", prefix, re.I)
        scope = field[1].strip() if field else ""
    if not scope or scope.casefold() in {"relevant", "related", "work", "prior", "previous"}:
        return None
    return _EMAIL.sub("[contact omitted]",scope[:180])


def _segments(description: str):
    # Flattened CSV text contains uppercase headings and inline field labels.
    text = re.sub(r"\b(PREFERRED QUALIFICATIONS|POSITION QUALIFICATIONS|MINIMUM QUALIFICATIONS|REQUIREMENTS|EDUCATION|EXPERIENCE|BENEFITS|RESPONSIBILITIES)\b:?(?![a-z])", r"\n\1:\n", description)
    text = re.sub(r"\bRequirements\s+(?=Education:)", "Requirements:\n", text)
    text = re.sub(r"(?<![A-Z])((?:Education|Experience|Certifications|Additional Requirements|License/Certification|Ability to Commute|Ability to Relocate|Work Location|Job Type|Pay|Benefits):)", r"\n\1", text)
    text = re.sub(r"\b(Qualifications|Minimum Qualifications|Required Qualifications)\s+(?=[A-Z])", r"\n\1:\n", text)
    text = re.sub(r"\b(About Us|Benefits|Responsibilities|Other Details)\s+(?=[A-Z])", r"\n\1:\n", text)
    yield from description_segments(text)
    for match in re.finditer(r"\bExperience:\s*([^\n.;]+)",text,re.I):
        if not re.search(r"\bexperience\b",match[1],re.I):
            yield match.group(), "qualifications"


@lru_cache(maxsize=2048)
def _extract(description: str) -> tuple[Requirement, ...]:
    found = []
    for text, section in _segments(description):
        if NON_APPLICANT.search(text) or re.search(r"\b(?:tuition|reimbursement|scholarship|student loan|retirement|anniversary)\b",text,re.I):
            continue
        educational = sorted((match.start(), match.end(), level) for level, pattern in _EDUCATION for match in pattern.finditer(text))
        alternative_levels = {level for left,right in zip(educational,educational[1:])
                              if left[2] != right[2] and re.search(r"\bor\b",text[left[1]:right[0]],re.I)
                              for level in [left[2],right[2]]}
        for index, (start, end, level) in enumerate(educational):
            # Keep a preferred higher degree from modifying the preceding minimum.
            stop = educational[index+1][0] if index+1 < len(educational) else len(text)
            context = text[:stop]
            kind = _kind(context,start,end,section,"education")
            if kind is None:
                continue
            if level in alternative_levels:
                kind = "alternative"
            if kind == "uncertain" and section not in {"required", "qualifications"}:
                continue
            evidence = _excerpt(text,start,end)
            found.append(Requirement(field="education",value=level,kind=kind,evidence=evidence,source=SOURCE))
        experience = re.search(r"\bexperience\b", NON_REQUIRED_CONTEXT.sub(lambda match:" "*len(match.group()),text), re.I)
        if not experience:
            continue
        durations = [match for match in _DURATION.finditer(text) if abs(match.start()-experience.start()) < 110]
        if durations:
            for match in durations:
                if re.search(r"\b(?:less|fewer) than\s*$",text[:match.start()],re.I):
                    continue
                if re.match(r"\s*(?:of\s+age|old\b)",text[match.end():],re.I):
                    continue
                if match.end() <= experience.start() and re.search(r"\b(?:age|old|benefits?|retirement|anniversary)\b",text[match.end():experience.start()],re.I):
                    continue
                minimum = match["minimum"].casefold()
                years = float(_NUMBERS[minimum]) if minimum in _NUMBERS else float(minimum)
                if years <= 0 or re.search(r"\bup to\s*$",text[:match.start()],re.I):
                    continue
                if match["unit"].casefold().startswith("month"):
                    years /= 12
                kind = _kind(text,match.start(),match.end(),section,"experience_years")
                if len(durations) > 1 and any(re.search(r"\bor\b",text[left.end():right.start()],re.I)
                                             for left,right in zip(durations,durations[1:])):
                    kind = "alternative" if kind not in {None, "preferred"} else kind
                if kind is None or (kind == "uncertain" and section not in {"required", "qualifications"}):
                    continue
                evidence = _excerpt(text,match.start(),match.end())
                found.append(Requirement(field="experience_years",value=years,kind=kind,evidence=evidence,source=SOURCE,scope=_scope(text,match.end())))
        elif (section in {"required", "qualifications"} or _REQUIRED.search(text)) and re.search(
            r"\b(?:prior|previous|proven|relevant|demonstrated|professional|hands-on)\s+(?:\w+\s+){0,3}experience\b|\bexperience\s+(?:in|as|with)\b",text,re.I
        ):
            kind = _kind(text,experience.start(),experience.end(),section,"experience_years")
            if kind is not None:
                scope = re.sub(r"^\s*(?:in|as|with)\s+", "",text[experience.end():],flags=re.I).strip(" .:")
                evidence = _excerpt(text,experience.start(),experience.end())
                found.append(Requirement(field="experience_years",value="not_stated",kind=kind,evidence=evidence,source=SOURCE,scope=_EMAIL.sub("[contact omitted]",scope[:180]) or None))
    unique = {(r.field,str(r.value),r.kind,r.scope,r.evidence):r for r in found}
    return tuple(unique.values())


def with_qualification_evidence(job: Job) -> Job:
    authoritative = {r.field for r in job.requirements if not r.source.startswith((SOURCE,"posting_credential_hints_","operator_role_check:"))}
    requirements = list(job.requirements)
    keys = {(r.field,str(r.value),r.kind,r.evidence) for r in requirements}
    for req in _extract(job.description):
        key = (req.field,str(req.value),req.kind,req.evidence)
        if req.field not in authoritative and key not in keys:
            requirements.append(req.model_copy())
            keys.add(key)
    return with_credential_evidence(job.model_copy(update={"requirements":requirements}))


def experience_assessment(req: Requirement, profile: UserProfile, *, job_id: str | None = None) -> tuple[str, str]:
    if job_id and req.key in profile.qualification_answers.get(job_id, {}):
        held = profile.qualification_answers[job_id][req.key]
        return ("reported_match", "You report meeting this experience requirement; confirm it with the employer.") if held else (
            "gap", "You report not meeting this experience requirement. Ask about a trainee or supervised route.")
    try:
        needed = float(req.value)
    except (TypeError, ValueError):
        needed = None
    years = profile.experience.years
    if needed is not None and years is not None and years < needed:
        verb = "requires" if req.kind == "required" else "lists"
        return "gap", f"Posting {verb} {needed:g} years of relevant experience; {years:g} stated."
    scope = req.scope
    if not scope:
        duration = _DURATION.search(req.evidence)
        scope = _scope(req.evidence,duration.end()) if duration else None
    user = experience_text(profile)
    if scope:
        specialized = [
            (r"\b(?:forklift|reach truck|clamp truck)\b", ["forklift","reach truck","clamp truck"]),
            (r"\b(?:tractor[/ -]trailer|commercial driving|truck driving)\b", ["tractor/trailer","tractor trailer","commercial driving","truck driving","truck driver"]),
        ]
        for pattern, terms in specialized:
            if re.search(pattern,scope,re.I) and not any(contains(user,term) for term in terms):
                return "unknown", f"Experience in {scope} is not established by your stated experience. Confirm it with the employer."
        families = {family for family, terms in SKILL_FAMILIES.items() if any(contains(scope,term) for term in terms)}
        matches = any(any(contains(user,term) for term in SKILL_FAMILIES[family]) for family in families)
        if not families and len(scope.strip()) >= 4 and contains(user, scope):
            matches = True
        if "equipment repair" in families:
            matches = repair_experience_reported(user)
        if not matches:
            return "unknown", f"Experience in {scope} is not established by your stated experience. Confirm it with the employer."
    else:
        return "unknown", "The posting's experience scope needs confirmation; total years alone do not establish relevant experience."
    if needed is not None and years is None:
        return "unknown", f"Years of experience in {scope} are not confirmed."
    return "reported_match", f"Confirm that your reported experience covers {scope}."



def requirement_label(req: Requirement) -> str:
    if req.field == "certification":
        return str(req.value)
    if req.field == "education":
        return {"none": "No diploma requirement", "high_school": "High school diploma or GED",
                "some_college": "Some college", "associate": "Associate degree", "bachelor": "Bachelor's degree",
                "master": "Master's degree", "doctorate": "Doctoral degree"}.get(str(req.value), str(req.value))
    scope = req.scope or "relevant work"
    try:
        return f"{float(req.value):g} years of {scope} experience"
    except (ValueError, TypeError):
        return f"Experience in {scope} (duration not stated)"


def qualification_checks(job: Job, profile: UserProfile) -> list[QualificationCheck]:
    """Specific posting criteria, with explicit job-scoped user answers taking priority."""
    checks = {}
    answers = profile.qualification_answers.get(job.job_id, {})
    for req in job.requirements:
        label = requirement_label(req)
        if req.key in answers:
            status = "reported_met" if answers[req.key] else "preferred" if req.kind == "preferred" else "gap"
            detail = f"You report {'having' if answers[req.key] else 'not having'} this qualification. Confirm the employer's acceptance."
        elif req.field == "education":
            needed, actual = LEVELS.get(str(req.value)), LEVELS.get(profile.education.level)
            status = "needs_confirmation" if needed is None or actual is None else "gap" if actual < needed else "reported_met"
            detail = f"Your education: {profile.education.level.replace('_', ' ')}. Confirm the subject and accepted equivalents."
        elif req.field == "experience_years":
            result, detail = experience_assessment(req, profile)
            status = {"gap": "gap", "unknown": "needs_confirmation", "reported_match": "reported_met"}[result]
        else:
            held = credential_reported_held(str(req.value), profile)
            status = "reported_met" if held else "gap" if profile.education.no_certifications else "needs_confirmation"
            detail = "Reported held; check validity and employer acceptance." if held else "Not reported held. Ask about accepted training and whether it is needed before starting."
        if req.kind == "preferred" and status != "reported_met":
            status = "preferred"
        elif req.kind in {"alternative", "uncertain"} and req.key not in answers and status != "reported_met":
            status = "needs_confirmation"
        checks[req.key] = QualificationCheck(key=req.key, field=req.field, label=label,
            requirement_kind=req.kind, status=status, detail=detail + " Posting evidence: " + req.evidence)
    return list(checks.values())

"""Relative daily actions grounded in the selected job and reported qualifications.

Deterministic preparation advice, not generated job duties or promised appointments.
Credential instructions and links come from the existing evidence-backed pathways.
"""

from __future__ import annotations

import hashlib
import json
import re

from .models import DailyPlanAction, Job, PlanLink, ThirtyDayPlan, UserProfile
from .qualifications import SKILL_FAMILIES, contains, qualification_checks

EDUCATION_LABELS = {
    "unknown": "education not provided", "none": "no diploma yet",
    "high_school": "high school diploma or GED", "some_college": "some college",
    "associate": "associate degree", "bachelor": "bachelor's degree",
    "master": "master's degree", "doctorate": "doctoral degree",
}
# These are preparation examples for role families, not claims about a posting's duties.
ROLE_PREPARATION = {
    "commercial driving": ("route planning and safe delivery", "Plan a sample route on paper. Explain how you would report a delay.", "Ask about routes, vehicle class, endorsements, and accepted driving experience."),
    "equipment repair": ("fault finding and repair records", "Describe a sample equipment fault and how you would report it. Leave repairs to qualified, supervised staff.", "Ask about the equipment, supervision, tools, and repair experience needed."),
    "warehouse": ("inventory checks and safe handling", "Use a mock inventory list to find a count or order error. Use powered equipment only with accepted training and supervision.", "Ask about equipment training, order checks, and shifts."),
    "food service": ("order accuracy and kitchen teamwork", "Read a sample order and check it for errors. Ask about food safety training before starting unfamiliar tasks.", "Ask about the station, shifts, and any food safety certificate."),
    "customer service": ("listening and customer communication", "Practice helping a customer with an unclear request. Explain when you would ask a supervisor for help.", "Ask about customer needs, transaction training, and daily expectations."),
    "construction": ("following instructions and site safety", "Read a sample task checklist and prepare questions for a supervisor. Do not practice with unfamiliar tools.", "Ask about site training, supervision, and tools supplied."),
    "cleaning": ("cleaning routines and attention to detail", "Write a room-cleaning checklist. Explain how you would report a hazard. Follow product instructions; never mix chemicals.", "Ask about products, protective equipment, assigned areas, and shifts."),
    "driving": ("route planning and accurate deliveries", "Plan a mock delivery route. Explain how you would report a delay. Confirm vehicle and license requirements before driving for work.", "Ask about the vehicle, license, routes, and travel costs."),
    "administration": ("accurate records and scheduling", "Check a mock appointment list for errors. Use fictional information while practicing.", "Ask about software, daily tasks, and privacy training."),
    "landscaping": ("outdoor task planning and safe teamwork", "Read a sample groundskeeping checklist. Ask about training before using unfamiliar tools or equipment.", "Ask about the work areas, tools, supervision, and weather arrangements."),
    "caregiving": ("clear communication and reliable daily routines", "Practice giving a clear handover for a fictional daily routine. Keep real client details private and ask which duties need training.", "Ask about duties, supervision, required credentials, and training."),
    "general": ("the skills named in the posting", "Pick one task from the posting. Prepare a safe example or ask how it is taught.", "Ask which tasks need experience and which are taught after hiring."),
}

def _role_family(target: Job) -> str:
    title = target.title.casefold()
    if re.search(r"\b(?:cdl|commercial driv|truck driv|tractor[ /-]trailer)", title):
        return "commercial driving"
    # A forklift mechanic is a repair role, not evidence of warehouse experience.
    for family in ["equipment repair", "warehouse", "food service", "customer service",
                   "construction", "cleaning", "driving", "administration", "landscaping", "caregiving"]:
        if any(contains(title, term) for term in SKILL_FAMILIES[family]):
            return family
    return "general"


def _names(items, limit=2):
    labels = [item.label for item in items]
    brief = [" ".join(label.split()[:14]) + ("…" if len(label.split()) > 14 else "") for label in labels[:limit]]
    return "; ".join(brief) + (" and the other listed requirements" if len(labels) > limit else "")


def personalized_daily_actions(profile: UserProfile, target: Job, plan: ThirtyDayPlan) -> list[DailyPlanAction]:
    focus, practice, interview = ROLE_PREPARATION[_role_family(target)]
    checks = qualification_checks(target, profile)
    mandatory = [check for check in checks if check.requirement_kind == "required"]
    unresolved = [check for check in mandatory if check.status != "reported_met"]
    education = [check for check in checks if check.field == "education"]
    experience = [check for check in checks if check.field == "experience_years"]
    missing = [path for path in plan.credential_paths if path.user_status == "not_confirmed"]
    held = [path.credential for path in plan.credential_paths if path.user_status == "reported_held"]
    preparation = [path for path in missing if path.requirement_kind != "preferred"] or missing
    names = "; ".join(path.credential for path in preparation[:2])
    if len(preparation) > 2:
        names += " and your other listed credentials"
    interim = next((job for job in plan.interim_jobs if job.is_selected), None)
    posting = [link for step in plan.steps for link in step.links if link.role == "job_posting"]
    title = target.title

    edu_required = [check for check in education if check.requirement_kind == "required"]
    edu_gap = [check for check in edu_required if check.status != "reported_met"]
    if edu_gap:
        education_action = f"Check the requirement: {_names(edu_gap)}. Ask about accepted equivalents or education support. A diploma or degree may take longer than 30 days."
    elif edu_required:
        education_action = f"You report meeting: {_names(edu_required)}. Gather your records and confirm the subject and accepted equivalents."
    elif education:
        education_action = f"Ask how the employer uses this education criterion: {_names(education)}. Confirm whether it is preferred or an accepted alternative."
    else:
        education_action = "Ask whether this job needs a diploma or degree. Check which records or equivalents the employer accepts."

    exp_required = [check for check in experience if check.requirement_kind == "required"]
    exp_gap = [check for check in exp_required if check.status != "reported_met"]
    if exp_gap:
        experience_action = f"Check the experience needed: {_names(exp_gap)}. Ask about a trainee or supervised-work route. A certificate does not replace required work experience."
    elif exp_required:
        experience_action = f"You report meeting: {_names(exp_required)}. Prepare an honest example and dates. Ask the employer to confirm the type and length of experience."
    elif experience:
        experience_action = f"Confirm the preferred or alternative experience: {_names(experience)}. Ask whether your work history or a trainee route is accepted."
    elif profile.experience.years == 0:
        experience_action = "You reported no work experience yet. Ask about entry-level training or a supervised starting role. Use honest examples from learning or daily responsibilities."
    else:
        experience_action = "Ask about the type and length of experience needed. Compare your actual duties and dates; ask about a trainee route if needed."

    if missing:
        credential_action = f"Check the route for {names}. Ask if it is needed before starting, and whether the employer provides training."
        funding = f"Compare accepted training for {names}. Ask about full cost, start dates, and funding before booking."
        training = f"If the {names} route is confirmed and affordable, begin its prerequisites. Follow the provider’s instructions."
        progress = "If training is arranged, attend the required supervised sessions. Ask what remains before assessment or independent work."
        milestone = "Ask the provider which requirements are complete. Book testing only when eligible. Continue beyond 30 days if needed."
        if all(path.requirement_kind == "preferred" for path in missing):
            credential_action = f"{names} is preferred. Ask whether you can apply without it. Verify any credentials you already hold."
            funding = f"If you choose optional training for {names}, ask about accepted providers, full costs, and funding before booking."
            training = f"If you choose optional training for {names}, confirm the route before starting. Otherwise practice a skill from the posting."
            progress = "If taking optional training, check progress with the provider. Otherwise prepare an honest work example for an interview."
            milestone = "Review any optional training or application progress. A preferred certificate alone need not delay applying."
    elif held:
        credential_action = f"Verify your existing {'; '.join(held[:2])}. Check validity and employer acceptance before repeating training."
        funding = "Reuse accepted credential records. Ask a job center about application help or any remaining preparation costs."
        training, progress, milestone = practice, interview, "Gather proof of your earned credentials. Ask the employer whether any extra training or evaluation is needed."
    else:
        credential_action = "Ask whether this role needs a license, certificate, or workplace evaluation. Confirm the exact requirement before choosing a course."
        funding = "Ask a local job center about application help and any required training costs. Confirm eligibility before paying."
        training, progress, milestone = practice, interview, "Prepare a real example of a skill in the posting. Ask whether the employer wants a demonstration or records."

    application = (f"For {title}, confirm missing requirements or an accepted trainee route before applying. List pending training as in progress."
                   if unresolved else f"Confirm the vacancy and full requirements for {title}, then apply when ready. A preferred certificate alone need not delay applying.")
    schedule = (f"If offered {interim.title}, compare its shifts with your target-job training and travel. Ask about conflicts before accepting."
                if interim else "Compare the target job’s shifts with your availability, travel, and any confirmed training. Ask about conflicts before accepting a schedule.")
    starting = f"You reported {EDUCATION_LABELS[profile.education.level]}. "
    starting += f"You also reported {profile.experience.years:g} years of work experience." if profile.experience.years is not None else "Your work-experience duration is not provided."
    rows = [
        ("Check the opening", f"Open the posting for {title} at {target.company}. Ask if the job is still open and how to apply."),
        ("Check your starting point", starting + " Review the qualification checkboxes. Check only items you already have."),
        ("Check certificates and licenses", credential_action),
        ("Update your résumé", f"Tailor your résumé to {title}. Highlight real examples of {focus} where relevant. Do not claim skills you have not used."),
        ("Check required education", education_action),
        ("Check training costs", funding),
        ("Review week one", "Review the employer’s answers. Choose your next step: apply, verify an existing qualification, or follow an accepted preparation route."),
        ("Check interim work" if interim else "Write your introduction", f"Check the opening and requirements for {interim.title}. Apply if suitable while preparing for your target role." if interim else f"Write a short introduction for {title}. Mention your relevant skills and why the role interests you."),
        ("Check required experience", experience_action),
        ("Take the application step", application),
        ("Plan your commute", f"Confirm the actual worksite and shifts for {title}. Check travel options and costs for those times."),
        ("Start accepted training" if missing else "Practice a job skill", training),
        ("Check your schedule", schedule),
        ("Review week two", "Record applications, employer replies, and confirmed training. Follow up on any unanswered requirement before paying or enrolling."),
        ("Follow up", f"Follow {target.company}’s contact instructions. Ask about your application or preparation questions after its stated response window."),
        ("Practice for this role", practice),
        ("Check training progress" if missing else "Prepare job questions", progress),
        ("Practice an interview", interview + " Use real examples and be honest about training you still need."),
        ("Check your records", "Check your résumé, dates, and earned qualifications for accuracy. Keep unfinished courses marked in progress."),
        ("Confirm any meeting", "If an interview or provider meeting is arranged, confirm the time, place, and documents. If not, ask about the next step."),
        ("Review week three", "List completed steps and items waiting on someone else. Choose one practical action for this week."),
        ("Recheck the opening", f"Check that {title} is still available. If it has closed, find another opening in that role and check its requirements."),
        ("Review qualification progress", "Revisit this job’s qualification checklist. Update only items you actually meet. Ask about accepted alternatives for anything still missing."),
        ("Check the next milestone", milestone),
        ("Update your application", "Add any newly earned qualification or real experience. If a mandatory gap remains, ask about the next preparation step."),
        ("Ask what happens next", f"Ask {target.company} about the next application, interview, or trainee step. Respect its follow-up timeline."),
        ("Check any offer", "If an offer arrives, confirm written pay, shifts, worksite, and remaining requirements. Agree to a start only when those details are clear."),
        ("Review your progress", "Compare your progress with day two. Note completed steps, remaining costs, and qualifications still to earn or verify."),
        ("Set your next step", "Confirm the next interview, supervised session, or assessment with the employer or provider. Write down later dates if the route takes longer."),
        ("Continue toward your goal", f"Review progress toward {title}. Continue your application or accepted training route. Hiring, certificates, and funding are not guaranteed within 30 days."),
    ]
    actions = []
    for day, (heading, action) in enumerate(rows, 1):
        links: list[PlanLink] = list(posting)
        if day in {3, 6, 12, 17, 24}:
            links.extend(link for path in plan.credential_paths for link in path.links)
        if day == 6:
            links.extend(link for step in plan.steps for link in step.links if link.role == "funding_support")
        if interim and day in {8, 13} and interim.source_url:
            links.append(PlanLink(label="Selected interim job posting", url=interim.source_url, role="job_posting"))
        links = list({link.url: link for link in links}.values())
        phase = "Get ready" if day <= 7 else "Take action" if day <= 14 else "Build momentum" if day <= 21 else "Work toward your goal"
        identity = json.dumps([target.job_id, day, heading, action, [link.model_dump() for link in links]], sort_keys=True)
        action_id = f"day-{day}-{hashlib.sha256(identity.encode()).hexdigest()[:12]}"
        actions.append(DailyPlanAction(action_id=action_id, day=day, title=heading, action=action, phase=phase, links=links))
    return actions

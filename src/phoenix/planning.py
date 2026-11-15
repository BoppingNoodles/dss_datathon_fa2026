"""Selected-job preparation and optional interim work, without promising placement."""

from __future__ import annotations

from .credentials import credential_key, credential_reported_held, credential_summary
from .daily_plan import personalized_daily_actions
from .models import (CredentialPath, InterimJobOption, Job, JobCard, PlanLink, PlanStep,
                     ThirtyDayPlan, UserProfile)
from .qualifications import experience_assessment

DMV = PlanLink(label="California DMV commercial licensing steps", role="official_requirements",
              url="https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/commercial-driver-licenses-cdl/")
TPR = PlanLink(label="FMCSA registered training provider finder", role="provider_finder",
              url="https://tpr.fmcsa.dot.gov/")
FORKLIFT = PlanLink(label="California DIR forklift training and evaluation requirements", role="official_requirements",
                   url="https://www.dir.ca.gov/title8/3668.html")
JOB_CENTER = PlanLink(label="Find an American Job Center; ask about training funding and employment support",
                     role="funding_support",
                     url="https://cloudfront.careeronestop.org/LocalHelp/AmericanJobCenters/american-job-centers.aspx")


def interim_options(cards: list[JobCard], target_id: str, profile: UserProfile, *, limit: int = 5) -> list[InterimJobOption]:
    options = []
    for card in cards:
        if (card.job_id == target_id or card.qualification_gaps or card.availability == "expired_snapshot"
                or card.matches_reported_role is False):
            continue
        if any(r.field == "certification" and r.kind in {"required", "alternative", "uncertain"}
               and not credential_reported_held(str(r.value), profile, job_id=card.job_id, requirement=r) for r in card.requirements):
            continue
        if any(r.field == "experience_years" and r.kind in {"required", "alternative", "uncertain"}
               and experience_assessment(r, profile, job_id=card.job_id)[0] != "reported_match" for r in card.requirements):
            continue
        options.append(InterimJobOption(job_id=card.job_id, title=card.title, company=card.company,
            pay=card.pay, credential_summary=credential_summary(card.requirements, profile, job_id=card.job_id), source_url=card.source_url,
            confirmation_needed=["Confirm all qualifications, current vacancy, and any required training with the employer.",
                                 "Confirm offered shifts can fit the target credential's training schedule.",
                                 "A job application is not a confirmed start date or guaranteed income."]))
        if len(options) >= limit:
            break
    return options


def build_thirty_day_plan(profile: UserProfile, target: Job, cards: list[JobCard], *,
                          selected_interim_job_id: str | None = None) -> ThirtyDayPlan:
    posting = [PlanLink(label="Selected job posting", url=target.source_url, role="job_posting")] if target.source_url else []
    steps = [PlanStep(step_id="confirm-target", day_start=1, day_end=3, track="job_confirmation",
        title="Confirm the target job and your starting point",
        action="Ask whether the vacancy is still open, which credentials are mandatory before starting, which are preferred, and whether paid training or a trainee route exists. Confirm credentials you already hold before paying for a course.",
        links=posting)]
    paths = []
    credentials = [r for r in target.requirements if r.field == "certification"]
    seen = set()
    for req in credentials:
        label = str(req.value)
        key = credential_key(label)
        if key in seen:
            continue
        seen.add(key)
        held = credential_reported_held(label, profile, job_id=target.job_id, requirement=req)
        links = [DMV, TPR, JOB_CENTER] if key == "class a cdl" else [FORKLIFT, JOB_CENTER] if key == "forklift" else [JOB_CENTER]
        paths.append(CredentialPath(credential=label, requirement_kind=req.kind,
            user_status="reported_held" if held else "not_confirmed", job_evidence=req.evidence,
            evidence_source=req.source, links=links))
        prefix = f"credential-{len(paths)}"
        if held:
            steps.append(PlanStep(step_id=prefix+"-verify", day_start=1, day_end=7, track="credential",
                title=f"Verify your existing {label}", action="Check validity, any endorsements/restrictions, and employer acceptance. Reuse valid documented training where accepted; do not automatically enroll again.",
                depends_on=["confirm-target"], links=posting+links))
            continue
        optional = {
            "required": "",
            "preferred": "This credential is preferred; first ask whether you can apply without it. ",
            "alternative": "The posting offers alternatives; ask which route the employer accepts before choosing training. ",
            "uncertain": "Whether this credential is required is unclear; ask the employer before choosing training. ",
        }[req.kind]
        if key == "class a cdl":
            titles = ["Check the CDL pathway and endorsements", "Compare registered training and funding", "Start the application and enrollment steps", "Work through prerequisites and training", "Review progress and book the next eligible milestone"]
            actions = [
                "Use DMV's current checklist to check your starting license, documents, medical/application steps, and the exact class/endorsements the employer needs. Do not assume eligibility or a 30-day completion date.",
                "Use the FMCSA provider finder around your location. Ask providers about approval, theory/practical components, full costs, start dates, and timetables. Ask an American Job Center about possible funding before paying; support is not guaranteed.",
                "After eligibility, course scope, and payment arrangements are confirmed, begin the applicable DMV and provider steps. Save confirmations and schedule training around any interim job offer.",
                "Study and attend required supervised training according to DMV/provider guidance. Track the learner-permit and other prerequisites; do not undertake commercial driving duties without required authorization.",
                "Ask the provider/DMV which requirements are complete and which remain. Schedule testing only when eligible and appointments are available. If completion takes longer, carry the pathway forward and keep interim work options open.",
            ]
        elif key == "forklift":
            titles = ["Confirm the employer's equipment-specific training route", "Arrange accepted hands-on training and cost support", "Begin formal instruction and practical training", "Arrange the workplace evaluation", "Document training and review readiness"]
            actions = [
                "Ask the employer which truck/attachment and workplace training is needed and whether they provide it. California's requirements include instruction, hands-on practice, and workplace evaluation; an online-only card is not enough.",
                "Confirm the trainer and employer accept the practical training/evaluation arrangement. Ask about employer-paid training or job-center support and the full cost before enrolling.",
                "Once an accepted arrangement is confirmed, attend instruction and practical training under qualified supervision. Coordinate training sessions with any interim work schedule.",
                "Coordinate the required workplace evaluation with the employer/trainer. Course attendance alone does not authorize independent equipment operation.",
                "Ask the employer/trainer to document completed training and evaluation. Update your application with only completed, accepted qualifications; extend the plan if sessions or evaluation are still pending.",
            ]
        else:
            titles = [f"Identify the exact {label} pathway", "Find an accepted provider and cost support", "Start confirmed prerequisites", "Attend training or prepare for the assessment", "Review completion evidence and next steps"]
            actions = [
                "Ask the employer for the issuing body, exact credential name, prerequisites, and an official requirements link. Confirm the pathway with that body before enrolling; a similar-sounding course may not be accepted.",
                "Ask the issuing body/employer about accepted providers, schedules, exams, and all fees. Use a local American Job Center to ask about available funding; no provider, funding, or completion time is assumed.",
                "After checking eligibility, provider acceptance, and costs, begin the required application/documents or enrollment steps and save confirmations.",
                "Follow the approved provider's schedule. Coordinate interim work and travel so training is feasible. Do not represent a booked course as a completed credential.",
                "Confirm completed milestones and remaining requirements with the issuing body/provider. Update your resume only with earned qualifications and continue beyond 30 days when needed.",
            ]
        windows = [(1, 3), (4, 7), (8, 14), (15, 21), (22, 30)]
        previous = "confirm-target"
        for i, ((start, end), title, action) in enumerate(zip(windows, titles, actions), 1):
            step_id = f"{prefix}-{i}"
            steps.append(PlanStep(step_id=step_id, day_start=start, day_end=end, title=title,
                action=(optional+action if i == 1 else
                        "Only if the employer confirms this pathway is needed or you choose it as optional preparation: "+action
                        if req.kind != "required" else action),
                track="credential", depends_on=[previous], links=posting+links))
            previous = step_id
    if not credentials:
        steps.append(PlanStep(step_id="check-unparsed-requirements", day_start=1, day_end=7, track="credential",
            title="Check requirements before choosing a course", action="No credential pathway was identified from the supplied evidence. Read the full posting with the employer; do not assume no certification is required or buy a generic course.",
            depends_on=["confirm-target"], links=posting))
    if any(r.field == "experience_years" and r.kind in {"required", "alternative", "uncertain"} for r in target.requirements):
        steps.append(PlanStep(step_id="experience-route", day_start=1, day_end=7, track="experience",
            title="Check role-specific experience separately", action="Confirm that your experience is in the required trade. If it is not, ask about a trainee, apprenticeship, or supervised-work route; earning a certificate does not replace years of required experience.",
            depends_on=["confirm-target"], links=posting))
    if not any(p.requirement_kind in {"required", "uncertain", "alternative"} and p.user_status == "not_confirmed" for p in paths):
        steps.append(PlanStep(step_id="apply-target-when-confirmed", day_start=1, day_end=7, track="application",
            title="Apply to the selected job once requirements are confirmed", action="Confirm the full requirements and vacancy, then apply when ready. A preferred credential alone should not force you to wait for a course before applying.",
            depends_on=["confirm-target"], links=posting))
    options = interim_options(cards, target.job_id, profile)
    if selected_interim_job_id is not None and selected_interim_job_id not in {o.job_id for o in options}:
        raise ValueError("Selected interim job must be one of the displayed interim-work options")
    options = [o.model_copy(update={"is_selected":o.job_id == selected_interim_job_id}) for o in options]
    steps.extend([
        PlanStep(step_id="interim-apply", day_start=1, day_end=7, track="interim_work",
            title="Apply for interim work while preparing", action="Review the displayed interim options. Confirm required credentials, other qualifications, current openings, shifts, and pay before applying. If there are no suitable options, ask a local job center for a search with fewer entry barriers.", links=[JOB_CENTER]),
        PlanStep(step_id="schedule-work-training", day_start=4, day_end=14, track="interim_work",
            title="Fit an interim offer around training", action="Compare actual offered shifts with training sessions, travel, and assessment dates. Ask about part-time, evening, or employer-supported training options. Neither schedule compatibility nor a job start is assumed.", depends_on=["interim-apply"]),
        PlanStep(step_id="review-transition", day_start=22, day_end=30, track="application",
            title="Review the target-job transition", action="Check which credentials and experience requirements are actually met and whether the target opening is still available. Apply or ask about the next step when appropriate; continue interim work and the training pathway if more time is needed.", depends_on=["confirm-target"], links=posting),
    ])
    steps.sort(key=lambda s:(s.day_start, s.day_end, s.step_id))
    plan = ThirtyDayPlan(target_job_id=target.job_id, target_job_title=target.title,
        selected_interim_job_id=selected_interim_job_id, credential_paths=paths, interim_jobs=options, steps=steps,
        notes=["This is a 30-day action window, not a promise of certification, placement, or funding.",
               "Days are planning windows; actual prerequisites, course dates, and work shifts may extend the timeline.",
               "No certification identified is not confirmation that none is required; verify before starting work.",
               "Target pay is a future scenario. Interim pay is also only a scenario until employment and hours are confirmed.",
               "Official pathway/finder pages reviewed November 14, 2026; no individual course price, seat, or start date has been verified."])
    return plan.model_copy(update={"daily_actions": personalized_daily_actions(profile, target, plan)})

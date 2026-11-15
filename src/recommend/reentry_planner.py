"""Transparent barrier -> task rules. No model, network, or inferred legal conditions.

Only reported barriers affect urgency. Hard edges describe a specific action's
prerequisite, not a universal gate to jobs, housing research, or other support.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from src.common import ROOT
from src.recommend.reentry_models import Referral, ReentryDay, ReentryPlan, ReentryTask
from src.recommend.services import rank_services, resolve_location
from src.recommend.reentry_resources import resource_types, BARRIER_TYPES

PRIORITY = {"immediate": 0, "high": 1, "medium": 2, "later": 3}
STAGE = {"immediate_stability": 0, "removing_barriers": 1, "building_independence": 2}
REGISTRY = ROOT / "data/resources/reentry_services.json"
# Narrow service families: a generic bank, shop, or clinic is not ID/phone help.
RESOURCE_NEEDS = {
    "housing": ("housing", {"housing_assistance"}),
    "identification": ("community_support", {"government_services", "social_services"}),
    "communication": ("community_support", {"public_library", "social_services"}),
    "transportation": ("transportation", {"transit", "social_services"}),
    "employment": ("work", {"employment_services", "public_library"}),
    "qualifications": ("work", {"employment_services"}),
    "documents": ("work", {"employment_services", "public_library"}),
    "food": ("food", {"food_assistance"}),
    "health_care": ("health_care", {"community_health", "behavioral_health"}),
    "community_support": ("community_support", {"social_services"}),
}


def verified_referrals(city: str | None, barrier: str, today: date, *, path: Path = REGISTRY) -> list[Referral]:
    """Official-page scope check only; never claims individual eligibility.

    A small checked-in supplement to the existing place_id verification CSV.
    No fuzzy name joins, fabricated Places IDs, inferred service areas or ratings.
    Invalid/incomplete/future-dated entries are withheld.
    """
    if not city or not path.is_file():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for entry in entries:
        if (city.casefold() not in {c.casefold() for c in entry.get("cities", [])}
                or barrier not in entry.get("barriers", [])):
            continue
        evidence = {k: v for k, v in entry.items() if k not in {"cities", "barriers"}}
        evidence["service_area_cities"] = entry.get("cities", [])
        evidence["category_evidence"] = entry.get("scope")
        try:
            referral = Referral.model_validate(evidence)
        except ValidationError:
            continue
        if (referral.verification in {"verified_reentry_scope", "verified_general_service"} and referral.source_url
                and referral.source_url.startswith("https://") and referral.checked_on
                and referral.checked_on <= today and referral.scope):
            if set(referral.resource_types) & set(BARRIER_TYPES.get(barrier, [])):
                result.append(referral)
    return result


def candidate_referrals(barrier: str, request: dict, candidates, refs, *, source: str, today: date) -> list[Referral]:
    if candidates.empty:
        city = request["location"] if not request["location"].strip().isdigit() else None
    else:
        city = resolve_location(request["location"], refs, candidates).city
    # Synthetic runs must never mix real providers with fictional Places.
    result = verified_referrals(city, barrier, today) if source == "real" else []
    if candidates.empty or barrier not in RESOURCE_NEEDS:
        return result[:3]
    need, families = RESOURCE_NEEDS[barrier]
    section = rank_services(candidates, refs, need=need, location=request["location"],
                            age=request.get("age"), sort=request.get("service_sort", "highly_rated"))
    ids = [c["place_id"] for g in section["groups"] for c in g["items"]]
    source_rows = {str(r["place_id"]): r for r in candidates.loc[candidates["place_id"].isin(ids)].to_dict("records")}
    for group in section["groups"]:
        if group["key"] == "temporarily_closed":
            continue
        for card in group["items"]:
            if (card["family"] not in families
                    or card["eligibility"]["age_status"] == "outside_published_age_criterion"
                    or card["availability"]["permanently_closed"] is True):
                continue
            verification = card["verification"]
            raw = source_rows.get(card["place_id"], {})
            category = " ".join(str(raw.get(k, "")) for k in ("category", "categories") if raw.get(k) is not None)
            types = resource_types(category)
            if not set(types) & set(BARRIER_TYPES.get(barrier, [])):
                continue
            if barrier == "communication" and card["family"] != "public_library" and not any(term in str(raw.get("relevant_service", "")).casefold() for term in ("phone", "internet", "communication")):
                continue
            # General verification is deliberately not reentry verification.
            verified = (verification["status"].startswith("verified_")
                        and verification.get("official_url") and verification.get("checked_on"))
            result.append(Referral(
                resource_id=card["place_id"], name=card["name"],
                url=verification.get("official_url") or card["contact"]["website"] or card["contact"]["maps_url"],
                verification="verified_general_service" if verified else "unverified",
                provider_category=card["family_label"],
                scope=f"Source category: {category}. Specific assistance, cost, and reentry eligibility need confirmation.",
                source_url=verification.get("official_url"), checked_on=verification.get("checked_on"),
                resource_types=types, category_evidence=f"Google Places category: {category} (service unconfirmed).",
                city=card["contact"]["city"], distance_miles=card["distance"]["miles"],
                phone=card["contact"]["phone"], address=card["contact"]["address"],
            ))
    # Do not show a manually verified organization twice if also in the export.
    unique = {}
    for referral in result:
        unique.setdefault((referral.url or referral.resource_id).rstrip("/"), referral)
    # Geography and actual transport subtype take precedence over a highly
    # rated stop in a different city. No route or subsidy is inferred.
    return sorted(unique.values(), key=lambda r: (
        0 if r.verification == "verified_reentry_scope" or r.resource_id.startswith("manual:") and r.verification == "verified_general_service" else 1,
        0 if city and r.city and city.casefold() == r.city.casefold() else 1,
        1 if barrier == "transportation" and "bus stop" in (r.category_evidence or "").casefold() and "station" not in (r.category_evidence or "").casefold() else 0,
        r.distance_miles if r.distance_miles is not None else float("inf"), r.resource_id))[:3]


def ordered_tasks(tasks: list[ReentryTask]) -> list[ReentryTask]:
    """Stable urgency/deadline topological order; fail on invalid rule graphs."""
    by_id = {t.task_id: t for t in tasks}
    if len(by_id) != len(tasks) or any(p not in by_id for t in tasks for p in t.prerequisites):
        raise ValueError("Duplicate task ID or missing prerequisite")
    ordered = []
    seen = set()
    while len(seen) < len(tasks):
        eligible = [t for t in tasks if t.task_id not in seen and set(t.prerequisites) <= seen]
        if not eligible:
            raise ValueError("Reentry task dependency cycle")
        task = min(eligible, key=lambda t: (PRIORITY[t.priority], t.deadline or date.max, STAGE[t.stage], t.task_id))
        ordered.append(task)
        seen.add(task.task_id)
    return ordered


def build_reentry_plan(request: dict, jobs: dict, housing: dict, selection: dict, *,
                       source: str, today: date, referral_lookup=None) -> ReentryPlan | None:
    situation = request.get("reentry")
    if situation is None:
        return None
    tasks: list[ReentryTask] = []
    priority_need = situation.get("priority_need") or request["priority_need"]

    def add(key, title, action, barrier, priority, why, *, prerequisites=(), confirmations=(), deadline=None, links=()):
        independence = barrier in {"employment", "qualifications", "documents", "planning"} or key == "housing-long-term"
        stage = "building_independence" if independence else "immediate_stability" if barrier in {"housing", "food", "health_care"} else "removing_barriers"
        resource_tab = "housing" if key == "housing-long-term" else "jobs" if barrier in {"employment", "qualifications", "documents"} else "services" if barrier in RESOURCE_NEEDS else None
        if key == "work-routine":
            resource_tab = None  # The person's current employer is not a dataset job.
        resource_need = RESOURCE_NEEDS[barrier][0] if resource_tab == "services" else None
        tasks.append(ReentryTask(task_id=f"reentry:{key}", title=title, action=action, barrier=barrier,
            priority=priority, stage=stage, resource_tab=resource_tab, resource_need=resource_need,
            rationale=why, prerequisites=list(prerequisites),
            confirmations=list(confirmations), deadline=deadline, links=list(links)))

    release_date = situation.get("release_date")
    if isinstance(release_date, str):
        release_date = date.fromisoformat(release_date)
    preparing = situation.get("release_status") == "preparing_for_release"
    if preparing and release_date and release_date < today:
        add("release-timing", "Check your release timing", "Update your release date or release status when you know it.",
            "release_timing", "high", "Your reported date has passed; the plan cannot assume you have been released.")

    housing_answer = situation.get("has_immediate_housing")
    if housing_answer == "no":
        tonight = situation.get("release_status") == "already_released"
        urgent = tonight or (preparing and release_date is not None and release_date <= today)
        add("housing-now", "Find a safe place for tonight" if tonight else "Plan your first safe place to stay",
            "Ask a housing resource or trusted support person about a safe place to stay. Confirm intake before traveling.",
            "housing", "immediate" if urgent else "high", "You reported no immediate place to stay.",
            deadline=today if tonight else release_date if preparing and release_date and release_date >= today else None,
            confirmations=("Confirm space, intake time, eligibility, cost, and what to bring. No bed is reserved.",))
    elif housing_answer != "yes":
        add("confirm-housing", "Check your first place to stay", "Confirm where you can stay and when it will be available.",
            "housing", "high", "Your immediate housing is unknown; this does not mean you are homeless.",
            confirmations=("If you need somewhere tonight, move housing help to the front of your plan.",))

    if situation.get("has_required_appointment") == "yes":
        add("appointment", "Confirm your appointment details", "Check the time, location, contact person, and what to bring. Keep details private.",
            "appointment", "high", "You reported a required appointment; its date and rules are unknown.",
            confirmations=("Use your own notice or contact person. Phoenix does not infer legal requirements.",))
    elif situation.get("has_required_appointment") == "unsure":
        add("confirm-appointment", "Check dates you need to plan around", "Review your own notices or calendar. Confirm any appointment with your contact person if needed.",
            "appointment", "medium", "You are unsure about appointments; the plan does not assume one is required.")

    for field, key, title, action, confirm_title, confirm_action, priority in [
        ("has_id", "identification", "Find ID assistance", "Ask an ID assistance resource what documents, fees, and steps apply to you.",
         "Check your ID status", "Check whether your ID is available and current. Ask about replacements if needed.", "high"),
        ("has_phone_access", "communication", "Find a way to stay in touch", "Ask about phone or internet access. Consider a trusted contact or library while you arrange access.",
         "Check how you can stay in touch", "Confirm a reliable way to receive employer and provider messages.", "high"),
        ("has_transportation", "transportation", "Find transportation options", "Check transit or ride options, routes, and costs for places you need to reach.",
         "Check your travel options", "Confirm how you can reach work and any appointments you report.", "high"),
    ]:
        answer = situation.get(field)
        if answer == "no":
            add(key, title, action, key, priority, f"You reported no {'ID' if key == 'identification' else key} access.",
                confirmations=("Confirm this resource provides the specific help you need before visiting or paying.",))
        elif answer != "yes":
            add(f"confirm-{key}", confirm_title, confirm_action, key, "medium",
                "This answer is unknown; the plan asks you to check rather than assuming a barrier.")

    if situation.get("has_required_appointment") == "yes" and situation.get("has_transportation") != "yes":
        add("appointment-trip", "Plan travel for your appointment", "Use the confirmed appointment time and place to check your route and travel cost.",
            "transportation", "high", "A useful route needs the appointment details first.",
            prerequisites=("reentry:appointment",), confirmations=("Allow for actual travel time; map distance is not a transit schedule.",))

    all_jobs = [c for group in jobs.get("groups", []) + jobs.get("other_groups", []) for c in group["items"]]
    selected = next((c for c in all_jobs if c["job_id"] == request.get("selected_job_id")), None)
    job_key = selected["job_id"] if selected else "browse"
    work_priority = "high" if priority_need == "work" else "medium"
    links = [{"label": "Check job posting", "url": selected["url"]}] if selected and selected.get("url") else []
    if selected:
        add(f"job-review:{job_key}", "Check your chosen job", f"Review {selected['title']}. Confirm the opening and each listed requirement with the employer.",
            "qualifications", work_priority, "Your chosen role sets the preparation goal.", links=links,
            confirmations=("A match does not confirm hiring eligibility or current availability.",))
        gaps = [c for c in selected.get("qualification_checks", []) if c["status"] != "reported_met" and c["requirement_kind"] == "required"]
        for check in gaps:
            add(f"qualification:{selected['job_id']}:{check['key']}", f"Check {check['label']}",
                "Ask the employer what is required before starting, what can be learned after hire, and which proof they accept.",
                "qualifications", work_priority, check["detail"], links=links,
                confirmations=("Confirm costs and accepted training before enrolling. Completion in 30 days is not guaranteed.",))
        # Existing model flags can lack an exact credential/span. Ask a specific
        # confirmation question; never invent a diploma, years, or license.
        labels = {"education_required": ("education", "education"),
                  "experience_required": ("experience_years", "experience"),
                  "certification_required": ("certification", "certificate or license")}
        for label, (field, name) in labels.items():
            prediction = next((r for r in selected.get("requirements", [])
                if r["label"] == label and r.get("source") == "model_prediction" and r["status"] in {"required", "unknown"}), None)
            if prediction and not any(c["field"] == field and c["requirement_kind"] == "required" for c in selected.get("qualification_checks", [])):
                add(f"model-check:{job_key}:{label}", f"Confirm the {name} requirement",
                    "Ask the employer what the posting requires and which proof they accept. Check before choosing training.",
                    "qualifications", work_priority, "The posting may mention a qualification; confirm the exact requirement with the employer.",
                    confirmations=("A model prediction is not a verified requirement or an eligibility decision.",), links=links)
    goal = situation.get("employment_goal")
    wants_work = selected is not None or goal in {"find_work", "prepare_for_work"} or (goal is None and priority_need == "work")
    if not selected and wants_work:
        add(f"job-review:{job_key}", "Review jobs that fit your skills", "Open Jobs, compare the listed qualifications, and choose a role to work toward.",
            "employment", work_priority, "Your experience and education guide the existing job matcher.",
            links=(), confirmations=("Confirm the vacancy and requirements. No employer acceptance is assumed.",))
    if wants_work:
        add("work-documents", "Prepare your work information", "List your skills, work history, and references. Ask employers which documents they need and when.",
            "documents", work_priority, "Preparation can continue while you arrange ID or other support.")
        if goal == "prepare_for_work":
            add(f"job-preparation:{job_key}", "Choose your preparation route", "Compare your skills with the role. Ask about accepted training, costs, and whether learning can happen after hire.",
                "qualifications", work_priority, "You chose training or qualification preparation as your work goal.",
                prerequisites=(f"reentry:job-review:{job_key}",), links=links)
        else:
            add(f"job-action:{job_key}", "Take a job application step", "Apply where confirmed requirements fit, or ask about a trainee route. Report only qualifications you hold.",
                "employment", work_priority, "ID assistance does not automatically block an application.",
                prerequisites=(f"reentry:job-review:{job_key}",), links=links)
    elif goal == "keep_work":
        add("work-routine", "Plan a workable routine", "Check your work hours, transport, and any appointments you report. Confirm practical arrangements with your employer.",
            "employment", work_priority, "You chose keeping or improving your current work rather than starting an application.")
    elif goal == "unsure":
        add("work-goal", "Choose your next work step", "Decide whether you want to look for work, prepare for a role, or focus on another need first.",
            "planning", "medium", "Your work goal is unsure; the plan does not assume you need to apply.")

    if priority_need in {"food", "health_care", "community_support", "transportation"}:
        if not (priority_need == "transportation" and situation.get("has_transportation") != "yes"):
            add(f"priority-{priority_need}", f"Find {priority_need.replace('_', ' ')} support",
                "Review nearby candidate resources. Confirm the specific help, cost, and intake process before relying on them.",
                priority_need, "high", "You chose this as your priority need.")
    areas = housing.get("areas", [])
    scenario = bool(selection.get("housing_income_job_id"))
    housing_priority = "high" if priority_need == "housing" else "later" if housing_answer == "yes" else "medium"
    if housing_answer != "yes" or priority_need == "housing" or scenario:
        add("housing-long-term", "Compare longer-term housing costs",
            "Compare area rents with your chosen job's hypothetical income. Check all pay and hours assumptions." if scenario
            else "Compare area rents and possible income. Set a budget only when your own income and costs are known.",
            "housing", housing_priority,
            "Housing research can start before a job offer." + (" No rental summaries are available here yet." if not areas else ""),
            confirmations=("These are area summaries, not available homes or landlord approval. Expected pay is not current income.",))
    if not tasks:
        add("confirm-priority", "Choose your next priority", "Review what you want help with first. Update your answers if work is not your next goal.",
            "planning", "medium", "No practical barriers were reported, and you chose to focus on other needs before work.")

    tasks = ordered_tasks(tasks)
    completed = set(request.get("reentry_completed_ids", []))
    by_id = {t.task_id: t for t in tasks}
    # A client cannot complete a dependent action before its reported prerequisites.
    valid_completed = set()
    for task in tasks:
        task.planning_day = max(1 if task.priority in {"immediate", "high"} else 3 if task.priority == "medium" else 14,
                                max((by_id[p].planning_day + 1 for p in task.prerequisites), default=1))
        if task.task_id in completed and set(task.prerequisites) <= valid_completed:
            valid_completed.add(task.task_id)
        task.status = "completed" if task.task_id in valid_completed else "todo" if set(task.prerequisites) <= valid_completed else "waiting"
        if referral_lookup:
            task.referrals = referral_lookup(task.barrier)

    native_days = {a["day"]: a for a in (selection.get("thirty_day_plan") or {}).get("daily_actions", [])}
    days = []
    for day in range(1, 31):
        assigned = [t for t in tasks if t.planning_day == day]
        # Reused job activities change with the goal. Completion from the previous
        # role must not mark the new role's application/training days complete.
        day_id = f"reentry:day:{day}:{job_key}"
        if assigned:
            title = assigned[0].title if len(assigned) == 1 else "Work on your next steps"
            action = assigned[0].action if len(assigned) == 1 else "Use today's steps below. Start with immediate needs, and confirm details before you travel or spend money."
            if all(t.task_id in valid_completed for t in assigned):
                valid_completed.add(day_id)
        elif day in native_days:
            native = native_days[day]
            title, action = native["title"], native["action"]
            if day_id in completed:
                valid_completed.add(day_id)
        else:
            title = "Review your next steps" if day % 7 else "Review the week"
            followup = tasks[(day - 1) % len(tasks)]
            action = f"Review: {followup.title}. Check replies and unfinished steps. Follow up at the provider's stated time, and update your answers if needs change."
            if day_id in completed:
                valid_completed.add(day_id)
        days.append(ReentryDay(action_id=day_id, day=day, title=title, action=action,
            phase="First steps" if day <= 7 else "Follow through", task_ids=[t.task_id for t in assigned],
            links=native_days[day].get("links", []) if not assigned and day in native_days else []))
    return ReentryPlan(start_date=today, synthetic=source == "synthetic", tasks=tasks,
        next_task_ids=[t.task_id for t in tasks if t.status == "todo"][:3], completed_ids=sorted(valid_completed),
        daily_actions=days, notes=[
            "This is a suggested sequence, not appointment dates or a deadline to finish every barrier.",
            "Marked complete means you reported completing a step; it does not verify eligibility or resolve every need.",
            "Contact to confirm all referrals. Positive reviews do not establish reentry eligibility.",
            "Preparing for release? Arrange help through a trusted support person if direct contact is unavailable.",
        ])


def generate_plan(profile, recommendations, selected_recommendations, existing_tasks, user_events, *, today: date):
    """Replan incomplete actions while retaining completed/archived user history.

    Reuses the barrier rules above, exact job evidence, and the existing calendar
    action contract. No network/LLM calls and no shared-provider mutations.
    """
    from src.recommend.reentry_domain import PlanTask, PlanChange, profile_request, completion_outcome
    from src.recommend.reentry_resources import task_types, attach_resources

    resources = {r.id: r for r in recommendations}
    available = [r for r in recommendations if r.active and r.userStatus not in {"dismissed", "rejected"}
                 and r.userReportedAvailability != "unavailable"]
    selected = [resources[i] for i in selected_recommendations if i in resources]
    chosen_jobs = [r for r in selected if r.category == "job" and r in available]
    cards = [{"job_id": r.details["jobId"], "title": r.title, "url": r.sourceUrl,
              "requirements": r.details.get("requirements", []), "qualification_checks": r.details.get("qualificationChecks", [])}
             for r in recommendations if r.category == "job" and "jobId" in r.details]
    request = profile_request(profile)
    generated = {}
    categories = {"housing": "housing", "employment": "employment", "qualifications": "employment", "documents": "documents",
                  "identification": "documents", "transportation": "transportation", "health_care": "healthcare", "community_support": "community_support"}
    # Employment already obtained is not another general job search. Existing
    # selections stay in history; pending search actions are archived below.
    last_employment = next((i for i in range(len(user_events) - 1, -1, -1) if user_events[i].type == "job_obtained" or user_events[i].payload.get("employmentTransition") == "job_obtained"), -1)
    explicit_new_jobs = {e.payload.get("recommendationId") for e in user_events[last_employment + 1:] if e.type == "resource_status" and e.payload.get("status") == "selected"}
    job_goals = chosen_jobs if profile.employment.status != "employed" else [r for r in chosen_jobs if r.id in explicit_new_jobs]
    for job in job_goals or [None]:
        base = build_reentry_plan({**request, "selected_job_id": job.details["jobId"] if job else None},
            {"groups": [{"items": cards}]}, {"areas": [r.id for r in recommendations if r.mode == "long_term_area"]}, {},
            source="real", today=today)
        for task in base.tasks:
            if task.barrier == "food" and profile.barriers.hasFoodAccess is True:
                continue
            if task.barrier == "appointment" or task.task_id == "reentry:appointment-trip":
                continue  # Per-appointment stable IDs/deadlines below.
            if task.barrier == "communication" and profile.barriers.communicationAccess == "limited":
                continue
            selected_need = {"health_care": "healthcare", "qualifications": "education", "identification": "identification"}.get(task.barrier, task.barrier)
            if task.task_id.startswith("reentry:priority-") and selected_need not in profile.supportNeeds:
                continue  # A legacy discovery default is not a reported need.
            related = ([job.id] if job else [r.id for r in available if r.category == "job"][:5]) if task.barrier in {"qualifications", "employment"} else [r.id for r in available
                if (task.barrier == "housing" and r.category == "housing") or r.details.get("barrier") == task.barrier]
            item = PlanTask(id=task.task_id, title=task.title, description=task.action,
                category=categories.get(task.barrier, "other"), priority={"immediate": "critical", "later": "low"}.get(task.priority, task.priority),
                prerequisiteTaskIds=task.prerequisites, relatedRecommendationIds=related[:5], rationale=task.rationale,
                deadline=(profile.release.date if profile.release.status == "pre_release" else None) if task.task_id == "reentry:housing-now" else task.deadline,
                stage=task.stage, source="recommendation" if job else "profile",
                referenceLinks=[{"label": f"Source job: {job.title}", "url": job.sourceUrl}] if job and job.sourceUrl and task.barrier in {"qualifications", "employment"} else task.links)
            if item.id in generated:
                item.relatedRecommendationIds = list(dict.fromkeys(generated[item.id].relatedRecommendationIds + item.relatedRecommendationIds))
            generated[item.id] = item
            if item.id == "reentry:housing-now":
                item.priority = "critical"

    def add(key, title, description, category, priority, rationale, *, related=(), prerequisites=(), deadline=None, stage="removing_barriers", source="profile"):
        generated[key] = PlanTask(id=key, title=title, description=description, category=category, priority=priority,
            rationale=rationale, relatedRecommendationIds=list(related), prerequisiteTaskIds=list(prerequisites),
            deadline=deadline, stage=stage, source=source)

    from src.recommend.reentry_finances import assess_finances, BUDGET_SOURCE
    financial = assess_finances(profile.finances)
    budget_basis = "plan estimates" if profile.finances.projection and profile.finances.projection.estimatedFields else "reported amounts"
    if financial["housingHigh"] or financial["status"] in {"deficit", "tight"}:
        import hashlib
        budget_key = hashlib.sha256(profile.finances.model_dump_json().encode()).hexdigest()[:12]
        if financial["status"] in {"deficit", "tight"}:
            gap = financial["remaining"]
            add(f"finances:budget:{budget_key}", "Make room in your monthly budget",
                f"Your listed costs exceed take-home income by ${abs(gap):,.2f} each month. Check your amounts, identify a cost you can change, and review the support options in Finances." if gap < 0 else "No spare income is reported. Check how essentials are covered and which bills may come later." if profile.finances.monthlyTakeHomePay == 0 else "Your listed costs use at least 80% of take-home income. Check irregular bills and choose one cost or income change to create a buffer.",
                "other", "critical" if gap < 0 else "high", f"Your {budget_basis} leave a shortfall or a small buffer. Check actual amounts before relying on an estimate.", stage="immediate_stability")
            generated[f"finances:budget:{budget_key}"].referenceLinks = [{"label": "CFPB monthly budget worksheet", "url": BUDGET_SOURCE}]
        if financial["housingHigh"]:
            add(f"finances:housing:{budget_key}", "Review your housing costs",
                "Housing exceeds Phoenix’s 30% take-home-pay planning target. Check your actual cost and consider relevant housing assistance or lower-cost areas. Area estimates do not establish available homes.",
                "housing", "high", f"Housing uses a large share of income in your {budget_basis}.", stage="immediate_stability")
        if financial["status"] in {"deficit", "tight"} and (profile.finances.monthlyFoodCost or 0) > 0:
            add(f"finances:food:{budget_key}", "Check food-cost support",
                "Review food assistance that could reduce your monthly costs. Confirm eligibility, hours and the specific help before relying on it.",
                "other", "high", "Food is part of a budget that has little money left.", stage="immediate_stability")
        if financial["status"] == "deficit" and profile.employment.status != "not_seeking":
            add(f"finances:income:{budget_key}", "Review ways to increase income",
                "Check suitable openings or ask your current employer about available hours. Confirm pay and requirements; a posting is an opportunity, not current income.",
                "employment", "high", f"Income does not cover listed costs in your {budget_basis}.", stage="building_independence")

    for job in job_goals:
        if job.userStatus in {"applied", "accepted"}:
            application = generated.get(f"reentry:job-action:{job.details['jobId']}")
            if application:
                application.status = "completed"
        for check in job.details.get("qualificationChecks", []):
            if check.get("status") != "gap" or check.get("requirement_kind") != "required" or check.get("field") not in {"certification", "education"}:
                continue
            confirmation = f"reentry:qualification:{job.details['jobId']}:{check['key']}"
            add(f"training:{job.details['jobId']}:{check['key']}", f"Find preparation for {check['label']}",
                "Ask about the right training, entry rules, cost and employer-accepted proof. Confirm the route before enrolling; completion within 30 days is not guaranteed.",
                "employment", "high", check.get("detail", "You reported this required qualification missing."),
                prerequisites=[confirmation] if confirmation in generated else [], stage="building_independence", source="recommendation")
            if job.sourceUrl:
                generated[f"training:{job.details['jobId']}:{check['key']}"].referenceLinks = [{"label": f"Source job: {job.title}", "url": job.sourceUrl}]

    housing_candidates = [r.id for r in available if r.mode == "temporary_housing"][:5]
    if profile.barriers.communicationAccess == "limited":
        add("communication:limited", "Arrange a way to receive messages", "Choose a reliable time and place to check messages. Ask a library or support organization about phone and internet access.",
            "community_support", "high", "You reported limited communication access.", related=[r.id for r in available if r.details.get("barrier") == "communication"][:3])
    if profile.housing.status == "temporary":
        end = profile.housing.temporaryHousingEndDate
        soon = end is not None and (end - today).days <= 7
        add("housing:continuity", "Plan your next place to stay", "Contact housing support before your current arrangement ends. Confirm intake, costs, and available options.",
            "housing", "critical" if soon else "high", f"You reported temporary housing ending {end.isoformat()}." if end else "Your housing is temporary; the end date is unknown.",
            related=housing_candidates, deadline=end, stage="immediate_stability")
        previous_continuity = next((t for t in existing_tasks if t.id == "housing:continuity" and t.status == "completed"), None)
        if soon and previous_continuity is not None:
            add(f"housing:continuity-check:{end.isoformat()}", "Confirm your next place to stay", "Check whether your next place is confirmed. If it is not, contact housing assistance again before the current arrangement ends.",
                "housing", "critical", "Your current housing is still temporary and the end date is close. Earlier completed steps are kept.",
                related=housing_candidates, deadline=end, stage="immediate_stability")
    for appointment in profile.upcomingAppointments:
        days = (appointment.date - today).days if appointment.date else None
        priority = "critical" if days is not None and days <= 3 else "high"
        key = f"appointment:{appointment.id}"
        add(key, f"Prepare for {appointment.label}", "Use your own notice or contact person to confirm the time, place, and what to bring. Keep details private.",
            "other", priority, "You chose to track this appointment; no supervision rules are inferred.", deadline=appointment.date)
        if profile.barriers.hasTransportation is not True:
            add(f"trip:{appointment.id}", f"Plan travel for {appointment.label}", "Use the confirmed details to check a route, travel time, and cost.",
                "transportation", priority, "Travel planning depends on confirmed appointment details.", prerequisites=[key],
                deadline=appointment.date, related=[r.id for r in available if r.details.get("barrier") == "transportation"][:3])
    if not profile.upcomingAppointments and profile.appointmentStatus in {"yes", "unsure"}:
        add("appointment:confirmation", "Check any appointments you want to track", "Review your own notices. Add a general label and date if you want a reminder; private details are not needed.",
            "other", "medium", "Appointment timing is unknown; no obligation or date is assumed.")
    import hashlib
    for goal in profile.goals:
        key = hashlib.sha256(goal.strip().casefold().encode()).hexdigest()[:16]
        add(f"goal:{key}", f"Your goal: {goal[:100]}", "Choose one practical step for this goal. Record progress in your notes and update your situation when it changes.",
            "other", "low", "You entered this 30-day goal.", source="user", stage="building_independence")
    need_categories = {"food": ("other", "food"), "healthcare": ("healthcare", "health_care"), "community_support": ("community_support", "community_support"),
                       "education": ("employment", "qualifications"), "identification": ("documents", "identification")}
    for need in dict.fromkeys([*profile.supportNeeds, *(["food"] if profile.barriers.hasFoodAccess is False else [])]):
        if need == "food" and profile.barriers.hasFoodAccess is True:
            continue
        if need in need_categories:
            category, barrier = need_categories[need]
            if not any(t.category == category and t.id.startswith("reentry:priority-") for t in generated.values()):
                action = ("Contact a food pantry or helpline. Ask where and when you can pick up groceries or a meal." if need == "food"
                          else "Contact a provider to ask about the help you need, eligibility, cost and availability.")
                add(f"support:{need}", f"Find {need.replace('_', ' ')} support", action,
                    category, "high", "You selected this support need.", related=[r.id for r in available if r.details.get("barrier") == barrier][:3],
                    stage="immediate_stability" if need in {"food", "healthcare"} else "removing_barriers")
    if profile.employment.status == "employed":
        obtained = next((e.id for e in reversed(user_events) if e.type == "job_obtained" or e.payload.get("employmentTransition") == "job_obtained"), "current")
        add(f"employment:start:{obtained}", "Confirm your work arrangements", "Confirm your start or ongoing schedule, pay, commute, and any documents your employer actually requests.",
            "employment", "high", "You reported employment; general job-search actions can wait.", stage="building_independence", source="user")
    elif profile.employment.status == "unemployed":
        loss = next((e for e in reversed(user_events) if e.type == "job_lost" or e.payload.get("employmentTransition") == "job_lost"), None)
        if loss:
            add(f"employment:restart:{loss.id}", "Review your next work options", "Check current openings and decide whether to keep or change your selected roles. Earlier applications stay in your history.",
                "employment", "high", "You reported that your employment ended.", related=[r.id for r in available if r.category == "job"][:5], stage="building_independence", source="user")
    for resource in selected:
        if resource.userReportedAvailability == "unavailable" or resource.userStatus == "rejected":
            alternatives = [r.id for r in available if r.id != resource.id and r.mode == resource.mode][:5]
            add(f"alternative:{resource.id}", f"Review alternatives to {resource.title}",
                "Review other candidates and choose whom to contact. If none are listed, ask a known support organization for a referral.",
                "housing" if resource.category == "housing" else "community_support", "critical" if resource.mode == "temporary_housing" else "high",
                "You reported this option was unavailable or declined. This report applies only to your plan.", related=alternatives,
                stage="immediate_stability" if resource.mode == "temporary_housing" else "removing_barriers", source="user")
            continue
        if resource.mode == "long_term_area":
            add(f"area-review:{resource.id}", f"Compare costs in {resource.title}", "Compare the area rent range with your budget and confirmed income. Check current homes and all costs separately.",
                "housing", "medium", "You selected an area-level comparison; it is not an available home or approval.", related=[resource.id], source="recommendation", stage="building_independence")
            continue
        if resource.category == "job":
            continue
        key = f"contact:{resource.id}"
        add(key, f"Contact {resource.title}", "Use the source link to ask about the assistance, intake steps, cost, and availability. No place is reserved.",
            "housing" if resource.category == "housing" else "community_support", "critical" if resource.category == "housing" and profile.housing.status == "no_confirmed_housing" else "high", "You selected this resource.", related=[resource.id], source="recommendation",
            stage="immediate_stability" if resource.category == "housing" else "removing_barriers")
        if resource.resourceType == "public_transit":
            generated[key].title = f"Check transit at {resource.title}"
            generated[key].description = "Check the operator, current timetable, fare and connections for your destination. A listed station or stop does not confirm a usable route."
        if resource.userStatus in {"contacted", "applied", "accepted"}:
            generated[key].status = "completed"  # Explicit user report of contact.
            add(f"followup:{resource.id}", f"Follow up with {resource.title}", "Follow the provider's stated response window. Confirm the next step before making arrangements.",
                "housing" if resource.category == "housing" else "community_support", "medium", "You reported contacting this resource.",
                related=[resource.id], prerequisites=[key], source="user")

    old = {t.id: t for t in existing_tasks}
    # A new reported setback needs a new action, while its earlier completed
    # counterpart remains completed. Ordinary refreshes reuse the event ID.
    for key, barrier in (("reentry:housing-now", "housing"), ("reentry:identification", "identification"),
                         ("reentry:transportation", "transportation"), ("reentry:communication", "communication"),
                         ("support:food", "food"), ("reentry:priority-food", "food")):
        reported = next((e for e in reversed(user_events) if barrier in e.payload.get("reportedBarriers", [])), None)
        if key in generated and key in old and old[key].status == "completed" and reported:
            followup = generated[key].model_copy(deep=True)
            followup.id = f"{key}:reported:{reported.id}"
            followup.source = "user"
            followup.rationale = "You reported this barrier after an earlier completed step. Earlier progress is kept."
            generated[followup.id] = followup

    def configure_resources(task):
        task.completionOutcome = completion_outcome(task)
        task.allowedResourceTypes = task_types(task)
        candidate_ids = None
        if task.id.startswith(("contact:", "followup:", "alternative:")):
            resource_id = task.id.split(":", 1)[1]
            chosen = resources.get(resource_id)
            if chosen:
                task.allowedResourceTypes = chosen.supportedResourceTypes
                candidate_ids = task.relatedRecommendationIds
                if chosen.sourceUrl:
                    task.referenceLinks = [{"label": f"Source: {chosen.title}", "url": chosen.sourceUrl}]
        elif task.allowedResourceTypes == ["job_posting"]:
            # A specific job action stays attached to that posting; general
            # discovery may draw from the ranked job candidates.
            candidate_ids = task.relatedRecommendationIds or None
        elif task.id.startswith(("reentry:communication", "reentry:confirm-communication", "communication:")):
            candidate_ids = [r.id for r in recommendations if "communication" in r.details.get("barriers", [r.details.get("barrier")])]
        elif task.id.startswith("area-review:"):
            candidate_ids = task.relatedRecommendationIds
        attach_resources(task, profile, recommendations, candidate_ids=candidate_ids)
        return task

    for task in generated.values():
        configure_resources(task)
    changes = []
    for key, task in list(generated.items()):
        if key in old:
            previous = old[key]
            if previous.status == "completed":
                kept = previous.model_copy(deep=True)
                for field in ("allowedResourceTypes", "relatedRecommendationIds", "resourceMatchReasons", "referenceLinks", "resourceEmptyState"):
                    setattr(kept, field, getattr(task, field))
                generated[key] = kept
                continue
            task.notes = previous.notes
            task.blockedByUser = previous.blockedByUser
            if not previous.archived and task.status != "completed":
                task.status = previous.status
            if task.priority != previous.priority:
                changes.append(PlanChange(type="priority_changed", task_id=key, reason=task.rationale))
        else:
            changes.append(PlanChange(type="task_added", task_id=key, reason=task.rationale))
    for key, task in old.items():
        if key not in generated:
            kept = task.model_copy(deep=True)
            if kept.status != "completed":
                kept.status, kept.archived = "skipped", True
                if not task.archived:
                    changes.append(PlanChange(type="task_no_longer_needed", task_id=key, reason="Your circumstances or selected resources changed; history is retained."))
            generated[key] = kept
            configure_resources(kept)
    # Completing an action does not resolve an ongoing housing crisis. Keep one
    # explicit arrangement check, rather than silently promoting job search or
    # resetting the already-completed action.
    immediate_open = any(not t.archived and t.status not in {"completed", "skipped"}
                         and set(t.allowedResourceTypes) & set(BARRIER_TYPES["housing"]) for t in generated.values())
    if (profile.housing.status == "no_confirmed_housing" and not immediate_open
            and any(t.status == "completed" and t.id.startswith("reentry:housing-now") for t in generated.values())):
        episode = next((e.id for e in reversed(user_events) if "housing" in e.payload.get("reportedBarriers", [])), "initial")
        key = f"housing:arrangement-check:{episode}"
        add(key, "Confirm your current place to stay", "If a place is now confirmed, update your situation. If you still need somewhere, review housing assistance and confirm intake before traveling.",
            "housing", "critical", "You completed an action, but your reported housing is still unconfirmed.", stage="immediate_stability")
        if key in old:
            generated[key].status = old[key].status
            generated[key].notes = old[key].notes
            generated[key].blockedByUser = old[key].blockedByUser
        else:
            changes.append(PlanChange(type="task_added", task_id=key, reason=generated[key].rationale))
        configure_resources(generated[key])
    # Preserve historical prerequisites instead of silently deleting task history.
    for task in generated.values():
        if any(key not in generated for key in task.prerequisiteTaskIds):
            raise ValueError("A task references an unknown prerequisite")
    ordered, seen = [], set()
    priorities = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    while len(seen) < len(generated):
        candidates = [t for t in generated.values() if t.id not in seen and set(t.prerequisiteTaskIds) <= seen]
        if not candidates:
            raise ValueError("Task dependency cycle")
        def urgency(task):
            # Internal ordering can recognize tonight's need without publishing
            # an invented user deadline on the task.
            effective_date = today if task.id.startswith("reentry:housing-now") and profile.release.status == "post_release" else task.deadline or date.max
            return priorities[task.priority], effective_date, STAGE[task.stage], task.id
        task = min(candidates, key=urgency)
        if task.status not in {"completed", "skipped"}:
            blocked = task.blockedByUser or any(generated[key].status != "completed" for key in task.prerequisiteTaskIds)
            task.status = "blocked" if blocked else "in_progress" if task.status == "in_progress" else "not_started"
        ordered.append(task)
        seen.add(task.id)
    return ordered, changes


def planned_session(profile, recommendations, previous, event, *, today: date, top_job_ids, warnings,
                    selected_job_id=None, legacy_completed_ids=(), start_date=None):
    """Assemble a pure preview; the browser decides whether to save this state."""
    from datetime import datetime, timezone
    from src.recommend.reentry_domain import PhoenixSession

    selected = list(previous.selectedRecommendationIds) if previous else []
    newly_selected = selected_job_id and f"job:{selected_job_id}" not in selected
    if selected_job_id and f"job:{selected_job_id}" not in selected:
        selected.append(f"job:{selected_job_id}")
    for resource in recommendations:
        if resource.id in selected and resource.userStatus in {"recommended", "saved"}:
            resource.userStatus = "selected"
    events = list(previous.events) if previous else []
    if event and not any(e.id == event.id for e in events):
        events.append(event)
    if newly_selected:
        from src.recommend.reentry_domain import UserEvent
        events.append(UserEvent(type="resource_status", payload={"recommendationId": f"job:{selected_job_id}", "status": "selected"}))
    tasks, changes = generate_plan(profile, recommendations, selected, previous.tasks if previous else [], events, today=today)
    if previous is None:
        for task in tasks:
            if task.id in legacy_completed_ids:
                task.status = "completed"
        complete = {t.id for t in tasks if t.status == "completed"}
        for task in tasks:
            if task.status not in {"completed", "skipped"}:
                task.status = "blocked" if not set(task.prerequisiteTaskIds) <= complete else "not_started"
    # Suggested slots retain completed actions. New/incomplete actions move only
    # to the current/future portion of the roadmap, never an invented deadline.
    calendar_start = (previous.scheduleStartDate if previous else None) or start_date or today
    if (today - calendar_start).days >= 30:
        calendar_start = today
    first_day = max(1, min(30, 1 + (today - calendar_start).days))
    same_window = previous is not None and ((previous.scheduleStartDate or start_date or today) == calendar_start)
    prior_days = {key: d["day"] for d in previous.schedule for key in d["task_ids"]} if same_window else {}
    slots, assigned = {}, {}
    for task in tasks:
        if task.status == "completed" and task.id in prior_days:
            day = prior_days[task.id]
            slots.setdefault(day, []).append(task)
            assigned[task.id] = day
    pending = [t for t in tasks if not t.archived and t.status not in {"completed", "skipped"}]
    unfinished = {t.id for t in pending}
    for index, task in enumerate(pending):
        day = first_day if task.priority == "critical" else min(30, first_day + index // 2)
        if task.id in prior_days:
            day = max(first_day, prior_days[task.id])
        day = min(30, max(day, max((assigned.get(k, first_day) + 1 for k in task.prerequisiteTaskIds if k in unfinished), default=first_day)))
        assigned[task.id] = day
        slots.setdefault(day, []).append(task)
    resources = {r.id: r for r in recommendations}
    schedule = [{"action_id": f"reentry-day:{day}", "day": day,
                 "title": slots[day][0].title if day in slots else "Review your progress",
                 "action": " ".join(t.description for t in slots.get(day, [])) or "Review progress. Update your situation if something changes.",
                 "phase": "Your reentry plan", "links": list({r.id: {"label": r.title, "url": r.sourceUrl, "role": "job_posting" if r.category == "job" else "provider_finder"}
                     for task in slots.get(day, []) for key in task.relatedRecommendationIds
                     if (r := resources.get(key)) and r.sourceUrl and r.sourceUrl.startswith(("https://", "http://"))}.values())[:5],
                 "task_ids": [t.id for t in slots.get(day, [])]}
                for day in range(1, 31)]
    return PhoenixSession(profile=profile, recommendations=recommendations, tasks=tasks,
        selectedRecommendationIds=selected, dismissedRecommendationIds=previous.dismissedRecommendationIds if previous else [],
        events=events, lastPlannedAt=datetime.now(timezone.utc), changes=changes, warnings=warnings,
        topJobIds=top_job_ids, schedule=schedule, scheduleStartDate=calendar_start)

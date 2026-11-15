import type { PlanLink, ThirtyDayPlan } from "./types";

export interface PlanDay {
  id: string;
  day: number;
  date: Date;
  title: string;
  action: string;
  phase: string;
  links: PlanLink[];
}

// Calendar arithmetic keeps the local date intact across daylight-saving changes.
export function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days, 12);
}

export function dateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function monthCells(month: Date): Date[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1, 12);
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const length = Math.ceil((first.getDay() + count) / 7) * 7;
  return Array.from({ length }, (_, index) => addDays(first, index - first.getDay()));
}

export type CalendarPlan = Pick<ThirtyDayPlan, "daily_actions" | "credential_paths" | "steps" | "notes" | "target_job_title">;

export function buildDailyPlan(plan: CalendarPlan, start: Date): PlanDay[] {
  const daily = plan.daily_actions;
  if (daily?.length === 30 && new Set(daily.map((item) => item.action_id)).size === 30
      && daily.every((item) => Number.isInteger(item.day) && item.day >= 1 && item.day <= 30)
      && new Set(daily.map((item) => item.day)).size === 30) {
    return [...daily].sort((a, b) => a.day - b.day).map((item) => ({
      id: item.action_id, day: item.day, date: addDays(start, item.day - 1),
      title: item.title, action: item.action, phase: item.phase, links: item.links,
    }));
  }
  // Backward-compatible display for older API fixtures without daily actions.
  const missing = plan.credential_paths.filter((path) => path.user_status !== "reported_held");
  const required = missing.filter((path) => path.requirement_kind === "required");
  const held = plan.credential_paths.filter((path) => path.user_status === "reported_held");
  const credentialNames = missing.map((path) => path.credential).join(", ");
  const heldNames = held.map((path) => path.credential).join(", ");
  const needsExperience = plan.steps.some((step) => step.track === "experience");
  const credentialAction = missing.length
    ? `For ${credentialNames}, confirm the exact issuing body, prerequisites, and employer-accepted route. Ask whether each credential is required before starting or only preferred.`
    : held.length ? `Check the validity and employer acceptance of your ${heldNames}. Gather your existing records before considering repeat training.`
    : "Ask the employer whether any license, certificate, screening, or role-specific experience is required. Write down anything still unclear before choosing training.";
  const applicationAction = required.length || needsExperience
    ? "Check your confirmed qualifications against the posting. Apply if you meet them, or ask about a trainee route and when an application would be appropriate. Do not claim a pending qualification as earned."
    : "If the opening and required qualifications are confirmed, send your tailored application. A preferred credential alone need not delay applying. Save a copy and the submission date.";
  const templates: [string, string][] = [
    ["Check the opening", `Open the posting for ${plan.target_job_title}. Ask whether the vacancy is still open and how to apply. Save the employer's response.`],
    ["List requirements", "Separate mandatory qualifications from preferences. Compare them with your experience and write down the questions to ask the employer."],
    ["Gather documents", "Collect the work history, references, and qualification records requested by the employer. Keep sensitive documents private until a verified application process needs them."],
    ["Update your résumé", `Tailor your résumé to ${plan.target_job_title}. Highlight two relevant skills with honest examples of work you have done.`],
    ["Check your pathway", credentialAction],
    ["Ask about support", "Contact a local job center about résumé help, accepted training, and any available cost support. Confirm eligibility and costs before committing."],
    ["Review week one", "Review the employer's answers. Choose your next milestone: apply, verify an existing credential, or begin a confirmed preparation pathway."],
    ["Prepare to apply", "Draft a short introduction explaining why this role fits your skills. Check that the employer's application link still works."],
    ["Choose references", "Ask two people who know your work whether they can be references. Confirm how they would like to be contacted."],
    ["Take the next step", applicationAction],
    ["Plan your commute", "Check the worksite, likely shift times, and transport options. Note any travel costs or scheduling questions to confirm."],
    [missing.length ? "Compare training" : "Practice a job skill", missing.length
      ? `Compare accepted options for ${credentialNames}. Ask about practical components, total cost, start dates, and funding before enrolling.`
      : "Pick one skill named in the posting. Practice safely or prepare a concrete example showing how you have used it."],
    ["Confirm your schedule", "Check your availability against the employer's shifts and any confirmed appointments or training. Ask about conflicts before agreeing to a schedule."],
    ["Review week two", "Record applications, employer replies, and confirmed preparation steps. If a requirement is unclear, ask before spending money or making commitments."],
    ["Follow up", "If you applied and the employer's stated response window has passed, send a brief follow-up. Otherwise, check your preparation milestone and next available date."],
    ["Practice your introduction", "Practice a one-minute introduction: your relevant skills, the work you want to do, and why this role interests you."],
    ["Prepare work examples", "Write two short examples of solving a problem, working reliably, or learning a skill. Use real experience from work, volunteering, or daily responsibilities."],
    [missing.length ? "Check training progress" : "Prepare interview answers", missing.length
      ? "If you chose an accepted training route, review progress with the provider. Confirm prerequisites and the next supervised session or assessment; extend the timeline if needed."
      : "Practice answers about your strengths, availability, and relevant experience. Prepare a question about the team's expectations."],
    ["Check your documents", "Review your résumé, references, and earned credentials for accuracy. Mark any training still underway as in progress."],
    ["Prepare for a meeting", "If an interview or provider meeting is scheduled, confirm the time, location, and what to bring. If none is scheduled, request an update on your next step."],
    ["Review week three", "List what is complete and what is waiting on an employer or provider. Choose one practical action you can take this week."],
    ["Recheck the opportunity", "Check that the target opening is still available. If it has closed, look for the same role with another employer and reuse your preparation."],
    ["Confirm qualification progress", "Ask the employer or provider which requirements you now meet and which remain. Record only completed, accepted qualifications on your application."],
    ["Practice an interview", "Run through a practice interview with someone you trust. Focus on clear examples and two questions about the job."],
    ["Update your application", "If you earned a qualification or gained relevant experience, update your résumé and any active application. Otherwise, check the next confirmed milestone."],
    ["Ask for the next step", "Follow the employer's contact instructions to ask about an interview, application status, or trainee route. Respect any stated follow-up timeline."],
    ["Confirm practical details", "If an offer is made, confirm pay, shifts, worksite, required checks, and the written start arrangements. Otherwise, prepare these questions for the next conversation."],
    ["Review your progress", "Compare your progress with the requirements you listed on day two. Note completed steps and any remaining gap, cost, or scheduling issue."],
    ["Set your next milestone", "Confirm the next available interview, assessment, or training date with the relevant person. If it falls after this plan, write down that date and the preparation needed."],
    ["Move toward your goal", `Review your progress toward ${plan.target_job_title}. Confirm a start if an offer is made and requirements are met; otherwise, leave with an active application or a confirmed next preparation milestone.`],
  ];
  const allowedSteps = plan.steps.filter((step) => step.track !== "interim_work");
  return templates.map(([title, action], index) => {
    const day = index + 1;
    const links = allowedSteps.filter((step) => day >= step.day_start && day <= step.day_end).flatMap((step) => step.links);
    if ([5, 12, 18, 23].includes(day)) links.push(...plan.credential_paths.flatMap((path) => path.links));
    const roles: PlanLink["role"][] = day === 6 ? ["funding_support"] : [5, 23].includes(day) ? ["official_requirements"]
      : [12, 18].includes(day) ? ["provider_finder", "funding_support"] : ["job_posting"];
    return {
      id: `day-${day}`, day, date: addDays(start, index), title, action,
      phase: day <= 7 ? "Get ready" : day <= 14 ? "Take action" : day <= 21 ? "Build momentum" : "Work toward your goal",
      links: [...new Map(links.filter((link) => roles.includes(link.role)).map((link) => [link.url, link])).values()],
    };
  });
}

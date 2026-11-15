import type { PhoenixSession, PlanTask, Recommendation, ReentryProfile } from "./domain";

export const RESOURCE_LABELS = {
  job_posting: "Job posting", transitional_housing: "Transitional housing", housing_assistance: "Housing assistance",
  rental_market: "Rental cost information", transportation_assistance: "Transportation assistance", public_transit: "Public transit",
  identification_assistance: "ID assistance", workforce_training: "Workforce training", food_assistance: "Food assistance",
  healthcare: "Health care", community_support: "Community support",
};
export function resourceLabel(resource: Recommendation): string {
  return resource.resourceType ? RESOURCE_LABELS[resource.resourceType] : resource.mode === "job" ? "Job posting"
    : resource.mode === "long_term_area" ? "Rental cost information" : resource.mode === "temporary_housing" ? "Housing assistance" : "Service candidate";
}
export function taskResourceLabel(task: PlanTask, resource: Recommendation): string {
  const supported = resource.supportedResourceTypes ?? (resource.resourceType ? [resource.resourceType] : []);
  const match = task.allowedResourceTypes?.find(type => supported.includes(type));
  return match ? RESOURCE_LABELS[match] : resourceLabel(resource);
}
export const readyTasks = (session: PhoenixSession): PlanTask[] => session.tasks.filter((task) => !task.archived && ["not_started", "in_progress"].includes(task.status));
export const taskPrerequisites = (task: PlanTask, session: PhoenixSession): PlanTask[] => task.prerequisiteTaskIds.flatMap(id => session.tasks.filter(t => t.id === id && t.status !== "completed"));
function orderTasks(tasks: PlanTask[]) {
  const priority = { critical: 0, high: 1, medium: 2, low: 3 };
  const remaining = [...tasks].sort((a, b) => priority[a.priority] - priority[b.priority]);
  const result: PlanTask[] = [];
  while (remaining.length) {
    const index = remaining.findIndex(t => !t.prerequisiteTaskIds.some(id => remaining.some(p => p.id === id)));
    result.push(...remaining.splice(index < 0 ? 0 : index, 1));
  }
  return result;
}
export const planTasks = (session: PhoenixSession): PlanTask[] => orderTasks(session.tasks.filter(t => !t.archived || t.status === "completed"));
export function stableTaskOrder(tasks: PlanTask[], previousIds: string[]): PlanTask[] {
  const byId = new Map(tasks.map(task => [task.id, task]));
  const known = new Set(previousIds);
  return [...previousIds.flatMap(id => byId.has(id) ? [byId.get(id)!] : []), ...tasks.filter(task => !known.has(task.id))];
}
export function taskProgress(session: PhoenixSession) {
  const tasks = planTasks(session);
  const completed = tasks.filter(task => task.status === "completed").length;
  const skipped = tasks.filter(task => task.status === "skipped").length;
  const left = tasks.filter(task => task.status !== "completed" && task.status !== "skipped").length;
  return { completed, skipped, left, total: tasks.length, percent: tasks.length ? Math.round(completed / tasks.length * 100) : 0 };
}
export function taskResult(task: PlanTask, profile: ReentryProfile) {
  const outcome = task.completionOutcome ?? (task.id.startsWith("reentry:housing-now") || task.id.startsWith("reentry:confirm-housing") || task.id.startsWith("housing:arrangement-check:") || task.id.startsWith("housing:continuity") ? "housing_arranged"
    : task.id.startsWith("support:food") || task.id.startsWith("reentry:priority-food") ? "food_secured"
    : task.id.startsWith("reentry:transportation") || task.id.startsWith("reentry:confirm-transportation") ? "transportation_arranged" : null);
  if (outcome === "housing_arranged") return { outcome, label: "Housing arranged", recorded: ["stable", "temporary"].includes(profile.housing.status) };
  if (outcome === "food_secured") return { outcome, label: "Food secured", recorded: profile.barriers.hasFoodAccess === true };
  if (outcome === "transportation_arranged") return { outcome, label: "Transportation arranged", recorded: profile.barriers.hasTransportation === true };
  return null;
}
export function taskGroups(session: PhoenixSession) {
  const active = session.tasks.filter(t => !t.archived);
  const inProgress = orderTasks(active.filter(t => t.status === "in_progress"));
  const todo = orderTasks(active.filter(t => t.status === "not_started" || t.status === "blocked"));
  return { inProgress, todo, left: inProgress.length + todo.length, completed: session.tasks.filter(t => t.status === "completed"), skipped: active.filter(t => t.status === "skipped") };
}
export function taskResources(task: PlanTask, session: PhoenixSession): Recommendation[] {
  return task.relatedRecommendationIds.flatMap(id => session.recommendations.filter(r => r.id === id && r.active
    && !["dismissed", "rejected"].includes(r.userStatus) && r.userReportedAvailability !== "unavailable"
    && (!task.allowedResourceTypes?.length || task.allowedResourceTypes.some(type => (r.supportedResourceTypes ?? (r.resourceType ? [r.resourceType] : [])).includes(type)))));
}
export const actionableResources = (session: PhoenixSession): Recommendation[] => session.recommendations.filter((resource) => resource.active && !["dismissed", "rejected"].includes(resource.userStatus) && resource.userReportedAvailability !== "unavailable");
const known = (value: boolean | null | undefined) => value === true ? "Available" : value === false ? "Assistance needed" : "Not reported";
const text = (value: unknown): string => value == null || value === "" ? "Not reported" : Array.isArray(value) ? value.length ? value.join(", ") : "None reported" : String(value);
const housing = { stable: "Stable", temporary: "Temporary", no_confirmed_housing: "No confirmed housing", unsure: "Not sure" };
const employment = { unemployed: "Looking for work", employed: "Employed", seeking_training: "Seeking training", not_seeking: "Not seeking work", unsure: "Not sure" };
export function circumstances(profile: ReentryProfile) {
  return [
    { label: "Housing", value: housing[profile.housing.status] },
    { label: "Food", value: known(profile.barriers.hasFoodAccess) },
    { label: "Employment", value: employment[profile.employment.status] },
    { label: "Identification", value: known(profile.barriers.hasGovernmentId) },
    { label: "Transportation", value: known(profile.barriers.hasTransportation) },
  ];
}
export function releaseSummary(profile: ReentryProfile): string {
  const label = { pre_release: "Preparing for release", post_release: "After release", unsure: "Release timing unsure", prefer_not_to_answer: "Release timing private" }[profile.release.status];
  return profile.release.date ? `${label} · reported date ${profile.release.date}` : label;
}

export function circumstanceChanges(before: ReentryProfile, after: ReentryProfile) {
  const financial = (p: ReentryProfile, key: "monthlyTakeHomePay" | "monthlyHousingCost" | "monthlyFoodCost" | "monthlyOtherCosts") => p.finances?.[key] == null ? null : `$${p.finances[key].toFixed(2)}${p.finances.projection?.estimatedFields.includes(key) ? " (estimate)" : ""}`;
  const fields: [string, (p: ReentryProfile) => unknown][] = [
    ["Location", p => [p.location.city, p.location.zipCode].filter(Boolean).join(" ")],
    ["Release phase", p => releaseSummary(p)], ["Housing", p => housing[p.housing.status]],
    ["Temporary housing ends", p => p.housing.temporaryHousingEndDate], ["Monthly housing budget", p => p.housing.monthlyBudget == null ? null : `$${p.housing.monthlyBudget}`],
    ["Employment", p => employment[p.employment.status]], ["Work interests", p => p.employment.preferredJobTypes],
    ["Work experience", p => [p.employment.experienceYears == null ? "Years not reported" : `${p.employment.experienceYears} years`, ...p.employment.skills, p.employment.experienceText].filter(Boolean).join(" · ")],
    ["Education", p => p.employment.educationLevel?.replaceAll("_", " ")], ["Certificates", p => p.employment.certifications],
    ["Identification", p => known(p.barriers.hasGovernmentId)], ["Transportation", p => known(p.barriers.hasTransportation)],
    ["Food", p => known(p.barriers.hasFoodAccess)],
    ["Phone access", p => known(p.barriers.hasPhoneAccess)], ["Internet access", p => known(p.barriers.hasInternetAccess)],
    ["Communication", p => p.barriers.communicationAccess], ["Support needs", p => p.supportNeeds.map(v => v.replaceAll("_", " "))],
    ["Appointments", p => p.upcomingAppointments.map(a => [a.label, a.date ?? "Date not reported", a.location].filter(Boolean).join(" · "))],
    ["Appointment information", p => p.appointmentStatus.replaceAll("_", " ")], ["30-day goals", p => p.goals],
    ["Monthly take-home income", p => financial(p, "monthlyTakeHomePay")],
    ["Monthly housing cost", p => financial(p, "monthlyHousingCost")],
    ["Monthly food cost", p => financial(p, "monthlyFoodCost")],
    ["Other monthly costs", p => financial(p, "monthlyOtherCosts")],
    ["Budget assumptions", p => p.finances?.projection ? `${p.finances.projection.hoursPerWeek} hours/week; ${p.finances.projection.takeHomePercent}% of gross pay kept. Estimated fields are planning amounts.` : null],
  ];
  return fields.flatMap(([label, get]) => JSON.stringify(get(before)) === JSON.stringify(get(after)) ? [] : [{ label, before: text(get(before)), after: text(get(after)) }]);
}

export function rebaseSituation(before: ReentryProfile, proposed: ReentryProfile, current: ReentryProfile): ReentryProfile {
  function merge(old: unknown, next: unknown, latest: unknown): unknown {
    if (JSON.stringify(old) === JSON.stringify(next)) return structuredClone(latest);
    if (next && typeof next === "object" && !Array.isArray(next) && old && typeof old === "object" && latest && typeof latest === "object") {
      const result = { ...latest as Record<string, unknown> };
      for (const [key, value] of Object.entries(next)) result[key] = merge((old as Record<string, unknown>)[key], value, (latest as Record<string, unknown>)[key]);
      return result;
    }
    return structuredClone(next);
  }
  return merge(before, proposed, current) as ReentryProfile;
}

export function comparePlans(before: PhoenixSession, after: PhoenixSession) {
  const prior = new Map(before.tasks.map(t => [t.id, t]));
  const next = new Map(after.tasks.map(t => [t.id, t]));
  const activeBefore = actionableResources(before), activeAfter = actionableResources(after);
  const priorResources = new Set(activeBefore.map(r => r.id)), nextResources = new Set(activeAfter.map(r => r.id));
  return {
    added: after.tasks.filter(t => !t.archived && (!prior.has(t.id) || prior.get(t.id)?.archived)),
    reprioritized: after.tasks.filter(t => !t.archived && prior.has(t.id) && prior.get(t.id)?.priority !== t.priority),
    archived: before.tasks.filter(t => !t.archived && (next.get(t.id)?.archived || !next.has(t.id))),
    retained: before.tasks.filter(t => t.status === "completed" && next.get(t.id)?.status === "completed"),
    unchanged: before.tasks.filter(t => JSON.stringify(t) === JSON.stringify(next.get(t.id))),
    newResources: activeAfter.filter(r => !priorResources.has(r.id)), unavailableResources: activeBefore.filter(r => !nextResources.has(r.id)),
    preservedSelections: before.selectedRecommendationIds.filter(id => after.selectedRecommendationIds.includes(id)),
    previousPriorities: readyTasks(before).slice(0, 3), proposedPriorities: readyTasks(after).slice(0, 3),
  };
}

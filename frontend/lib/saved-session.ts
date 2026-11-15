import type { RecommendationRequest, Tab } from "./types";
import { validReentry } from "./reentry";

export const SESSION_STORAGE_KEY = "phoenix-session:v1";
export const RECOVERY_STORAGE_KEY = "phoenix-session:recovery";

export function validAdaptiveSession(value: unknown): boolean {
  if (!record(value) || value.schemaVersion !== 1 || !record(value.profile) || typeof value.profile.profileId !== "string") return false;
  const profile = value.profile;
  if (!["location", "release", "housing", "employment", "barriers"].every((key) => record(profile[key]))) return false;
  if (!Array.isArray(profile.supportNeeds) || !Array.isArray(profile.upcomingAppointments) || !Array.isArray(profile.goals)) return false;
  const location = profile.location as Record<string, unknown>, release = profile.release as Record<string, unknown>;
  const housing = profile.housing as Record<string, unknown>, employment = profile.employment as Record<string, unknown>, barriers = profile.barriers as Record<string, unknown>;
  if (profile.finances !== undefined && !validFinances(profile.finances)) return false;
  const date = (v: unknown) => v === null || typeof v === "string" && savedPlanDate(v) !== null;
  if (typeof location.city !== "string" || !["pre_release", "post_release", "unsure", "prefer_not_to_answer"].includes(String(release.status)) || !date(release.date)
    || !["stable", "temporary", "no_confirmed_housing", "unsure"].includes(String(housing.status)) || !date(housing.temporaryHousingEndDate)
    || !["unemployed", "employed", "seeking_training", "not_seeking", "unsure"].includes(String(employment.status))
    || !strings(employment.skills, 100) || !strings(employment.preferredJobTypes, 30) || !strings(employment.certifications, 100)
    || !["hasGovernmentId", "hasTransportation", "hasPhoneAccess", "hasInternetAccess"].every((key) => barriers[key] === null || typeof barriers[key] === "boolean")
    || (barriers.hasFoodAccess !== undefined && barriers.hasFoodAccess !== null && typeof barriers.hasFoodAccess !== "boolean")
    || !strings(profile.supportNeeds, 8) || !strings(profile.goals, 20)
    || !profile.upcomingAppointments.every((a) => record(a) && typeof a.id === "string" && typeof a.label === "string" && date(a.date))) return false;
  if (!strings(value.selectedRecommendationIds, 200) || !strings(value.dismissedRecommendationIds, 500) || !strings(value.topJobIds, 500)) return false;
  if (!Array.isArray(value.tasks) || value.tasks.length > 500 || !Array.isArray(value.recommendations) || value.recommendations.length > 500 || !Array.isArray(value.events) || value.events.length > 2000) return false;
  const tasks = value.tasks;
  if (!tasks.every((t) => record(t) && typeof t.id === "string" && typeof t.title === "string" && typeof t.description === "string"
    && ["critical", "high", "medium", "low"].includes(String(t.priority))
    && ["not_started", "in_progress", "blocked", "completed", "skipped"].includes(String(t.status))
    && strings(t.prerequisiteTaskIds, 500) && strings(t.relatedRecommendationIds, 500) && typeof t.notes === "string")) return false;
  const ids = new Set(tasks.map((t) => t.id));
  if (ids.size !== tasks.length || tasks.some((t) => t.prerequisiteTaskIds.some((id: string) => !ids.has(id)))) return false;
  return value.recommendations.every((r) => record(r) && typeof r.id === "string" && typeof r.title === "string" && typeof r.description === "string" && typeof r.mode === "string"
      && typeof r.active === "boolean" && strings(r.matchReasons, 100) && strings(r.uncertainties, 100) && record(r.details)
      && ["recommended", "saved", "selected", "contacted", "applied", "accepted", "rejected", "dismissed"].includes(String(r.userStatus)))
    && value.events.every((e) => record(e) && typeof e.id === "string" && typeof e.type === "string" && record(e.payload))
    && Array.isArray(value.schedule) && value.schedule.length === 30 && value.schedule.every((d) => record(d) && typeof d.action_id === "string" && typeof d.title === "string" && typeof d.action === "string" && strings(d.task_ids, 500))
    && Array.isArray(value.changes) && value.changes.every((c) => record(c) && typeof c.reason === "string" && typeof c.type === "string") && strings(value.warnings, 100);
}

export interface SavedSession {
  version: 1;
  onboardingVersion?: 2 | 3;
  request: RecommendationRequest;
  tab: Tab;
  done: string[];
  plan: { jobId: string; startDate: string; completed: string[] } | null;
}

type SessionStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const NEEDS = ["work", "housing", "food", "health_care", "transportation", "community_support"];
const LEVELS = ["no_diploma", "high_school_or_ged", "some_college", "associate", "bachelor", "graduate", "not_sure"];
const TABS = ["jobs", "housing", "services", "plan", "finances"];
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const strings = (value: unknown, max: number): value is string[] =>
  Array.isArray(value) && value.length <= max && value.every((item) => typeof item === "string" && item.length <= 1000);
const optionalNumber = (value: unknown, min: number, max: number) =>
  value === null || (typeof value === "number" && Number.isFinite(value) && value >= min && value <= max);

function validFinances(value: unknown): boolean {
  const fields = ["monthlyTakeHomePay", "monthlyHousingCost", "monthlyFoodCost", "monthlyOtherCosts"];
  if (!record(value) || fields.some(key => value[key] !== null && (typeof value[key] !== "number" || !Number.isFinite(value[key]) || value[key] < 0 || value[key] > 1000000 || Math.abs(Math.round(value[key] * 100) - value[key] * 100) > 0.000001))) return false;
  const projection = value.projection;
  return projection == null || record(projection)
    && ["jobId", "housingId"].every(key => projection[key] === null || typeof projection[key] === "string" && projection[key].length <= 200)
    && typeof projection.hoursPerWeek === "number" && projection.hoursPerWeek > 0 && projection.hoursPerWeek <= 80
    && typeof projection.takeHomePercent === "number" && projection.takeHomePercent > 0 && projection.takeHomePercent <= 100
    && Array.isArray(projection.estimatedFields) && projection.estimatedFields.length <= 4 && projection.estimatedFields.every(key => fields.includes(key));
}

function validRequest(value: unknown): value is RecommendationRequest {
  if (!record(value) || !record(value.experience) || !record(value.education)) return false;
  const { experience, education } = value;
  return typeof value.location === "string" && value.location.trim().length >= 2 && value.location.length <= 80
    && typeof value.priority_need === "string" && NEEDS.includes(value.priority_need)
    && optionalNumber(value.age, 14, 110) && (value.age === null || Number.isInteger(value.age))
    && strings(experience.skills, 100) && (experience.text === null || (typeof experience.text === "string" && experience.text.length <= 1000))
    && optionalNumber(experience.years, 0, 60) && typeof experience.no_experience_yet === "boolean"
    && (education.level === null || (typeof education.level === "string" && LEVELS.includes(education.level)))
    && strings(education.credentials, 100) && (education.no_credentials === undefined || typeof education.no_credentials === "boolean")
    && ["highly_rated", "nearest"].includes(String(value.service_sort))
    && (value.service_need == null || NEEDS.includes(String(value.service_need)))
    && ["highest_pay", "nearest"].includes(String(value.job_sort))
    && (value.reentry == null || validReentry(value.reentry))
    && (value.reentry_completed_ids === undefined || strings(value.reentry_completed_ids, 200))
    && (value.reentry_start_date == null || (typeof value.reentry_start_date === "string" && savedPlanDate(value.reentry_start_date) !== null))
    && (value.selected_job_id == null || (typeof value.selected_job_id === "string" && value.selected_job_id.length > 0))
    && (value.qualification_answers === undefined || (record(value.qualification_answers)
      && Object.keys(value.qualification_answers).length <= 100
      && Object.values(value.qualification_answers).every((answers) => record(answers)
        && Object.keys(answers).length <= 100 && Object.values(answers).every((answer) => typeof answer === "boolean"))));
}

// Save calendar dates without a UTC conversion so a refresh keeps the same day.
export function savedPlanDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const [, year, month, day] = match.map(Number);
  const date = new Date(year, month - 1, day, 12);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
}

export function makeSavedSession(request: RecommendationRequest, tab: Tab, done: string[], completed: string[], start: Date | null, onboardingVersion?: 2 | 3): SavedSession {
  const startDate = start && Number.isFinite(start.getTime())
    ? `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(start.getDate()).padStart(2, "0")}` : null;
  return {
    version: 1, request, tab, done: [...new Set(done)],
    ...(onboardingVersion === 2 || onboardingVersion === 3 ? { onboardingVersion } : {}),
    plan: request.selected_job_id && startDate
      ? { jobId: request.selected_job_id, startDate, completed: [...new Set(completed)] } : null,
  };
}

export function readSavedSession(storage?: SessionStorage): { session: SavedSession | null; available: boolean; recovery?: string } {
  try {
    const raw = (storage ?? window.localStorage).getItem(SESSION_STORAGE_KEY);
    if (!raw) return { session: null, available: true };
    const value: unknown = JSON.parse(raw);
    if (record(value) && record(value.request) && value.request.phoenix_session != null && !validAdaptiveSession(value.request.phoenix_session)) {
      return { session: null, available: true, recovery: raw };
    }
    if (!record(value) || value.version !== 1 || !validRequest(value.request)
      || typeof value.tab !== "string" || !TABS.includes(value.tab) || !strings(value.done, 100)) {
      return record(value) && record(value.request) && (value.request.profile || value.request.phoenix_session)
        ? { session: null, available: true, recovery: raw } : { session: null, available: true };
    }
    const plan = value.plan;
    const validPlan = record(plan) && plan.jobId === value.request.selected_job_id
      && typeof plan.startDate === "string" && savedPlanDate(plan.startDate) && strings(plan.completed, 30);
    return {
      available: true,
      session: {
        version: 1, request: value.request, tab: value.tab as Tab, done: [...new Set(value.done)],
        ...(value.onboardingVersion === 2 || value.onboardingVersion === 3 ? { onboardingVersion: value.onboardingVersion } : {}),
        plan: validPlan ? { jobId: plan.jobId as string, startDate: plan.startDate as string, completed: [...new Set(plan.completed as string[])] } : null,
      },
    };
  } catch (error) {
    // Malformed old data is disposable; a browser denying storage needs a notice.
    return { session: null, available: error instanceof SyntaxError };
  }
}

export function writeSavedSession(session: SavedSession, storage?: SessionStorage): boolean {
  try {
    const target = storage ?? window.localStorage;
    const old = target.getItem(SESSION_STORAGE_KEY);
    if (old) {
      try {
        JSON.parse(old);
        const previous = readSavedSession(target);
        if (previous.recovery) target.setItem(RECOVERY_STORAGE_KEY, old);
        const current = previous.session?.request.phoenix_session, incoming = session.request.phoenix_session;
        if (current && incoming && current.profile.profileId === incoming.profile.profileId) {
          const known = new Set(incoming.events.map(event => event.id));
          // An older open tab must not erase actions saved by another tab.
          if (current.events.some(event => !known.has(event.id))) return false;
        }
      } catch { target.setItem(RECOVERY_STORAGE_KEY, old); }
    }
    target.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    return true;
  } catch {
    return false;
  }
}

export function hasNewerSavedHistory(request: RecommendationRequest, storage?: SessionStorage): boolean {
  const current = readSavedSession(storage).session?.request.phoenix_session, incoming = request.phoenix_session;
  if (!current || !incoming || current.profile.profileId !== incoming.profile.profileId) return false;
  const known = new Set(incoming.events.map(event => event.id));
  return current.events.some(event => !known.has(event.id));
}

export function clearSavedSession(storage?: SessionStorage): boolean {
  try {
    (storage ?? window.localStorage).removeItem(SESSION_STORAGE_KEY);
    (storage ?? window.localStorage).removeItem(RECOVERY_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

export const DRAFT_STORAGE_KEY = "phoenix-onboarding:v1";

// Keep raw input, including incomplete numbers and an unfinished certificate name.
export interface OnboardingDraft {
  adaptive?: boolean;
  housingStatus?: import("./domain").ReentryProfile["housing"]["status"];
  housingEnd?: string;
  housingBudget?: string;
  preferredJobs?: string[];
  phone?: string;
  food?: string;
  internet?: string;
  supportNeeds?: import("./domain").SupportNeed[];
  supportChoice?: "unsure" | "none";
  appointments?: import("./domain").ReentryProfile["upcomingAppointments"];
  goals?: string;
  goalsUnsure?: boolean;
  expUnsure?: boolean;
  certsUnsure?: boolean;
  reentryEnabled?: boolean;
  reentry?: NonNullable<RecommendationRequest["reentry"]>;
  location: string;
  need: RecommendationRequest["priority_need"] | null;
  age: string;
  skills: string[];
  expText: string;
  years: string;
  noExp: boolean;
  level: string;
  certs: string[];
  otherCerts: string;
  noCerts: boolean;
}

export function onboardingDraft(initial: RecommendationRequest | null): OnboardingDraft {
  const p = initial?.profile;
  const answer = (v: boolean | null | undefined) => v === true ? "yes" : v === false ? "no" : "unsure";
  return {
    adaptive: !!p, ...(p ? { housingStatus: p.housing.status, phone: p.barriers.hasPhoneAccess === null && p.barriers.communicationAccess === "limited" ? "limited" : answer(p.barriers.hasPhoneAccess), internet: p.barriers.hasInternetAccess === null && p.barriers.communicationAccess === "limited" ? "limited" : answer(p.barriers.hasInternetAccess) } : {}),
    ...(p ? { food: answer(p.barriers.hasFoodAccess) } : {}),
    housingEnd: p?.housing.temporaryHousingEndDate ?? "", housingBudget: p?.housing.monthlyBudget?.toString() ?? "",
    preferredJobs: p?.employment.preferredJobTypes ?? [], supportNeeds: p?.supportNeeds ?? [],
    appointments: p?.upcomingAppointments ?? [], goals: p?.goals.join("\n") ?? "",
    reentryEnabled: initial?.reentry != null, reentry: initial?.reentry ?? {},
    expUnsure: initial != null && !initial.experience.no_experience_yet && !initial.experience.skills.length && !initial.experience.text && initial.experience.years == null,
    certsUnsure: initial != null && !initial.education.no_credentials && !initial.education.credentials.length,
    location: initial?.location ?? "", need: initial?.priority_need ?? null, age: initial?.age?.toString() ?? "",
    skills: initial?.experience.skills ?? [], expText: initial?.experience.text ?? "", years: initial?.experience.years?.toString() ?? "",
    noExp: initial?.experience.no_experience_yet ?? false, level: initial?.education.level ?? "",
    certs: initial?.education.credentials ?? [], otherCerts: "", noCerts: initial?.education.no_credentials ?? false,
  };
}

export function hasDraftAnswers(draft: OnboardingDraft): boolean {
  return Object.entries(draft).some(([key, value]) => key === "reentryEnabled" || key === "adaptive" ? false
    : key === "reentry" ? Object.values(value ?? {}).some((answer) => answer != null && answer !== "")
    : Array.isArray(value) ? value.length > 0 : value !== "" && value != null && value !== false);
}

export function readOnboardingDraft(storage?: SessionStorage): { draft: OnboardingDraft | null; available: boolean } {
  try {
    const raw = (storage ?? window.localStorage).getItem(DRAFT_STORAGE_KEY);
    if (!raw) return { draft: null, available: true };
    const value: unknown = JSON.parse(raw);
    if (!record(value) || value.version !== 1 || !record(value.answers)) return { draft: null, available: true };
    const draft = value.answers;
    if (!["location", "age", "expText", "years", "level", "otherCerts"].every((key) => typeof draft[key] === "string" && draft[key].length <= 10000)
      || !(draft.need === null || (typeof draft.need === "string" && NEEDS.includes(draft.need)))
      || !(draft.level === "" || LEVELS.includes(draft.level as string))
      || !strings(draft.skills, 100) || !strings(draft.certs, 100)
      || typeof draft.noExp !== "boolean" || typeof draft.noCerts !== "boolean") return { draft: null, available: true };
    if ((draft.reentryEnabled !== undefined && typeof draft.reentryEnabled !== "boolean")
      || (draft.expUnsure !== undefined && typeof draft.expUnsure !== "boolean")
      || (draft.certsUnsure !== undefined && typeof draft.certsUnsure !== "boolean")
      || (draft.reentry !== undefined && !validReentry(draft.reentry))) return { draft: null, available: true };
    if ((draft.adaptive !== undefined && typeof draft.adaptive !== "boolean")
      || (draft.food !== undefined && !["yes", "no", "unsure", "prefer_not_to_say"].includes(draft.food as string))
      || (draft.supportChoice !== undefined && !["unsure", "none"].includes(draft.supportChoice as string))
      || (draft.goalsUnsure !== undefined && typeof draft.goalsUnsure !== "boolean")
      || (draft.preferredJobs !== undefined && !strings(draft.preferredJobs, 30))
      || (draft.supportNeeds !== undefined && !strings(draft.supportNeeds, 8))
      || ["housingEnd", "housingBudget", "goals"].some((key) => draft[key] !== undefined && (typeof draft[key] !== "string" || (draft[key] as string).length > 10000))
      || (draft.appointments !== undefined && (!Array.isArray(draft.appointments) || draft.appointments.length > 20 || !draft.appointments.every((a) => record(a) && typeof a.id === "string" && typeof a.label === "string" && (a.date === null || typeof a.date === "string"))))) return { draft: null, available: true };
    return { draft: draft as unknown as OnboardingDraft, available: true };
  } catch (error) {
    return { draft: null, available: error instanceof SyntaxError };
  }
}

export function writeOnboardingDraft(draft: OnboardingDraft, storage?: SessionStorage): boolean {
  try {
    const target = storage ?? window.localStorage;
    if (hasDraftAnswers(draft)) target.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ version: 1, answers: draft }));
    else target.removeItem(DRAFT_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

export function clearOnboardingDraft(storage?: SessionStorage): boolean {
  try {
    (storage ?? window.localStorage).removeItem(DRAFT_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

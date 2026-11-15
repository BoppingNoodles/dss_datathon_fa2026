import type { RecommendationRequest, Tab } from "./types";

export const SESSION_STORAGE_KEY = "phoenix-session:v1";

export interface SavedSession {
  version: 1;
  request: RecommendationRequest;
  tab: Tab;
  done: string[];
  plan: { jobId: string; startDate: string; completed: string[] } | null;
}

type SessionStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const NEEDS = ["work", "housing", "food", "health_care", "transportation", "community_support"];
const LEVELS = ["no_diploma", "high_school_or_ged", "some_college", "associate", "bachelor", "graduate", "not_sure"];
const TABS = ["jobs", "housing", "services", "plan"];
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const strings = (value: unknown, max: number): value is string[] =>
  Array.isArray(value) && value.length <= max && value.every((item) => typeof item === "string" && item.length <= 1000);
const optionalNumber = (value: unknown, min: number, max: number) =>
  value === null || (typeof value === "number" && Number.isFinite(value) && value >= min && value <= max);

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
    && ["highest_pay", "nearest"].includes(String(value.job_sort))
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

export function makeSavedSession(request: RecommendationRequest, tab: Tab, done: string[], completed: string[], start: Date | null): SavedSession {
  const startDate = start && Number.isFinite(start.getTime())
    ? `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(start.getDate()).padStart(2, "0")}` : null;
  return {
    version: 1, request, tab, done: [...new Set(done)],
    plan: request.selected_job_id && startDate
      ? { jobId: request.selected_job_id, startDate, completed: [...new Set(completed)] } : null,
  };
}

export function readSavedSession(storage?: SessionStorage): { session: SavedSession | null; available: boolean } {
  try {
    const raw = (storage ?? window.localStorage).getItem(SESSION_STORAGE_KEY);
    if (!raw) return { session: null, available: true };
    const value: unknown = JSON.parse(raw);
    if (!record(value) || value.version !== 1 || !validRequest(value.request)
      || typeof value.tab !== "string" || !TABS.includes(value.tab) || !strings(value.done, 100)) {
      return { session: null, available: true };
    }
    const plan = value.plan;
    const validPlan = record(plan) && plan.jobId === value.request.selected_job_id
      && typeof plan.startDate === "string" && savedPlanDate(plan.startDate) && strings(plan.completed, 30);
    return {
      available: true,
      session: {
        version: 1, request: value.request, tab: value.tab as Tab, done: [...new Set(value.done)],
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
    (storage ?? window.localStorage).setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    return true;
  } catch {
    return false;
  }
}

export function clearSavedSession(storage?: SessionStorage): boolean {
  try {
    (storage ?? window.localStorage).removeItem(SESSION_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

export const DRAFT_STORAGE_KEY = "phoenix-onboarding:v1";

// Keep raw input, including incomplete numbers and an unfinished certificate name.
export interface OnboardingDraft {
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
  return {
    location: initial?.location ?? "", need: initial?.priority_need ?? null, age: initial?.age?.toString() ?? "",
    skills: initial?.experience.skills ?? [], expText: initial?.experience.text ?? "", years: initial?.experience.years?.toString() ?? "",
    noExp: initial?.experience.no_experience_yet ?? false, level: initial?.education.level ?? "",
    certs: initial?.education.credentials ?? [], otherCerts: "", noCerts: initial?.education.no_credentials ?? false,
  };
}

export function hasDraftAnswers(draft: OnboardingDraft): boolean {
  return Object.values(draft).some((value) => Array.isArray(value) ? value.length > 0 : value !== "" && value !== null && value !== false);
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

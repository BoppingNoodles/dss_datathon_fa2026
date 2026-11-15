import type { RecommendationRequest, RecommendationResponse } from "./types";

// Typed task/resource associations must be regenerated from the API, not replayed
// from the earlier cache that could link rental estimates to immediate housing.
export const RESULTS_CACHE_KEY = "phoenix-results:v2";
const CACHE_AGE_MS = 15 * 60 * 1000;
type CacheStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

function isResponse(value: unknown): value is RecommendationResponse {
  if (!record(value) || !["jobs", "housing", "services", "plan"].includes(String(value.open_tab))
    || typeof value.disclaimer !== "string" || !Array.isArray(value.next_steps)
    || !record(value.jobs) || !record(value.housing_areas) || !record(value.services) || !record(value.data_coverage)) return false;
  const groups = [...(Array.isArray(value.jobs.groups) ? value.jobs.groups : []),
    ...(Array.isArray(value.jobs.other_groups) ? value.jobs.other_groups : [])];
  return Array.isArray(value.jobs.groups) && groups.every((group) => record(group) && Array.isArray(group.items))
    && Array.isArray(value.housing_areas.areas) && Array.isArray(value.services.groups)
    && value.services.groups.every((group) => record(group) && Array.isArray(group.items))
    && Array.isArray(value.data_coverage.notes)
    && (value.thirty_day_plan === null || (record(value.thirty_day_plan)
      && typeof value.thirty_day_plan.target_job_id === "string" && Array.isArray(value.thirty_day_plan.steps)
      && Array.isArray(value.thirty_day_plan.credential_paths)));
}

// One response in this tab's session storage, separate from durable answers/progress.
// A cache hit still refreshes from the API; another profile can never reuse it.
export function readCachedResults(request: RecommendationRequest, storage?: CacheStorage, now = Date.now()): RecommendationResponse | null {
  try {
    const raw = (storage ?? window.sessionStorage).getItem(RESULTS_CACHE_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!record(value) || value.version !== 2 || value.request !== JSON.stringify(request)
      || typeof value.savedAt !== "number" || now < value.savedAt || now - value.savedAt > CACHE_AGE_MS
      || !isResponse(value.data)) return null;
    return value.data;
  } catch {
    return null;
  }
}

export function cacheResults(request: RecommendationRequest, data: RecommendationResponse, storage?: CacheStorage, now = Date.now()): boolean {
  try {
    const value = JSON.stringify({ version: 2, request: JSON.stringify(request), savedAt: now, data });
    if (value.length > 2_000_000) return false;
    (storage ?? window.sessionStorage).setItem(RESULTS_CACHE_KEY, value);
    return true;
  } catch {
    return false;
  }
}

export function clearCachedResults(storage?: CacheStorage): boolean {
  try {
    const target = storage ?? window.sessionStorage;
    target.removeItem(RESULTS_CACHE_KEY);
    target.removeItem("phoenix-results:v1");
    return true;
  } catch {
    return false;
  }
}

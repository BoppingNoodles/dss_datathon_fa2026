import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../lib/saved-session.ts", import.meta.url), "utf8");
const compilerOptions = { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext };
const reentryCode = ts.transpileModule(readFileSync(new URL("../lib/reentry.ts", import.meta.url), "utf8"), { compilerOptions }).outputText;
const reentryUrl = `data:text/javascript;base64,${Buffer.from(reentryCode).toString("base64")}`;
const { outputText } = ts.transpileModule(source.replace('"./reentry"', JSON.stringify(reentryUrl)), { compilerOptions });
const { SESSION_STORAGE_KEY, makeSavedSession, readSavedSession, savedPlanDate, writeSavedSession, hasNewerSavedHistory, clearSavedSession, DRAFT_STORAGE_KEY, onboardingDraft, hasDraftAnswers, readOnboardingDraft, writeOnboardingDraft, clearOnboardingDraft } =
  await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

test("damaged adaptive state is exposed for recovery and backed up before replacement", () => {
  const storage = memoryStorage();
  const damaged = { ...makeSavedSession(request, "jobs", [], [], null, 3), request: { ...request, phoenix_session: { schemaVersion: 99, tasks: [{ id: "completed-work", status: "completed" }] } } };
  const raw = JSON.stringify(damaged);
  storage.setItem(SESSION_STORAGE_KEY, raw);
  const loaded = readSavedSession(storage);
  assert.equal(loaded.session, null);
  assert.equal(loaded.recovery, raw);
  assert.equal(storage.getItem(SESSION_STORAGE_KEY), raw);
  assert.equal(writeSavedSession(makeSavedSession(request, "jobs", [], [], null, 3), storage), true);
  assert.equal(storage.getItem("phoenix-session:recovery"), raw);
  assert.equal(readSavedSession(storage).session.onboardingVersion, 3);
});

test("invalid legacy fields never silently discard an attached canonical profile", () => {
  const storage = memoryStorage();
  const raw = JSON.stringify({ ...makeSavedSession(request, "jobs", [], [], null, 3), request: { ...request, age: "damaged", profile: { profileId: "original-person" } } });
  storage.setItem(SESSION_STORAGE_KEY, raw);
  assert.equal(readSavedSession(storage).recovery, raw);
  assert.equal(storage.getItem(SESSION_STORAGE_KEY), raw);
  assert.equal(writeSavedSession(makeSavedSession(request, "jobs", [], [], null, 3), storage), true);
  assert.equal(storage.getItem("phoenix-session:recovery"), raw);
  assert.equal(readSavedSession(storage).session.onboardingVersion, 3);
});

function memoryStorage() {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
}

function canonical(events = []) {
  return { schemaVersion: 1, profile: { profileId: "fictional-refresh", location: { city: "Oakland", zipCode: null }, release: { status: "post_release", date: null }, housing: { status: "stable", temporaryHousingEndDate: null }, employment: { status: "unemployed", skills: [], preferredJobTypes: [], certifications: [] }, barriers: { hasGovernmentId: true, hasTransportation: true, hasPhoneAccess: true, hasInternetAccess: true }, supportNeeds: [], goals: [], upcomingAppointments: [] }, tasks: [], recommendations: [], selectedRecommendationIds: [], dismissedRecommendationIds: [], topJobIds: [], events, changes: [], warnings: [], schedule: Array.from({ length: 30 }, (_, i) => ({ action_id: `day-${i + 1}`, day: i + 1, title: "Review", action: "Review progress", task_ids: [] })) };
}

const request = {
  age: 34, location: "Oakland", priority_need: "work",
  experience: { skills: ["Driving"], text: "Deliveries", years: 2, no_experience_yet: false },
  education: { level: "high_school_or_ged", credentials: ["Class A CDL"], no_credentials: false },
  service_sort: "highly_rated", job_sort: "highest_pay", selected_job_id: "goal-job",
  qualification_answers: { "goal-job": { diploma: true, experience: false } },
};

test("saved plan estimates retain their sources and an older tab cannot erase newer history", () => {
  const storage = memoryStorage();
  const state = canonical([{ id: "task-finished", type: "task_status", payload: { taskId: "food", status: "completed" } }]);
  state.profile.finances = { monthlyTakeHomePay: 2000, monthlyHousingCost: 1200, monthlyFoodCost: 886.08, monthlyOtherCosts: 730.92, projection: { jobId: "job:fixture", housingId: "area:fixture", hoursPerWeek: 40, takeHomePercent: 80, estimatedFields: ["monthlyFoodCost", "monthlyOtherCosts"] } };
  const latest = makeSavedSession({ ...request, phoenix_session: state }, "finances", [], [], null, 3);
  assert.equal(writeSavedSession(latest, storage), true);
  assert.deepEqual(readSavedSession(storage).session.request.phoenix_session.profile.finances, state.profile.finances);
  const stale = structuredClone(latest);
  stale.request.phoenix_session.events = [];
  assert.equal(writeSavedSession(stale, storage), false);
  assert.equal(hasNewerSavedHistory(stale.request, storage), true);
  assert.equal(hasNewerSavedHistory(latest.request, storage), false);
  assert.deepEqual(readSavedSession(storage).session.request.phoenix_session.events, state.events);
  const changedTab = { ...latest, tab: "housing" };
  assert.equal(writeSavedSession(changedTab, storage), true);
  assert.equal(readSavedSession(storage).session.tab, "housing");
  const invalid = structuredClone(latest);
  invalid.request.phoenix_session.profile.finances.projection.hoursPerWeek = 90;
  storage.setItem(SESSION_STORAGE_KEY, JSON.stringify(invalid));
  assert.ok(readSavedSession(storage).recovery);
});

test("refresh restores submitted answers, qualification reports, goal, and completed days", () => {
  const storage = memoryStorage();
  const session = makeSavedSession(request, "plan", ["contact"], ["day-1", "day-8"], new Date(2026, 10, 14, 23));
  assert.equal(writeSavedSession(session, storage), true);
  const restored = readSavedSession(storage);
  assert.equal(restored.available, true);
  assert.deepEqual(restored.session, session);
  assert.equal(restored.session.request.qualification_answers["goal-job"].experience, false);
  assert.equal(restored.session.plan.startDate, "2026-11-14");
  const date = savedPlanDate(restored.session.plan.startDate);
  assert.deepEqual([date.getFullYear(), date.getMonth(), date.getDate()], [2026, 10, 14]);
});

test("optional reentry answers and completion survive refresh and draft restore", () => {
  const storage = memoryStorage();
  const profile = { ...request, reentry: { has_id: "unsure", release_status: "already_released" },
    reentry_completed_ids: ["reentry:confirm-identification"], reentry_start_date: "2026-11-14" };
  const session = makeSavedSession(profile, "jobs", [], [], null);
  writeSavedSession(session, storage);
  assert.deepEqual(readSavedSession(storage).session.request.reentry, profile.reentry);
  assert.deepEqual(readSavedSession(storage).session.request.reentry_completed_ids, profile.reentry_completed_ids);
  const draft = onboardingDraft(profile);
  assert.equal(draft.reentryEnabled, true);
  writeOnboardingDraft(draft, storage);
  assert.deepEqual(readOnboardingDraft(storage).draft.reentry, profile.reentry);
  assert.equal(hasDraftAnswers(onboardingDraft(null)), false);
});

test("new onboarding completion survives refresh while legacy sessions stay available for review", () => {
  const storage = memoryStorage();
  const legacy = makeSavedSession(request, "jobs", [], [], null);
  writeSavedSession(legacy, storage);
  assert.equal(readSavedSession(storage).session.onboardingVersion, undefined);
  const completed = makeSavedSession(request, "jobs", [], [], null, 2);
  writeSavedSession(completed, storage);
  assert.equal(readSavedSession(storage).session.onboardingVersion, 2);
  assert.deepEqual(readSavedSession(storage).session.request, request);
  const draft = { ...onboardingDraft(null), reentryEnabled: true, expUnsure: true, certsUnsure: true };
  writeOnboardingDraft(draft, storage);
  assert.deepEqual(readOnboardingDraft(storage).draft, draft);
  assert.equal(hasDraftAnswers({ ...onboardingDraft(null), reentryEnabled: true }), false);
});

test("progress from a different goal never applies to the saved target", () => {
  const storage = memoryStorage();
  const session = makeSavedSession(request, "plan", [], ["day-1"], new Date(2026, 10, 14));
  session.plan.jobId = "old-goal";
  writeSavedSession(session, storage);
  assert.equal(readSavedSession(storage).session.plan, null);
  assert.equal(readSavedSession(storage).session.request.selected_job_id, "goal-job");
  assert.equal(makeSavedSession({ ...request, selected_job_id: null }, "jobs", [], ["day-1"], new Date()).plan, null);
});

test("bad or incompatible stored data never breaks the page", () => {
  const storage = memoryStorage();
  const valid = makeSavedSession(request, "plan", [], [], new Date(2026, 10, 14));
  for (const invalid of ["{broken", "null", "[]", JSON.stringify({ ...valid, version: 2 }),
    JSON.stringify({ ...valid, request: { ...request, experience: null } }),
    JSON.stringify({ ...valid, request: { ...request, qualification_answers: { job: { item: "yes" } } } }),
    JSON.stringify({ ...valid, done: [null] })]) {
    storage.setItem(SESSION_STORAGE_KEY, invalid);
    assert.deepEqual(readSavedSession(storage), { session: null, available: true });
  }
  for (const invalid of ["2026-02-30", "2026-13-01", "not a date"]) assert.equal(savedPlanDate(invalid), null);
});

test("denied storage and full storage return a failure without losing in-memory work", () => {
  const denied = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("quota"); }, removeItem() { throw new Error("denied"); } };
  const session = makeSavedSession(request, "jobs", [], [], null);
  assert.deepEqual(readSavedSession(denied), { session: null, available: false });
  assert.equal(writeSavedSession(session, denied), false);
  assert.equal(clearSavedSession(denied), false);
  assert.equal(session.request.location, "Oakland");
});

test("clearing saved answers and progress keeps the theme preference", () => {
  const storage = memoryStorage();
  storage.setItem("phoenix-theme", "dark");
  writeSavedSession(makeSavedSession(request, "services", [], [], null), storage);
  assert.equal(clearSavedSession(storage), true);
  assert.equal(readSavedSession(storage).session, null);
  assert.equal(storage.getItem("phoenix-theme"), "dark");
});

test("onboarding drafts preserve incomplete input before it can be submitted", () => {
  const storage = memoryStorage();
  const draft = { ...onboardingDraft(null), location: "O", need: "work", age: "1", skills: ["Warehouse"],
    expText: "Learning inventory", years: "0", level: "high_school_or_ged", certs: ["CPR certification"], otherCerts: "Forklift, " };
  assert.equal(writeOnboardingDraft(draft, storage), true);
  assert.deepEqual(readOnboardingDraft(storage), { draft, available: true });
  assert.equal(readSavedSession(storage).session, null);
  assert.equal(hasDraftAnswers(onboardingDraft(null)), false);
});

test("an unfinished edit stays separate from the submitted profile and plan", () => {
  const storage = memoryStorage();
  const session = makeSavedSession(request, "plan", [], ["day-1"], new Date(2026, 10, 14));
  writeSavedSession(session, storage);
  const draft = { ...onboardingDraft(request), location: "Berkeley", noExp: true, noCerts: true };
  writeOnboardingDraft(draft, storage);
  assert.equal(readOnboardingDraft(storage).draft.location, "Berkeley");
  assert.deepEqual(readSavedSession(storage).session, session);
  assert.equal(clearOnboardingDraft(storage), true);
  assert.equal(readOnboardingDraft(storage).draft, null);
  assert.deepEqual(readSavedSession(storage).session, session);
});

test("support uncertainty and preset goals survive an unfinished onboarding refresh", () => {
  const storage = memoryStorage();
  for (const supportChoice of ["unsure", "none"]) {
    const draft = { ...onboardingDraft(null), supportNeeds: [], supportChoice, goals: "", goalsUnsure: true };
    assert.equal(writeOnboardingDraft(draft, storage), true);
    assert.deepEqual(readOnboardingDraft(storage).draft, draft);
  }
  const selected = { ...onboardingDraft(null), supportNeeds: ["housing", "transportation"], goals: "Arrange a place to stay\nArrange reliable transportation\nMy own goal " };
  writeOnboardingDraft(selected, storage);
  assert.deepEqual(readOnboardingDraft(storage).draft, selected);
});

test("empty drafts, damaged drafts, and denied storage are handled without losing the saved plan", () => {
  const storage = memoryStorage();
  writeOnboardingDraft({ ...onboardingDraft(null), noCerts: true }, storage);
  assert.equal(readOnboardingDraft(storage).draft.noCerts, true);
  writeOnboardingDraft(onboardingDraft(null), storage);
  assert.equal(readOnboardingDraft(storage).draft, null);
  for (const value of ["{broken", JSON.stringify({ version: 2 }), JSON.stringify({ version: 1, answers: { ...onboardingDraft(null), skills: null } })]) {
    storage.setItem(DRAFT_STORAGE_KEY, value);
    assert.deepEqual(readOnboardingDraft(storage), { draft: null, available: true });
  }
  const denied = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("quota"); }, removeItem() { throw new Error("denied"); } };
  assert.equal(readOnboardingDraft(denied).available, false);
  assert.equal(writeOnboardingDraft(onboardingDraft(request), denied), false);
});

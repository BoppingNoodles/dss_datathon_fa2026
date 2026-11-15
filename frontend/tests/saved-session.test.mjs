import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../lib/saved-session.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } });
const { SESSION_STORAGE_KEY, makeSavedSession, readSavedSession, savedPlanDate, writeSavedSession, clearSavedSession, DRAFT_STORAGE_KEY, onboardingDraft, hasDraftAnswers, readOnboardingDraft, writeOnboardingDraft, clearOnboardingDraft } =
  await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

function memoryStorage() {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
}

const request = {
  age: 34, location: "Oakland", priority_need: "work",
  experience: { skills: ["Driving"], text: "Deliveries", years: 2, no_experience_yet: false },
  education: { level: "high_school_or_ged", credentials: ["Class A CDL"], no_credentials: false },
  service_sort: "highly_rated", job_sort: "highest_pay", selected_job_id: "goal-job",
  qualification_answers: { "goal-job": { diploma: true, experience: false } },
};

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

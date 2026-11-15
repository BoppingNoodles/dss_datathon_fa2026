import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const { outputText } = ts.transpileModule(readFileSync(new URL("../lib/onboarding.ts", import.meta.url), "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
});
const { onboardingErrors, onboardingRequest, hasRequiredReentryAnswers } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const blank = { location: "", need: null, age: "", skills: [], expText: "", years: "", noExp: false, level: "", certs: [], otherCerts: "", noCerts: false, reentry: {} };
const ready = { ...blank, location: "Oakland", need: "work", skills: ["Warehouse"], years: "2", level: "high_school_or_ged", noCerts: true,
  reentry: { release_status: "already_released", has_immediate_housing: "yes", has_id: "yes", has_transportation: "yes", has_phone_access: "yes", has_required_appointment: "no", employment_goal: "find_work" } };

test("blank onboarding cannot generate a plan; every required group needs a response", () => {
  assert.deepEqual(Object.keys(onboardingErrors(blank)), ["release-status", "location", "need", "has_immediate_housing", "has_id", "has_transportation", "has_phone_access", "has_required_appointment", "employment-goal", "experience", "level", "certificates"]);
  assert.deepEqual(onboardingErrors(ready), {});
  for (const key of ["has_immediate_housing", "has_id", "has_transportation", "has_phone_access", "has_required_appointment"]) {
    assert.ok(onboardingErrors({ ...ready, reentry: { ...ready.reentry, [key]: null } })[key]);
  }
});

test("uncertainty and private appointment answers satisfy required onboarding without false claims", () => {
  const answers = { ...ready, skills: [], years: "", expUnsure: true, noCerts: false, certsUnsure: true, level: "not_sure",
    reentry: { ...ready.reentry, has_immediate_housing: "unsure", has_id: "unsure", has_transportation: "unsure", has_phone_access: "unsure", has_required_appointment: "prefer_not_to_say" } };
  assert.deepEqual(onboardingErrors(answers), {});
  const request = onboardingRequest(answers, null);
  assert.equal(request.experience.no_experience_yet, false);
  assert.equal(request.education.no_credentials, false);
  assert.equal(request.experience.years, null);
  assert.deepEqual(request.education.credentials, []);
  assert.equal(request.reentry.has_id, "unsure");
  assert.equal(hasRequiredReentryAnswers(request), true);
  const privateAnswers = { ...answers, reentry: { ...answers.reentry, release_status: "prefer_not_to_say", has_id: "prefer_not_to_say", employment_goal: "not_now" } };
  assert.deepEqual(onboardingErrors(privateAnswers), {});
  assert.equal(hasRequiredReentryAnswers(onboardingRequest(privateAnswers, null)), true);
});

test("a release date may stay unknown; supplied dates and experience years must be valid", () => {
  const preparing = { ...ready, reentry: { ...ready.reentry, release_status: "preparing_for_release", release_date: null } };
  assert.deepEqual(onboardingErrors(preparing), {});
  assert.ok(onboardingErrors({ ...preparing, reentry: { ...preparing.reentry, release_date: "2026-02-30" } })["release-date"]);
  for (const years of ["-1", "61", "unknown"]) assert.ok(onboardingErrors({ ...ready, years }).years);
});

test("known skills and presets reach the matcher; new priority replaces the old planner priority", () => {
  const answers = { ...ready, certs: ["Forklift certification"], otherCerts: "CPR certification, Forklift certification", noCerts: false,
    reentry: { ...ready.reentry, priority_need: "housing" } };
  const request = onboardingRequest(answers, null);
  assert.equal(request.reentry.priority_need, "work");
  assert.deepEqual(request.experience.skills, ["Warehouse"]);
  assert.equal(request.experience.years, 2);
  assert.deepEqual(request.education.credentials, ["Forklift certification", "CPR certification"]);
  assert.equal(request.age, null);
  assert.equal(hasRequiredReentryAnswers({ ...request, reentry: {} }), false);
  assert.equal(hasRequiredReentryAnswers({ ...request, reentry: null }), false);
  assert.equal(hasRequiredReentryAnswers({ ...request, reentry: { ...request.reentry, employment_goal: null } }), false);
});

test("reviewing onboarding keeps the existing goal; new location clears it", () => {
  const initial = { ...onboardingRequest(ready, null), selected_job_id: "fictional-goal", qualification_answers: { "fictional-goal": { forklift: true } } };
  const reviewed = onboardingRequest(ready, initial);
  assert.equal(reviewed.selected_job_id, "fictional-goal");
  assert.deepEqual(reviewed.qualification_answers, initial.qualification_answers);
  assert.equal(onboardingRequest({ ...ready, location: "Berkeley" }, initial).selected_job_id, undefined);
  assert.equal(onboardingRequest({ ...ready, noExp: true, skills: [], years: "" }, initial).qualification_answers, undefined);
});

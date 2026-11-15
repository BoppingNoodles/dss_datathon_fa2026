import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const options = { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext };
const compile = async (file) => import(`data:text/javascript;base64,${Buffer.from(ts.transpileModule(readFileSync(new URL(file, import.meta.url), "utf8"), { compilerOptions: options }).outputText).toString("base64")}`);
const { onboardingErrors, onboardingRequest, adoptSession } = await compile("../lib/onboarding.ts");
const { extractSituation, profileDifferences } = await compile("../lib/domain.ts");
const answers = { adaptive: true, location: "Oakland", need: "work", age: "", skills: ["Warehouse"], expText: "Inventory", years: "2", noExp: false,
  level: "high_school_or_ged", certs: [], otherCerts: "", noCerts: true, housingStatus: "temporary", housingEnd: "2026-11-20", housingBudget: "900",
  preferredJobs: ["Warehouse"], phone: "limited", internet: "no", supportNeeds: ["housing", "employment"], goals: "Find work\nKeep appointments",
  appointments: [{ id: "fictional-visit", label: "Appointment", date: "2026-11-18", location: null }],
  reentry: { release_status: "already_released", release_date: null, has_immediate_housing: "yes", has_id: "unsure", has_transportation: "no", has_phone_access: "unsure", has_required_appointment: "yes", employment_goal: "find_work" } };

test("four-step answers carry temporary housing, separate access, work interests, support and appointments", () => {
  assert.deepEqual(onboardingErrors(answers), {});
  const request = onboardingRequest(answers, null);
  assert.equal(request.profile.housing.temporaryHousingEndDate, "2026-11-20");
  assert.equal(request.profile.barriers.hasGovernmentId, null);
  assert.equal(request.profile.barriers.hasPhoneAccess, null);
  assert.equal(request.profile.barriers.hasInternetAccess, false);
  assert.equal(request.profile.barriers.communicationAccess, "limited");
  assert.deepEqual(request.profile.employment.preferredJobTypes, ["Warehouse"]);
  assert.deepEqual(request.profile.supportNeeds, ["housing", "employment"]);
  assert.equal(request.priority_need, "housing");
  assert.equal(request.profile.upcomingAppointments[0].date, "2026-11-18");
  assert.equal(onboardingErrors({ ...answers, phone: undefined }).phone.length > 0, true);
});

test("structured edits preserve profile ID and progress as preview inputs", () => {
  const initial = onboardingRequest(answers, null);
  initial.phoenix_session = { schemaVersion: 1, profile: initial.profile, tasks: [{ id: "done", status: "completed" }] };
  const next = onboardingRequest({ ...answers, housingStatus: "stable", housingEnd: "" }, initial);
  assert.equal(next.profile.profileId, initial.profile.profileId);
  assert.equal(next.profile.housing.temporaryHousingEndDate, null);
  assert.deepEqual(next.phoenix_session.tasks, [{ id: "done", status: "completed" }]);
  assert.deepEqual(profileDifferences(initial.profile, next.profile), ["Housing"]);
  assert.equal(initial.profile.housing.status, "temporary");
});

test("natural-language preview is conservative, pure, and never invents dates or credentials", () => {
  const original = onboardingRequest(answers, null).profile;
  const employed = extractSituation("I got a job", original);
  assert.equal(employed.profile.employment.status, "employed");
  assert.equal(original.employment.status, "unemployed");
  assert.deepEqual(employed.profile.upcomingAppointments, original.upcomingAppointments);
  for (const text of ["Maybe I got a job", "I haven't got a job", "I got a job but lost my job", "I have an appointment next Tuesday", "I earned a CDL"]) {
    assert.deepEqual(extractSituation(text, original).understood, [], text);
  }
});

test("accepting server state synchronizes form values and removes the preview event", () => {
  const initial = onboardingRequest(answers, null);
  const profile = extractSituation("I got a job", initial.profile).profile;
  const response = { phoenix_session: { profile, tasks: [{ id: "done", status: "completed" }] } };
  const accepted = adoptSession({ ...initial, user_event: { type: "profile_updated" } }, response);
  assert.equal(accepted.user_event, undefined);
  assert.equal(accepted.reentry.employment_goal, "keep_work");
  assert.equal(accepted.phoenix_session.tasks[0].status, "completed");
  assert.equal(initial.reentry.employment_goal, "find_work");
});

test("a confirmed rejected target clears the native calendar pointer while preserving the selected history", () => {
  const initial = { ...onboardingRequest(answers, null), selected_job_id: "old-target" };
  const response = { selected_job_id: null, phoenix_session: { profile: initial.profile, tasks: [{ id: "earlier-application", status: "completed" }], selectedRecommendationIds: ["job:old-target"] } };
  const accepted = adoptSession(initial, response);
  assert.equal(accepted.selected_job_id, null);
  assert.deepEqual(accepted.phoenix_session.selectedRecommendationIds, ["job:old-target"]);
  assert.equal(accepted.phoenix_session.tasks[0].status, "completed");
});

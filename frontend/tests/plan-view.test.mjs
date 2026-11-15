import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const compile = async file => import(`data:text/javascript;base64,${Buffer.from(ts.transpileModule(readFileSync(new URL(file, import.meta.url), "utf8"), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString("base64")}`);
const { quickProposal } = await compile("../lib/quick-update.ts");
const { extractSituation } = await compile("../lib/domain.ts");
const { readyTasks, circumstances, circumstanceChanges, comparePlans, resourceLabel, taskResourceLabel, taskGroups, taskResources, planTasks, stableTaskOrder, taskProgress, taskResult, rebaseSituation } = await compile("../lib/plan-view.ts");
const profile = {
  profileId: "fictional", location: { city: "Oakland", zipCode: null }, release: { status: "post_release", date: null },
  housing: { status: "temporary", temporaryHousingEndDate: "2026-12-01", monthlyBudget: 900 },
  employment: { status: "unemployed", preferredJobTypes: ["Warehouse"], experienceYears: 2, skills: ["Inventory"], experienceText: null, noExperienceYet: false, educationLevel: "high_school_or_ged", certifications: [], noCertifications: true },
  barriers: { hasGovernmentId: false, hasTransportation: false, hasPhoneAccess: true, hasInternetAccess: null, communicationAccess: "reliable" },
  supportNeeds: ["housing", "employment"], upcomingAppointments: [], appointmentStatus: "no", goals: [],
};
const task = (id, status = "not_started", priority = "high") => ({ id, title: id, status, priority, archived: false, prerequisiteTaskIds: [], notes: "" });
const resource = (id, mode) => ({ id, title: id, mode, active: true, userStatus: "selected", userReportedAvailability: null });
const session = { profile, tasks: [task("contact", "completed"), { ...task("apply"), prerequisiteTaskIds: ["contact"] }, task("blocked", "blocked")], recommendations: [resource("provider:1", "temporary_housing"), resource("job:1", "job"), resource("area:1", "long_term_area")], selectedRecommendationIds: ["provider:1", "job:1"], events: [{ id: "earlier" }] };
const values = { resourceId: "", taskId: "", endDate: "", appointmentId: "appointment-new", appointmentLabel: "", appointmentDate: "", appointmentLocation: "" };

test("quick housing and employment updates propose explicit outcomes without mutating saved state", () => {
  const before = structuredClone(session);
  const result = quickProposal("stable_housing", values, session);
  assert.equal(result.profile.housing.status, "stable");
  assert.equal(result.profile.housing.temporaryHousingEndDate, null);
  assert.equal(quickProposal("started_work", values, session).profile.employment.status, "employed");
  assert.equal(quickProposal("transport_gained", values, session).profile.barriers.hasTransportation, true);
  assert.equal(quickProposal("id_obtained", values, session).profile.barriers.hasGovernmentId, true);
  assert.deepEqual(session, before);
});

test("task completion and provider outcomes are events, never housing stability", () => {
  const completed = quickProposal("task_completed", { ...values, taskId: "apply" }, session);
  assert.deepEqual(completed.profile, profile);
  assert.deepEqual(completed.event, { type: "task_status", payload: { taskId: "apply", status: "completed" } });
  const unavailable = quickProposal("provider_unavailable", { ...values, resourceId: "provider:1" }, session);
  assert.equal(unavailable.event.type, "resource_unavailable");
  assert.equal(unavailable.profile.housing.status, "temporary");
  assert.throws(() => quickProposal("provider_unavailable", { ...values, resourceId: "area:1" }, session), /relevant opportunity/);
  assert.throws(() => quickProposal("application_rejected", { ...values, resourceId: "provider:1" }, session), /relevant opportunity/);
});

test("unknown dates stay unknown and quick updates validate required details", () => {
  assert.throws(() => quickProposal("housing_ending", values, session), /end date/);
  assert.equal(quickProposal("temporary_housing", values, session).profile.housing.temporaryHousingEndDate, null);
  const appointment = quickProposal("appointment", { ...values, appointmentLabel: "Provider visit" }, session).profile.upcomingAppointments[0];
  assert.equal(appointment.date, null);
  assert.equal(appointment.location, null);
  assert.equal(appointment.id, "appointment-new");
  assert.throws(() => quickProposal("appointment", values, session), /short appointment label/);
  assert.throws(() => quickProposal("task_completed", { ...values, taskId: "contact" }, session), /prerequisites/);
});

test("before-and-after comparison names additions, priorities, archives and preserved progress", () => {
  const before = structuredClone(session);
  before.tasks.push(task("old-search"));
  before.tasks[0].notes = "Keep this contact history";
  const after = structuredClone(before);
  after.profile.housing.status = "stable";
  after.tasks[1].priority = "critical";
  after.tasks.at(-1).archived = true;
  after.tasks.push(task("start-work"));
  after.recommendations[0].userReportedAvailability = "unavailable";
  after.recommendations.push(resource("provider:2", "temporary_housing"));
  const result = comparePlans(before, after);
  assert.deepEqual(result.added.map(t => t.id), ["start-work"]);
  assert.deepEqual(result.reprioritized.map(t => t.id), ["apply"]);
  assert.deepEqual(result.archived.map(t => t.id), ["old-search"]);
  assert.equal(result.retained[0].notes, "Keep this contact history");
  assert.deepEqual(result.unavailableResources.map(r => r.id), ["provider:1"]);
  assert.deepEqual(result.newResources.map(r => r.id), ["provider:2"]);
  assert.deepEqual(result.preservedSelections, before.selectedRecommendationIds);
  assert.deepEqual(circumstanceChanges(before.profile, after.profile).find(row => row.label === "Housing"), { label: "Housing", before: "Temporary", after: "Stable" });
  assert.equal(before.profile.housing.status, "temporary");
});

test("the dashboard uses planner order and keeps reported circumstances separate from progress", () => {
  assert.deepEqual(readyTasks(session).map(t => t.id), ["apply"]);
  assert.equal(circumstances(profile).find(row => row.label === "Housing").value, "Temporary");
  assert.equal(resourceLabel({ ...session.recommendations[2], resourceType: "rental_market" }), "Rental cost information");
  assert.equal(resourceLabel({ ...session.recommendations[0], resourceType: "housing_assistance" }), "Housing assistance");
  assert.equal(taskResourceLabel({ allowedResourceTypes: ["identification_assistance"] }, { resourceType: "workforce_training", supportedResourceTypes: ["workforce_training", "identification_assistance"] }), "ID assistance");
});

test("the task list counts remaining work and separates started, blocked, skipped and completed steps", () => {
  const state = { ...session, tasks: [task("low", "not_started", "low"), task("urgent", "not_started", "critical"), task("working-low", "in_progress", "low"), task("working-high", "in_progress", "high"), task("blocked", "blocked"), task("done", "completed"), task("skip", "skipped"), { ...task("old"), archived: true }] };
  const before = structuredClone(state);
  const groups = taskGroups(state);
  assert.equal(groups.left, 5);
  assert.deepEqual(groups.inProgress.map(t => t.id), ["working-high", "working-low"]);
  assert.deepEqual(groups.todo.map(t => t.id), ["urgent", "blocked", "low"]);
  assert.deepEqual(groups.completed.map(t => t.id), ["done"]);
  assert.deepEqual(groups.skipped.map(t => t.id), ["skip"]);
  assert.deepEqual(state, before);
  state.tasks.find(t => t.id === "urgent").status = "in_progress";
  assert.equal(taskGroups(state).inProgress[0].id, "urgent");
  assert.equal(taskGroups(state).left, 5);
});

test("priority order respects prerequisites and does not promote unrelated or unavailable resources", () => {
  const state = { ...session, tasks: [{ ...task("dependent", "not_started", "critical"), prerequisiteTaskIds: ["first"] }, task("free", "not_started", "critical"), task("first", "not_started", "low")], recommendations: [
    { ...resource("valid", "service"), resourceType: "public_transit" },
    { ...resource("wrong", "long_term_area"), resourceType: "rental_market" },
    { ...resource("unavailable", "service"), resourceType: "public_transit", userReportedAvailability: "unavailable" },
  ] };
  assert.deepEqual(taskGroups(state).todo.map(t => t.id), ["free", "first", "dependent"]);
  const step = { ...task("transport"), allowedResourceTypes: ["public_transit"], relatedRecommendationIds: ["valid", "wrong", "unavailable"] };
  assert.deepEqual(taskResources(step, state).map(r => r.id), ["valid"]);
});

test("one task list retains completed steps alongside unstarted and started work without duplicates", () => {
  const state = { ...session, tasks: [task("later", "not_started", "low"), task("working", "in_progress", "high"), task("done", "completed", "critical"), { ...task("archived-done", "completed"), archived: true }, { ...task("old"), archived: true }, task("skipped", "skipped", "low")] };
  const before = structuredClone(state);
  const result = planTasks(state);
  assert.deepEqual(result.map(t => t.id), ["done", "working", "archived-done", "later", "skipped"]);
  assert.equal(new Set(result.map(t => t.id)).size, result.length);
  assert.deepEqual(result.map(t => t.status), ["completed", "in_progress", "completed", "not_started", "skipped"]);
  assert.equal(taskGroups(state).left, 2);
  assert.deepEqual(state, before);
});

test("task actions retain row positions while new steps are appended", () => {
  const initial = [task("first", "not_started", "high"), task("second", "in_progress", "medium")];
  const order = initial.map(t => t.id);
  const updated = [task("new-follow-up", "not_started", "critical"), task("second", "in_progress", "high"), task("first", "completed", "low")];
  assert.deepEqual(stableTaskOrder(updated, order).map(t => t.id), ["first", "second", "new-follow-up"]);
  assert.equal(stableTaskOrder(updated, order)[0].status, "completed");
  assert.deepEqual(stableTaskOrder(updated.filter(t => t.id !== "first"), order).map(t => t.id), ["second", "new-follow-up"]);
});

test("progress follows completed actions, including reopening, without changing reported circumstances", () => {
  const state = { ...session, tasks: [task("done", "completed"), task("working", "in_progress"), task("blocked", "blocked"), task("skip", "skipped"), { ...task("old"), archived: true }] };
  assert.deepEqual(taskProgress(state), { completed: 1, skipped: 1, left: 2, total: 4, percent: 25 });
  state.tasks[1].status = "completed";
  assert.deepEqual(taskProgress(state), { completed: 2, skipped: 1, left: 1, total: 4, percent: 50 });
  state.tasks[0].status = "not_started";
  assert.equal(taskProgress(state).percent, 25);
  assert.equal(state.profile.housing.status, "temporary");
  assert.deepEqual(taskProgress({ ...state, tasks: [] }), { completed: 0, skipped: 0, left: 0, total: 0, percent: 0 });
});

test("a completion result is specific to its need and can confirm an older completed search", () => {
  assert.equal(taskResult({ id: "reentry:housing-now" }, { ...profile, housing: { status: "no_confirmed_housing" } }).recorded, false);
  assert.equal(taskResult({ id: "support:food" }, profile).outcome, "food_secured");
  assert.equal(taskResult({ id: "reentry:transportation" }, { ...profile, barriers: { hasTransportation: true } }).recorded, true);
  assert.equal(taskResult({ id: "contact:provider:1" }, profile), null);
  assert.equal(taskResult({ id: "reentry:job-review:one" }, profile), null);
});

test("change chat recognizes declared access and work while leaving applications and uncertain reports unclaimed", () => {
  const result = extractSituation("We now have food, transport, and housing", { ...profile, housing: { ...profile.housing, status: "no_confirmed_housing" } });
  assert.equal(result.profile.barriers.hasFoodAccess, true);
  assert.equal(result.profile.barriers.hasTransportation, true);
  assert.equal(result.profile.housing.status, "temporary");
  assert.equal(extractSituation("I have a job", profile).profile.employment.status, "employed");
  assert.equal(extractSituation("I started working", profile).profile.employment.status, "employed");
  for (const text of ["I have a job interview", "I got a food assistance application", "I got food poisoning", "Maybe I now have housing"]) {
    assert.equal(extractSituation(text, profile).understood.length, 0, text);
  }
});

test("refreshing a chat proposal preserves a need resolved while the preview was open", () => {
  const proposed = structuredClone(profile);
  proposed.employment.status = "employed";
  const current = structuredClone(profile);
  current.barriers.hasFoodAccess = true;
  current.barriers.hasTransportation = true;
  const result = rebaseSituation(profile, proposed, current);
  assert.equal(result.employment.status, "employed");
  assert.equal(result.barriers.hasFoodAccess, true);
  assert.equal(result.barriers.hasTransportation, true);
  assert.equal(profile.employment.status, "unemployed");
});

test("a compound change recognizes explicit work and transport but requires the housing date", () => {
  const result = extractSituation("I got a warehouse job, but my temporary housing ends next Friday and I still don’t have transportation", profile);
  assert.equal(result.profile.employment.status, "employed");
  assert.equal(result.profile.barriers.hasTransportation, false);
  assert.equal(result.profile.housing.temporaryHousingEndDate, null);
  assert.equal(result.requiresDateConfirmation, true);
  assert.equal(profile.employment.status, "unemployed");
  for (const text of ["I got a job offer", "I got a warehouse job interview", "I got a call for a job", "I got an interview for the job", "I got a letter about a job", "I got a new job application", "My friend got a job", "Maybe I got a job", "I haven't got a job"]) {
    assert.equal(extractSituation(text, profile).profile.employment.status, "unemployed", text);
  }
});

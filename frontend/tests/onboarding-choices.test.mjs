import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";
const compile = async file => import(`data:text/javascript;base64,${Buffer.from(ts.transpileModule(readFileSync(new URL(file, import.meta.url), "utf8"), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString("base64")}`);
const { GOAL_PRESETS, goalLines, ownGoals, replaceOwnGoals, toggleGoal } = await compile("../lib/onboarding-choices.ts");
const { onboardingRequest } = await compile("../lib/onboarding.ts");
const draft = { adaptive: true, location: "Oakland", need: "housing", age: "", skills: [], expText: "", years: "", noExp: true, level: "not_sure", certs: [], otherCerts: "", noCerts: true, housingStatus: "temporary", housingEnd: "", housingBudget: "", phone: "unsure", internet: "unsure", reentry: { release_status: "preparing_for_release", has_immediate_housing: "yes", has_id: "no", has_transportation: "no", has_phone_access: "unsure", has_required_appointment: "unsure", employment_goal: "find_work" } };

test("preset and personal goals share the existing string draft without losing spaces while typing", () => {
  let goals = toggleGoal("", GOAL_PRESETS[0], true);
  goals = toggleGoal(goals, GOAL_PRESETS[1], true);
  goals = replaceOwnGoals(goals, "Meet my support person ");
  assert.equal(ownGoals(goals), "Meet my support person ");
  goals = toggleGoal(goals, GOAL_PRESETS[0], false);
  assert.deepEqual(goalLines(goals), [GOAL_PRESETS[1], "Meet my support person"]);
  const request = onboardingRequest({ ...draft, goals, supportNeeds: ["housing", "transportation"] }, null);
  assert.deepEqual(request.profile.goals, [GOAL_PRESETS[1], "Meet my support person"]);
  assert.deepEqual(request.profile.supportNeeds, ["housing", "transportation"]);
  assert.equal(request.profile.housing.status, "temporary");
  assert.equal(request.profile.employment.status, "unemployed");
});

test("unknown or no additional support does not assert an outcome or invent a goal", () => {
  for (const supportChoice of ["unsure", "none"]) {
    const request = onboardingRequest({ ...draft, supportNeeds: [], supportChoice, goals: "", goalsUnsure: true }, null);
    assert.deepEqual(request.profile.supportNeeds, []);
    assert.deepEqual(request.profile.goals, []);
    assert.equal(request.profile.housing.status, "temporary");
    assert.equal(request.profile.barriers.hasTransportation, false);
    assert.equal(request.profile.appointmentStatus, "unsure");
  }
});

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const { outputText } = ts.transpileModule(readFileSync(new URL("../lib/reentry.ts", import.meta.url), "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
});
const { withReentryCompletion, validReentry } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const plan = {
  tasks: [
    { task_id: "appointment", title: "Check appointment", prerequisites: [], status: "todo" },
    { task_id: "travel", title: "Plan trip", prerequisites: ["appointment"], status: "waiting" },
    { task_id: "id", title: "Find ID help", prerequisites: [], status: "todo" },
  ],
  daily_actions: [{ action_id: "day1", task_ids: ["appointment", "id"] }, { action_id: "day2", task_ids: ["travel"] }, { action_id: "day3", task_ids: [] }],
  completed_ids: [], next_task_ids: ["appointment", "id"],
};

test("completion unlocks next steps and undo reopens all dependent progress", () => {
  const first = withReentryCompletion(plan, [], "appointment", true);
  assert.equal(first.tasks[1].status, "todo");
  const trip = withReentryCompletion(first, first.completed_ids, "travel", true);
  assert.ok(trip.completed_ids.includes("day2"));
  const undone = withReentryCompletion(trip, trip.completed_ids, "appointment", false);
  assert.equal(undone.tasks[1].status, "waiting");
  assert.ok(!undone.completed_ids.includes("day2"));
  assert.ok(!undone.completed_ids.includes("travel"));
  assert.deepEqual(plan.completed_ids, []);
});

test("calendar day marks its tasks and prevents completing blocked actions", () => {
  const invalid = withReentryCompletion(plan, [], "day2", true);
  assert.ok(!invalid.completed_ids.includes("travel"));
  const first = withReentryCompletion(plan, [], "day1", true);
  assert.ok(first.completed_ids.includes("appointment") && first.completed_ids.includes("id"));
  assert.ok(first.completed_ids.includes("day1"));
  assert.deepEqual(first.next_task_ids, ["travel"]);
  const review = withReentryCompletion(first, first.completed_ids, "day3", true);
  assert.ok(review.completed_ids.includes("day3"));
});

test("saved reentry answers reject unrequested fields and invalid options", () => {
  assert.equal(validReentry({ has_id: "unsure", has_required_appointment: "prefer_not_to_say" }), true);
  assert.equal(validReentry({ has_id: "maybe" }), false);
  assert.equal(validReentry({ case_number: "fictional" }), false);
  assert.equal(validReentry(null), false);
  assert.equal(validReentry({ release_date: "2026-02-30" }), false);
  assert.equal(validReentry({ constructor: "unexpected" }), false);
});

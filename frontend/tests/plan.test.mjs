import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

// Use the project's compiler so the tests also work on the supported Node 20.
const source = readFileSync(new URL("../lib/plan.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } });
const { addDays, buildDailyPlan, dateKey, monthCells } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

const base = { target_job_id: "fictional", target_job_title: "Warehouse associate", credential_paths: [], steps: [], notes: [] };

test("thirty distinct daily actions begin today and continue into the next year", () => {
  const start = new Date(2026, 11, 20);
  const days = buildDailyPlan(base, start);
  assert.equal(days.length, 30);
  assert.equal(dateKey(days[0].date), "2026-12-20");
  assert.equal(dateKey(days[29].date), "2027-01-18");
  assert.equal(new Set(days.map((day) => dateKey(day.date))).size, 30);
  assert.equal(new Set(days.map((day) => day.title)).size, 30);
  assert.ok(days[0].action.includes(base.target_job_title));
  assert.ok(days[29].action.includes(base.target_job_title));
});

test("calendar aligns weekdays and includes leap day", () => {
  const cells = monthCells(new Date(2028, 1, 1));
  assert.equal(cells.length % 7, 0);
  assert.equal(cells[0].getDay(), 0);
  assert.equal(cells.at(-1).getDay(), 6);
  assert.equal(cells.filter((day) => day.getMonth() === 1).length, 29);
  assert.equal(dateKey(addDays(new Date(2028, 1, 28), 1)), "2028-02-29");
});

test("date arithmetic remains consecutive across daylight-saving time", () => {
  const days = buildDailyPlan(base, new Date(2027, 2, 10));
  assert.equal(dateKey(days[29].date), "2027-04-08");
  assert.equal(new Set(days.map((day) => dateKey(day.date))).size, 30);
});

test("credential paths distinguish missing requirements from credentials already held", () => {
  const path = { credential: "Example credential", requirement_kind: "required", user_status: "not_confirmed", links: [] };
  const required = buildDailyPlan({ ...base, credential_paths: [path] }, new Date(2026, 10, 14));
  assert.ok(required[4].action.includes("Example credential"));
  assert.ok(required[9].action.includes("trainee route"));
  const held = buildDailyPlan({ ...base, credential_paths: [{ ...path, user_status: "reported_held" }] }, new Date(2026, 10, 14));
  assert.ok(held[4].action.includes("existing records"));
  assert.ok(!held[11].action.includes("Compare accepted options"));
});

test("daily resources exclude interim work and deduplicate shared source links", () => {
  const link = { url: "https://example.com/job", label: "Job posting", role: "job_posting" };
  const steps = [
    { day_start: 1, day_end: 30, track: "application", links: [link, link] },
    { day_start: 1, day_end: 30, track: "interim_work", links: [{ ...link, url: "https://example.com/interim" }] },
  ];
  const days = buildDailyPlan({ ...base, steps }, new Date(2026, 10, 14));
  assert.deepEqual(days[0].links, [link]);
  assert.ok(days.every((day) => !/interim/i.test(day.title + day.action)));
});

test("the calendar preserves personalized backend activities and stable task IDs", () => {
  const daily = Array.from({ length: 30 }, (_, i) => ({
    action_id: `target-job-${i + 1}`, day: i + 1, title: `Task ${i + 1}`,
    action: `Role-specific preparation ${i + 1}`, phase: "Get ready", links: [],
  })).reverse();
  const plan = { ...base, daily_actions: daily };
  const days = buildDailyPlan(plan, new Date(2026, 11, 20));
  assert.equal(days[0].id, "target-job-1");
  assert.equal(days[8].action, "Role-specific preparation 9");
  assert.equal(dateKey(days[29].date), "2027-01-18");
  assert.deepEqual(daily.map((day) => day.day), Array.from({ length: 30 }, (_, i) => 30 - i));
  assert.deepEqual(days.map((day) => day.id), buildDailyPlan(plan, new Date(2027, 0, 1)).map((day) => day.id));
});

test("an incomplete or duplicate backend schedule uses the complete legacy fallback", () => {
  const duplicate = Array.from({ length: 30 }, () => ({
    action_id: "same", day: 1, title: "Invalid", action: "Invalid", phase: "Invalid", links: [],
  }));
  for (const daily_actions of [duplicate, duplicate.slice(0, 3)]) {
    const days = buildDailyPlan({ ...base, daily_actions }, new Date(2026, 10, 14));
    assert.equal(days.length, 30);
    assert.equal(days[29].day, 30);
    assert.notEqual(days[0].action, "Invalid");
  }
});

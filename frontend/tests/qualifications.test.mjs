import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../lib/qualifications.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } });
const { matchLabel, qualificationProgress, withQualificationAnswer } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

const job = { job_id: "target", matches: ["warehouse"], matches_reported_role: true, qualification_checks: [
  { key: "diploma", field: "education", label: "High school diploma or GED", requirement_kind: "required", status: "reported_met" },
  { key: "cdl", field: "certification", label: "Class-A CDL", requirement_kind: "required", status: "needs_confirmation" },
  { key: "optional", field: "certification", label: "Optional credential", requirement_kind: "preferred", status: "preferred" },
] };
const section = { groups: [{ items: [job] }], other_groups: [{ items: [{ ...job, job_id: "another" }] }] };

test("checking listed mandatory qualifications raises the label and unchecking lowers it", () => {
  assert.equal(matchLabel(job), "Related experience");
  assert.deepEqual(qualificationProgress(job), { total: 3, reported: 1, required: 2, requiredMet: 1 });
  const checked = withQualificationAnswer(section, "target", "cdl", true);
  assert.equal(matchLabel(checked.groups[0].items[0]), "Clear match");
  assert.deepEqual(qualificationProgress(checked.groups[0].items[0]), { total: 3, reported: 2, required: 2, requiredMet: 2 });
  const unchecked = withQualificationAnswer(checked, "target", "diploma", false);
  assert.equal(matchLabel(unchecked.groups[0].items[0]), "Related experience");
  const neither = withQualificationAnswer(unchecked, "target", "cdl", false);
  assert.equal(matchLabel(neither.groups[0].items[0]), "Needs preparation");
  assert.equal(matchLabel(job), "Related experience"); // original response stays immutable
  assert.equal(matchLabel(checked.other_groups[0].items[0]), "Related experience");
});

test("preferred qualifications do not block a clear match", () => {
  const checked = withQualificationAnswer(section, "target", "cdl", true);
  const optional = withQualificationAnswer(checked, "target", "optional", false);
  assert.equal(matchLabel(optional.groups[0].items[0]), "Clear match");
});

test("missing requirements cannot create a clear match", () => {
  assert.equal(matchLabel({ ...job, qualification_checks: [] }), "Related experience");
  assert.equal(matchLabel({ matches: [], matches_reported_role: null }), "Not assessed");
  assert.equal(matchLabel({ matches: [], matches_reported_role: false }), "Different work area");
});

test("skipped qualifications alone do not imply preparation is missing", () => {
  const unknown = { ...job, qualification_checks: job.qualification_checks.map(check => ({ ...check, status: "needs_confirmation" })) };
  assert.equal(matchLabel(unknown), "Related experience");
});

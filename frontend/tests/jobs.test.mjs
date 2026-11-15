import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const compile = text => ts.transpileModule(text, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const moduleUrl = source => `data:text/javascript;base64,${Buffer.from(compile(source)).toString("base64")}`;
const api = moduleUrl(readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8"));
const source = readFileSync(new URL("../lib/jobs.ts", import.meta.url), "utf8").replace('"./api"', JSON.stringify(api));
const { payText } = await import(moduleUrl(source));

test("job headlines use consistent English pay units and preserve range precision", () => {
  assert.equal(payText({ min: 25, max: 25, period: "hour", raw_text: "$25 por hora" }), "$25 / hr");
  assert.equal(payText({ min: 1500, max: 1800, period: "month", raw_text: "$1,500–$1,800 por mes" }), "$1,500–$1,800 / mo");
  assert.equal(payText({ min: 33.57, max: 37.30, period: "hour" }), "$33.57–$37.30 / hr");
});

test("unconfirmed, missing and foreign pay never become fabricated U.S. earnings", () => {
  assert.equal(payText({ min: 25, period: "hour", needs_confirmation: true }), "Pay needs confirmation");
  assert.equal(payText({ min: null, max: null, period: null }), "Pay not listed");
  assert.equal(payText({ min: 25, period: "hour", currency: "CAD", raw_text: "C$25/hour" }), "C$25/hour");
  assert.equal(payText({ min: null, max: null, period: null, raw_text: "Negotiable" }), "Negotiable");
});

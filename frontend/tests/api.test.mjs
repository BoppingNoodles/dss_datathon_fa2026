import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { getRecommendations } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

test("a plan request sends the submitted answers and returns the API response", async context => {
  const answers = { location: "Oakland", priority_need: "housing" };
  const expected = { phoenix_session: { profile: { profileId: "fictional-api" } } };
  context.mock.method(globalThis, "fetch", async (url, options) => {
    assert.ok(url.endsWith("/recommendations"));
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), answers);
    assert.ok(options.signal instanceof AbortSignal);
    return { ok: true, json: async () => expected };
  });
  assert.deepEqual(await getRecommendations(answers), expected);
});

test("API validation errors give actionable text instead of discarding the saved plan", async context => {
  context.mock.method(globalThis, "fetch", async () => ({ ok: false, status: 422, json: async () => ({ detail: [{ msg: "Enter a valid city" }] }) }));
  await assert.rejects(getRecommendations({}), /Please check your answers: Enter a valid city/);
  context.mock.method(globalThis, "fetch", async () => { throw new TypeError("Load failed"); });
  await assert.rejects(getRecommendations({}), /Couldn’t connect to Phoenix.*Try again/);
});

test("a stalled request ends with a retry message and releases its timer", async context => {
  let expire;
  let cleared = false;
  context.mock.method(globalThis, "setTimeout", callback => { expire = callback; return 42; });
  context.mock.method(globalThis, "clearTimeout", timer => { assert.equal(timer, 42); cleared = true; });
  context.mock.method(globalThis, "fetch", (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    expire();
  }));
  await assert.rejects(getRecommendations({}), /taking longer than expected.*Try again/);
  assert.equal(cleared, true);
});

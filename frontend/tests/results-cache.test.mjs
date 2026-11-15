import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../lib/results-cache.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } });
const { RESULTS_CACHE_KEY, cacheResults, readCachedResults, clearCachedResults } =
  await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const response = { ...JSON.parse(readFileSync(new URL("../lib/sample-response.json", import.meta.url), "utf8")), thirty_day_plan: null };
const request = { location: "Oakland", priority_need: "work", qualification_answers: { job: { diploma: true } } };

function memoryStorage() {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
}

test("refresh can display the recent response for the exact saved answers", () => {
  const storage = memoryStorage();
  assert.equal(cacheResults(request, response, storage, 1000), true);
  assert.deepEqual(readCachedResults(request, storage, 2000), response);
  assert.equal(readCachedResults({ ...request, location: "Berkeley" }, storage, 2000), null);
  assert.equal(readCachedResults({ ...request, qualification_answers: { job: { diploma: false } } }, storage, 2000), null);
});

test("expired, incompatible, and malformed results are fetched again", () => {
  const storage = memoryStorage();
  cacheResults(request, response, storage, 1000);
  assert.equal(readCachedResults(request, storage, 1000 + 16 * 60 * 1000), null);
  assert.equal(readCachedResults(request, storage, 999), null);
  for (const value of ["{broken", JSON.stringify({ version: 2 }), JSON.stringify({ version: 1, savedAt: 1000, request: JSON.stringify(request), data: {} })]) {
    storage.setItem(RESULTS_CACHE_KEY, value);
    assert.equal(readCachedResults(request, storage, 2000), null);
  }
});

test("cache failures do not block live results and clearing removes the snapshot", () => {
  const storage = memoryStorage();
  cacheResults(request, response, storage, 1000);
  assert.equal(clearCachedResults(storage), true);
  assert.equal(readCachedResults(request, storage, 2000), null);
  const denied = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("quota"); }, removeItem() { throw new Error("denied"); } };
  assert.equal(cacheResults(request, response, denied), false);
  assert.equal(readCachedResults(request, denied), null);
});

test("legacy task-resource associations cannot reappear from an earlier cached response", () => {
  const storage = memoryStorage();
  storage.setItem("phoenix-results:v1", JSON.stringify({ version: 1, savedAt: 1000, request: JSON.stringify(request), data: response }));
  assert.equal(readCachedResults(request, storage, 2000), null);
  cacheResults(request, response, storage, 1000);
  assert.deepEqual(readCachedResults(request, storage, 2000), response);
  clearCachedResults(storage);
  assert.equal(storage.getItem("phoenix-results:v1"), null);
});

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";
const compile = async file => import(`data:text/javascript;base64,${Buffer.from(ts.transpileModule(readFileSync(new URL(file, import.meta.url), "utf8"), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString("base64")}`);
const { assessFinances, parseFinances, EMPTY_FINANCES, initialFinanceProjection, projectedFinances, selectedBudgetOptions, monthlyJobIncome, monthlyHousingEstimate, US_COST_BASELINE } = await compile("../lib/finances.ts");
const { onboardingRequest } = await compile("../lib/onboarding.ts");
const values = (income, rent, food, other) => ({ monthlyTakeHomePay: income, monthlyHousingCost: rent, monthlyFoodCost: food, monthlyOtherCosts: other });

test("the budget distinguishes unknown amounts, zero income, housing pressure and a cash deficit", () => {
  assert.equal(assessFinances(EMPTY_FINANCES).remaining, null);
  assert.equal(assessFinances(values(3000, 800, 300, 300)).status, "within_budget");
  assert.equal(assessFinances(values(3000, 1000, 300, 300)).status, "high_housing");
  assert.equal(assessFinances(values(2000, 1400, 300, 200)).status, "tight");
  assert.equal(assessFinances(values(1000, 800, 250, 200)).remaining, -250);
  assert.equal(assessFinances(values(0, 500, 0, 0)).status, "deficit");
  assert.equal(assessFinances(values(10.01, 4.10, 2.20, 3.30)).remaining, 0.41);
  assert.equal(assessFinances(values(3000, 900, 1000, 500)).housingHigh, false);
  assert.equal(assessFinances(values(3000, 900, 1000, 500)).status, "tight");
});

test("financial inputs keep unknowns and zero distinct and reject malformed money", () => {
  assert.deepEqual(parseFinances(values("", "0", "100.25", "")), values(null, 0, 100.25, null));
  for (const raw of ["-1", "NaN", "Infinity", "0.001", "1000001"]) assert.throws(() => parseFinances(values(raw, "0", "0", "0")), /amount/);
});

test("editing the current situation preserves an existing financial budget", () => {
  const finances = values(3000, 800, 300, 300);
  const initial = { profile: { profileId: "fictional-finances", finances }, experience: {}, education: {}, location: "Oakland", reentry: {} };
  const draft = { adaptive: true, location: "Oakland", need: "work", noExp: true, expUnsure: false, skills: [], expText: "", years: "", level: "not_sure", noCerts: true, certs: [], otherCerts: "", housingStatus: "stable", phone: "yes", internet: "yes", reentry: { release_status: "already_released", has_required_appointment: "unsure", employment_goal: "find_work" } };
  const result = onboardingRequest(draft, initial);
  assert.deepEqual(result.profile.finances, finances);
  assert.notEqual(result.profile.finances, finances);
});

const job = (id, pay) => ({ id, title: id, mode: "job", resourceType: "job_posting", category: "job", active: true, userStatus: "selected", details: { jobId: id.replace("job:", ""), pay } });
const area = (id, details) => ({ id, title: id, mode: "long_term_area", resourceType: "rental_market", category: "housing", active: true, userStatus: "selected", details });
function fixture(recommendations, finances) {
  return { profile: { finances }, recommendations, selectedRecommendationIds: recommendations.map(resource => resource.id) };
}

test("a plan budget uses one selected job at its lower pay bound and the selected area's rent", () => {
  const state = fixture([job("job:first", { min: 20, max: 30, period: "hour", currency: "USD" }), job("job:other", { min: 50, max: 60, period: "hour" }), area("area:chosen", { medianMonthlyRent: 1800, rentP25: 1400, rentP75: 2400 })]);
  const projection = initialFinanceProjection(state, "first");
  const result = projectedFinances(state, projection);
  assert.equal(projection.jobId, "job:first");
  assert.equal(projection.hoursPerWeek, 40);
  assert.equal(result.monthlyTakeHomePay, 2773.33);
  assert.equal(result.monthlyHousingCost, 1800);
  assert.equal(result.monthlyFoodCost, US_COST_BASELINE.monthlyFood);
  assert.equal(result.monthlyOtherCosts, US_COST_BASELINE.monthlyOther);
  assert.equal(assessFinances(result).status, "deficit");
  assert.equal(state.profile.finances, undefined);
  state.recommendations[1].userStatus = "dismissed";
  assert.deepEqual(selectedBudgetOptions(state).jobs.map(resource => resource.id), ["job:first"]);
});

test("pay conversion honors the pay period and labeled schedule/deduction assumptions", () => {
  assert.equal(monthlyJobIncome(job("a", { min: 60000, period: "year" }), 20, 80).takeHome, 4000);
  assert.equal(monthlyJobIncome(job("a", { min: 3000, period: "month" }), 20, 90).takeHome, 2700);
  assert.equal(monthlyJobIncome(job("a", { min: 600, period: "week" })).takeHome, 2080);
  assert.equal(monthlyJobIncome(job("a", { min: 160, period: "day" }), 20).takeHome, 1386.67);
  const stated = fixture([job("job:part-time", { min: 20, period: "hour", hours_basis: "stated", hours_per_week: 20 })]);
  const projection = initialFinanceProjection(stated);
  assert.equal(projection.hoursPerWeek, 20);
  assert.equal(projectedFinances(stated, projection).monthlyTakeHomePay, 1386.67);
  for (const pay of [{ min: 20, period: null }, { min: 20, period: "hour", currency: "EUR" }, { min: null, max: null, period: "year" }]) assert.equal(monthlyJobIncome(job("a", pay)).takeHome, null);
});

test("housing providers with unknown costs stay unknown and ranges are honest estimates", () => {
  assert.equal(monthlyHousingEstimate(area("a", { rentP25: 1400, rentP75: 2000 })).amount, 1700);
  const provider = { ...area("provider:help", {}), resourceType: "housing_assistance", mode: "temporary_housing" };
  assert.equal(monthlyHousingEstimate(provider).amount, null);
  assert.match(monthlyHousingEstimate(provider).note, /not assumed free/);
  const state = fixture([job("job:a", { min: 20, period: "hour" }), provider]);
  assert.equal(assessFinances(projectedFinances(state, initialFinanceProjection(state))).status, "incomplete");
});

test("actual overrides survive refresh while different selections receive new estimates", () => {
  const state = fixture([job("job:old", { min: 20, period: "hour" }), job("job:new", { min: 30, period: "hour" }), area("area:old", { medianMonthlyRent: 1500 })]);
  const projection = initialFinanceProjection(state, "old");
  state.profile.finances = { ...values(2500, 1200, 300, 200), projection: { ...projection, estimatedFields: ["monthlyOtherCosts"] } };
  assert.equal(projectedFinances(state, initialFinanceProjection(state, "old")).monthlyTakeHomePay, 2500);
  assert.equal(projectedFinances(state, initialFinanceProjection(state, "new")).monthlyTakeHomePay, 4160);
  assert.equal(projectedFinances(state, initialFinanceProjection(state, "new")).monthlyFoodCost, 300);
  const removed = { ...state, recommendations: [], selectedRecommendationIds: [] };
  assert.equal(projectedFinances(removed, initialFinanceProjection(removed)).monthlyTakeHomePay, null);
  assert.equal(US_COST_BASELINE.monthlyFood, Math.round(10633 / 12 * 100) / 100);
  assert.equal(US_COST_BASELINE.monthlyOther, Math.round((4931 + 844 + 2010 + 986) / 12 * 100) / 100);
});

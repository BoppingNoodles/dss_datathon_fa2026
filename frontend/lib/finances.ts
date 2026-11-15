import type { FinanceField, FinanceProjection, Finances, PhoenixSession, Recommendation } from "./domain";

export const EMPTY_FINANCES: Finances = { monthlyTakeHomePay: null, monthlyHousingCost: null, monthlyFoodCost: null, monthlyOtherCosts: null };
export const FINANCE_FIELDS: [FinanceField, string][] = [["monthlyTakeHomePay", "Monthly take-home pay / income"], ["monthlyHousingCost", "Monthly housing cost"], ["monthlyFoodCost", "Monthly food cost"], ["monthlyOtherCosts", "Other monthly costs and goods"]];
// BLS Consumer Expenditures 2025, released October 29, 2026. These are
// household (consumer-unit) averages, not a minimum or a one-person budget.
export const US_COST_BASELINE = {
  year: 2025,
  source: "https://www.bls.gov/news.release/cesan.nr0.htm",
  monthlyFood: 886.08, // $10,633 / 12, food at home and away from home.
  monthlyOther: 730.92, // ($4,931 utilities + $844 supplies + $2,010 apparel + $986 personal care) / 12.
};
export function parseFinances(values: Record<FinanceField, string>): Finances {
  return Object.fromEntries(FINANCE_FIELDS.map(([key, label]) => {
    const raw = values[key].trim();
    if (!raw) return [key, null];
    if (!/^\d+(?:\.\d{0,2})?$/.test(raw) || Number(raw) > 1000000) throw new Error(`${label}: enter a non-negative amount in dollars and cents.`);
    return [key, Number(raw)];
  })) as unknown as Finances;
}

const amount = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
const cents = (value: number) => Math.round(value * 100) / 100;

export function selectedBudgetOptions(session: PhoenixSession) {
  const selected = session.selectedRecommendationIds.flatMap(id => session.recommendations.filter(resource => resource.id === id && resource.active && !["dismissed", "rejected"].includes(resource.userStatus) && resource.userReportedAvailability !== "unavailable"));
  return { jobs: selected.filter(resource => resource.resourceType === "job_posting" || resource.mode === "job"), housing: selected.filter(resource => resource.category === "housing") };
}

export function monthlyJobIncome(job: Recommendation | undefined, hoursPerWeek = 40, takeHomePercent = 80) {
  const pay = job?.details.pay as Record<string, unknown> | undefined;
  if (!pay || (pay.currency != null && pay.currency !== "USD") || hoursPerWeek <= 0 || hoursPerWeek > 80 || takeHomePercent <= 0 || takeHomePercent > 100) return { gross: null, takeHome: null, hours: hoursPerWeek, assumedHours: false, note: "Pay is not available in U.S. dollars. Enter an amount when known." };
  const low = amount(pay.min), high = amount(pay.max);
  if (low == null && high == null) return { gross: null, takeHome: null, hours: hoursPerWeek, assumedHours: false, note: "No usable pay amount is listed. Enter an amount when known." };
  const rate = low ?? high!;
  const statedHours = pay.hours_basis === "stated" ? amount(pay.hours_per_week) : null;
  const hours = hoursPerWeek;
  const weekly = pay.period === "hour" ? rate * hours : pay.period === "day" ? rate * hours / 8 : pay.period === "week" ? rate : null;
  const gross = pay.period === "year" ? rate / 12 : pay.period === "month" ? rate : weekly == null ? null : weekly * 52 / 12;
  if (gross == null || gross > 1000000) return { gross: null, takeHome: null, hours, assumedHours: false, note: "The pay period is unknown. Enter monthly income when known." };
  const schedule = pay.period === "hour" || pay.period === "day" ? `${hours} hours/week${statedHours === hours ? " listed in the posting" : " assumed"}${pay.period === "day" ? ", 8-hour workdays assumed" : ""}; 52 weeks/year. ` : "";
  return { gross: cents(gross), takeHome: cents(gross * takeHomePercent / 100), hours, assumedHours: statedHours !== hours && !!schedule, note: `${low == null ? "Only the advertised upper amount is available" : high != null && high !== low ? "Uses the low end of advertised pay" : "Uses advertised pay"}. ${schedule}${takeHomePercent}% kept after estimated deductions; adjust to your actual pay.` };
}

export function monthlyHousingEstimate(housing: Recommendation | undefined) {
  if (!housing) return { amount: null, note: "Select housing in Resources or enter a monthly cost." };
  const value = amount(housing.details.monthlyCost) ?? amount(housing.details.monthlyRent) ?? amount(housing.details.medianMonthlyRent);
  if (value != null) return { amount: cents(value), note: housing.resourceType === "rental_market" ? "Uses the area’s median monthly rent. This is an area estimate; confirm the actual rent and fees." : "Uses the listed monthly cost. Confirm fees and any assistance." };
  const low = amount(housing.details.rentP25), high = amount(housing.details.rentP75);
  if (low != null && high != null) return { amount: cents((low + high) / 2), note: "Uses the midpoint of this area’s rent range. Confirm the actual rent and fees." };
  return { amount: null, note: "This housing provider does not list a rent. Enter the cost after confirming it; assistance is not assumed free." };
}

export function initialFinanceProjection(session: PhoenixSession, preferredJobId?: string | null): FinanceProjection {
  const options = selectedBudgetOptions(session), saved = session.profile.finances?.projection;
  const job = options.jobs.find(resource => resource.id === preferredJobId || resource.details.jobId === preferredJobId)
    ?? options.jobs.find(resource => resource.id === saved?.jobId) ?? options.jobs.at(-1);
  const housing = options.housing.find(resource => resource.id === saved?.housingId) ?? options.housing.at(-1);
  const pay = job?.details.pay as Record<string, unknown> | undefined;
  const statedHours = pay?.hours_basis === "stated" ? amount(pay.hours_per_week) : null;
  const finances = session.profile.finances;
  const estimatedFields = FINANCE_FIELDS.flatMap(([key]) => {
    const changed = key === "monthlyTakeHomePay" ? saved?.jobId !== (job?.id ?? null) : key === "monthlyHousingCost" ? saved?.housingId !== (housing?.id ?? null) : false;
    if (saved && !changed) return saved.estimatedFields.includes(key) ? [key] : [];
    return (key === "monthlyTakeHomePay" ? !!job : key === "monthlyHousingCost" ? !!housing : finances?.[key] == null) ? [key] : [];
  });
  return { jobId: job?.id ?? null, housingId: housing?.id ?? null, hoursPerWeek: saved && saved.jobId === job?.id ? saved.hoursPerWeek : statedHours && statedHours <= 80 ? statedHours : 40, takeHomePercent: saved?.takeHomePercent ?? 80, estimatedFields };
}

export function projectedFinances(session: PhoenixSession, projection: FinanceProjection): Finances {
  const options = selectedBudgetOptions(session);
  const job = options.jobs.find(resource => resource.id === projection.jobId), housing = options.housing.find(resource => resource.id === projection.housingId);
  const saved = session.profile.finances ?? EMPTY_FINANCES;
  const income = monthlyJobIncome(job, projection.hoursPerWeek, projection.takeHomePercent);
  const rent = monthlyHousingEstimate(housing);
  const defaults: Finances = {
    monthlyTakeHomePay: job ? income.takeHome : saved.projection?.jobId ? null : saved.monthlyTakeHomePay,
    monthlyHousingCost: housing ? rent.amount : saved.projection?.housingId ? null : saved.monthlyHousingCost,
    monthlyFoodCost: saved.monthlyFoodCost ?? US_COST_BASELINE.monthlyFood,
    monthlyOtherCosts: saved.monthlyOtherCosts ?? US_COST_BASELINE.monthlyOther,
  };
  // Actual/user-entered overrides remain until the corresponding option changes.
  if (saved.projection) for (const [key] of FINANCE_FIELDS) {
    const sameOption = key === "monthlyTakeHomePay" ? saved.projection.jobId === projection.jobId : key === "monthlyHousingCost" ? saved.projection.housingId === projection.housingId : true;
    if (sameOption && !saved.projection.estimatedFields.includes(key)) defaults[key] = saved[key];
  }
  return defaults;
}
export function assessFinances(finances: Finances) {
  const missing = FINANCE_FIELDS.filter(([key]) => finances[key] == null).map(([, label]) => label);
  const income = finances.monthlyTakeHomePay == null ? null : Math.round(finances.monthlyTakeHomePay * 100);
  const housing = finances.monthlyHousingCost == null ? null : Math.round(finances.monthlyHousingCost * 100);
  const housingHigh = income != null && housing != null && housing > 0 && (income === 0 || housing * 100 > income * 30);
  const costs = missing.length ? null : Math.round(finances.monthlyHousingCost! * 100) + Math.round(finances.monthlyFoodCost! * 100) + Math.round(finances.monthlyOtherCosts! * 100);
  const remaining = costs == null ? null : (income! - costs) / 100;
  const spendingHigh = costs != null && costs * 100 >= income! * 80;
  const status = missing.length ? "incomplete" : remaining! < 0 ? "deficit" : spendingHigh ? "tight" : housingHigh ? "high_housing" : "within_budget";
  return { status, missing, housingHigh, spendingHigh, totalCosts: costs == null ? null : costs / 100, remaining, housingShare: income && housing != null ? housing / income : null };
}

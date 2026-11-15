"use client";

import { useEffect, useRef, useState } from "react";
import type { FinanceField, FinanceProjection, Finances, PhoenixSession, ReentryProfile } from "@/lib/domain";
import { assessFinances, FINANCE_FIELDS, initialFinanceProjection, monthlyHousingEstimate, monthlyJobIncome, parseFinances, projectedFinances, selectedBudgetOptions, US_COST_BASELINE } from "@/lib/finances";
import { money } from "@/lib/api";
import { resourceLabel } from "@/lib/plan-view";
import type { RecommendationResponse } from "@/lib/types";
import PlanPreview from "./PlanPreview";
import PhoenixThinking from "./PhoenixThinking";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";

const INPUT_LABELS: Record<FinanceField, string> = { monthlyTakeHomePay: "Income", monthlyHousingCost: "Housing", monthlyFoodCost: "Food", monthlyOtherCosts: "Other essentials" };
const asInputs = (value: Finances) => Object.fromEntries(FINANCE_FIELDS.map(([key]) => [key, value[key]?.toString() ?? ""])) as Record<FinanceField, string>;
type Props = {
  session: PhoenixSession; disabled: boolean; preferredJobId?: string | null;
  onPreview: (profile: ReentryProfile) => Promise<RecommendationResponse>;
  onConfirm: (response: RecommendationResponse) => void; onOpenResource: (id: string) => void;
};

export default function FinancesTab(props: Props) {
  const options = selectedBudgetOptions(props.session);
  const version = JSON.stringify([props.session.profile.finances, props.preferredJobId, [...options.jobs, ...options.housing].map(resource => [resource.id, resource.details.pay, resource.details.medianMonthlyRent, resource.details.rentP25, resource.details.rentP75, resource.details.monthlyCost, resource.details.monthlyRent])]);
  return <FinancePlanner key={version} {...props} />;
}

function FinancePlanner({ session, disabled, preferredJobId, onPreview, onConfirm, onOpenResource }: Props) {
  const [projection, setProjection] = useState(() => initialFinanceProjection(session, preferredJobId));
  const [values, setValues] = useState(() => asInputs(projectedFinances(session, initialFinanceProjection(session, preferredJobId))));
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [preview, setPreview] = useState<RecommendationResponse | null>(null);
  const [base, setBase] = useState<PhoenixSession | null>(null);
  const options = selectedBudgetOptions(session);
  const job = options.jobs.find(resource => resource.id === projection.jobId);
  const housing = options.housing.find(resource => resource.id === projection.housingId);
  const pay = monthlyJobIncome(job, projection.hoursPerWeek, projection.takeHomePercent);
  const rent = monthlyHousingEstimate(housing);
  const operation = useRef(0);
  useEffect(() => () => { ++operation.current; }, []);
  let finances: Finances | null = null;
  try { finances = parseFinances(values); } catch { /* Review displays the field error. */ }
  const budget = finances ? assessFinances(finances) : null;
  const estimate = (value: number | null | undefined) => value == null ? "—" : money(value);
  const working = preview?.phoenix_session ?? session;
  const financialTasks = working.tasks.filter(task => task.id.startsWith("finances:") && !task.archived && task.status !== "completed");
  const resourceIds = new Set(financialTasks.flatMap(task => task.relatedRecommendationIds));
  const resources = working.recommendations.filter(resource => resourceIds.has(resource.id) && resource.active && !["dismissed", "rejected"].includes(resource.userStatus) && resource.userReportedAvailability !== "unavailable").slice(0, 6);

  async function review(event: React.FormEvent) {
    event.preventDefault(); setError("");
    const version = ++operation.current;
    try {
      const proposed = { ...structuredClone(session.profile), finances: { ...parseFinances(values), projection } };
      setPending(true); setBase(session);
      const response = await onPreview(proposed);
      if (version !== operation.current) return;
      if (!response.phoenix_session) throw new Error("The plan preview could not be prepared.");
      setPreview(response);
    } catch (failure) { if (version === operation.current) setError((failure as Error).message); }
    finally { if (version === operation.current) setPending(false); }
  }
  function changeProjection(next: FinanceProjection, field: FinanceField) {
    next.estimatedFields = [...new Set([...next.estimatedFields, field])];
    setProjection(next);
    const defaults = projectedFinances({ ...session, profile: { ...session.profile, finances: undefined } }, next);
    setValues(previous => ({ ...previous, [field]: defaults[field]?.toString() ?? "" }));
    setPreview(null);
  }
  function reset() {
    const defaults = initialFinanceProjection(session, preferredJobId);
    setProjection(defaults); setValues(asInputs(projectedFinances(session, defaults))); setPreview(null);
  }
  const helpers: Record<FinanceField, string> = {
    monthlyTakeHomePay: projection.estimatedFields.includes("monthlyTakeHomePay") && job ? pay.note : "Monthly income after deductions.",
    monthlyHousingCost: projection.estimatedFields.includes("monthlyHousingCost") ? rent.note : "Your monthly rent and housing fees.",
    monthlyFoodCost: "Food estimate uses U.S. household spending. Edit for your household.",
    monthlyOtherCosts: "Utilities, supplies, clothing and personal care. Add transport, healthcare and other bills.",
  };
  const headline = !budget ? "Check your amounts" : budget.status === "incomplete" ? "Add missing amounts to check your budget" : budget.status === "deficit" ? "Over budget" : budget.status === "tight" ? "Little left for unexpected costs" : budget.status === "high_housing" ? "High housing cost" : "Within budget";
  return <section id="finances-panel" aria-labelledby="finances-title" className="scroll-mt-16 space-y-4">
    <h3 id="finances-title" className="text-xl font-semibold">Finances</h3>
    <form onSubmit={review} noValidate className="space-y-4 rounded-xl border bg-card p-4 sm:p-5">
      <fieldset disabled={disabled || pending} className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2"><Label htmlFor="finance-job">Selected job</Label>{options.jobs.length > 1 ? <select id="finance-job" className="w-full rounded-md border bg-background p-2 text-sm" value={projection.jobId ?? ""} onChange={event => {
          const nextPay = options.jobs.find(item => item.id === event.target.value)?.details.pay as Record<string, unknown> | undefined;
          const hours = nextPay?.hours_basis === "stated" && typeof nextPay.hours_per_week === "number" ? nextPay.hours_per_week : 40;
          changeProjection({ ...projection, jobId: event.target.value, hoursPerWeek: hours }, "monthlyTakeHomePay");
        }}>{options.jobs.map(item => <option key={item.id} value={item.id}>{item.title}{typeof item.details.employer === "string" ? " · " + item.details.employer : ""}</option>)}</select> : <p id="finance-job" className="text-sm">{job?.title ?? "Choose a job or enter income below"}</p>}</div>
        <div className="space-y-2"><Label htmlFor="finance-housing">Selected housing</Label>{options.housing.length > 1 ? <select id="finance-housing" className="w-full rounded-md border bg-background p-2 text-sm" value={projection.housingId ?? ""} onChange={event => changeProjection({ ...projection, housingId: event.target.value }, "monthlyHousingCost")}>{options.housing.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select> : <p id="finance-housing" className="text-sm">{housing?.title ?? "Choose housing or enter a cost below"}</p>}</div>
      </fieldset>
      <div className="border-t pt-4">
        <p className="mb-3 text-xs font-medium text-muted-foreground">Monthly amounts · USD</p>
        <fieldset disabled={disabled || pending} className="grid gap-4 sm:grid-cols-2">{FINANCE_FIELDS.map(([key]) => <div key={key} className="space-y-2">
          <Label htmlFor={"finance-" + key}>{INPUT_LABELS[key]}{projection.estimatedFields.includes(key) && <span className="ml-2 text-xs font-normal text-muted-foreground">Est.</span>}</Label>
          <Input id={"finance-" + key} aria-describedby={"finance-help-" + key} type="number" inputMode="decimal" min="0" max="1000000" step="0.01" placeholder="Unknown" value={values[key]} onChange={event => {
            setValues(previous => ({ ...previous, [key]: event.target.value }));
            setProjection(previous => ({ ...previous, estimatedFields: previous.estimatedFields.filter(field => field !== key) }));
            setPreview(null);
          }} />
          <p id={"finance-help-" + key} className="sr-only">{helpers[key]}</p>
          {key === "monthlyHousingCost" && housing && rent.amount == null && !values[key] && <p className="text-xs text-muted-foreground">Price not listed. Enter the confirmed cost.</p>}
        </div>)}</fieldset>
      </div>
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer">Estimates &amp; assumptions</summary>
        <div className="mt-3 space-y-3">
          {job && <><p>{pay.note} Gross pay: {estimate(pay.gross)}/month. One selected job is used at a time; selection does not confirm hiring.</p><fieldset disabled={disabled || pending} className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="finance-hours">Hours per week</Label><Input id="finance-hours" type="number" min="1" max="80" value={projection.hoursPerWeek} onChange={event => { const hours = Number(event.target.value); if (hours > 0 && hours <= 80) changeProjection({ ...projection, hoursPerWeek: hours }, "monthlyTakeHomePay"); }} /></div>
            <div className="space-y-2"><Label htmlFor="finance-take-home">Pay kept after deductions (%)</Label><Input id="finance-take-home" type="number" min="1" max="100" value={projection.takeHomePercent} onChange={event => { const percent = Number(event.target.value); if (percent > 0 && percent <= 100) changeProjection({ ...projection, takeHomePercent: percent }, "monthlyTakeHomePay"); }} /></div>
          </fieldset><p>80% take-home is a planning assumption; actual deductions vary.</p></>}
          <p>{rent.note}</p>
          <p>Food defaults to {money(US_COST_BASELINE.monthlyFood, 2)}/month. Other essentials default to {money(US_COST_BASELINE.monthlyOther, 2)}/month for utilities, supplies, clothing and personal care. These are {US_COST_BASELINE.year} U.S. household averages, not one-person minimums. Edit to fit your needs and add travel, healthcare, debt and other bills. <a className="text-brand-text underline" href={US_COST_BASELINE.source} target="_blank" rel="noopener noreferrer">BLS source</a></p>
          <p>Food: $10,633/year ÷ 12. Essentials: ($4,931 + $844 + $2,010 + $986)/year ÷ 12.</p>
          <p>Phoenix flags housing above 30% of take-home or spending at least 80%. These are planning targets, not eligibility rules. Remaining = income − housing − food − essentials. <a className="text-brand-text underline" href="https://files.consumerfinance.gov/f/documents/cfpb_well-being_monthly-budget.pdf" target="_blank" rel="noopener noreferrer">Budget worksheet</a></p>
        </div>
      </details>
      <div aria-live="polite" className="grid grid-cols-2 gap-3">{[["Monthly costs", budget?.totalCosts], ["Remaining", budget?.remaining]].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-muted/50 p-3"><p className="text-xs text-muted-foreground">{String(label)}</p><p className={"mt-1 text-lg font-semibold " + (typeof value === "number" && value < 0 ? "text-destructive" : "")}>{estimate(typeof value === "number" ? value : null)}</p></div>)}</div>
      <p role="status" className={"text-sm " + (budget?.status === "deficit" ? "text-destructive" : budget?.status === "within_budget" ? "text-ok" : "text-muted-foreground")}>{headline}{budget?.housingShare != null ? " · Housing " + Math.round(budget.housingShare * 100) + "% of income" : ""}</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <Button type="submit" variant={pending ? "outline" : "default"} className={pending ? "disabled:opacity-100" : undefined} disabled={disabled || pending}>{pending ? <PhoenixThinking /> : "Review budget"}</Button>
    </form>
    {!!financialTasks.length && <details className="rounded-xl border p-4"><summary className="cursor-pointer text-sm font-medium">Budget steps ({financialTasks.length})</summary><ul className="mt-3 space-y-3 text-sm">{financialTasks.map(task => <li key={task.id}><p className="font-medium">{task.title}</p><p className="mt-1 text-muted-foreground">{task.description}</p></li>)}</ul></details>}
    {!!resources.length && <details className="rounded-xl border p-4"><summary className="cursor-pointer text-sm font-medium">Resources to consider ({resources.length})</summary><ul className="mt-3 grid gap-3 sm:grid-cols-2">{resources.map(resource => <li key={resource.id}><p className="text-sm font-medium">{resource.title}</p><p className="text-xs text-muted-foreground">{resourceLabel(resource)}</p>{preview ? resource.sourceUrl && /^https?:\/\//i.test(resource.sourceUrl) && <a href={resource.sourceUrl} target="_blank" rel="noopener noreferrer" className="text-xs text-brand-text underline">Website</a> : <Button type="button" variant="link" className="h-auto px-0 text-xs" onClick={() => onOpenResource(resource.id)}>View resource</Button>}</li>)}</ul></details>}
    {preview?.phoenix_session && base && <div className="space-y-4 rounded-xl border p-4">
      <PlanPreview before={base} after={preview.phoenix_session} />
      {base !== session && <p role="status" className="text-xs text-warn">Your plan changed. Review this budget again.</p>}
      <div className="flex flex-wrap gap-2"><Button type="button" disabled={disabled || base !== session} onClick={() => { onConfirm(preview); setPreview(null); }}>Apply budget and plan</Button><Button type="button" variant="outline" onClick={() => setPreview(null)}>Edit</Button><Button type="button" variant="ghost" onClick={reset}>Cancel</Button></div>
    </div>}
  </section>;
}

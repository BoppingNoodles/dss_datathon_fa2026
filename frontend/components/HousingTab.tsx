"use client";

import { useEffect, useState } from "react";
import { compareHousing, money } from "@/lib/api";
import type { HousingArea, HousingComparisonResponse, HousingSection, JobCard, Pay } from "@/lib/types";
import { payText } from "./JobsTab";
import { Badge, EmptyState, Notes } from "./ui";

const input = "w-full rounded-lg border border-line bg-card px-3 py-2 text-base";
const pct = (x: number) => `${Math.round(x * 100)}%`;

function AreaCard({ a, onUse }: { a: HousingArea; onUse: (rent: number) => void }) {
  return (
    <li className="rounded-xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div>
          <h4 className="text-lg font-semibold">{a.label}</h4>
          <p className="text-sm text-muted">
            {a.usable_rental_records.toLocaleString()} rental record{a.usable_rental_records === 1 ? "" : "s"}
          </p>
        </div>
        {a.median_monthly_rent != null && !a.suppressed && (
          <p className="text-right">
            <span className="block text-xl font-semibold">{money(a.median_monthly_rent)}</span>
            <span className="text-sm text-muted">typical monthly rent</span>
          </p>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {a.rent_basis === "rent_estimate" && <Badge tone="warn">Estimate, not an available listing</Badge>}
        {a.suppressed && <Badge tone="neutral">Too few listings to show details</Badge>}
      </div>
      {!a.suppressed && a.rent_p25 != null && a.rent_p75 != null && (
        <p className="mt-2 text-sm">Most rents fall between {money(a.rent_p25)} and {money(a.rent_p75)}.</p>
      )}
      {a.nearby_services.length > 0 && (
        <ul className="mt-2 text-sm text-muted">
          {a.nearby_services.map((s) => (
            <li key={s.family}>
              {s.family_label}: {s.count_within_1_mile ?? "unknown"} within 1 mile
              {s.nearest_miles != null && `, nearest about ${s.nearest_miles} mi`}
            </li>
          ))}
        </ul>
      )}
      {a.source_note && <p className="mt-2 text-sm text-muted">{a.source_note}</p>}
      {a.median_monthly_rent != null && !a.suppressed && (
        <button type="button" onClick={() => onUse(a.median_monthly_rent!)}
          className="mt-3 rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:border-brand">
          Compare this rent with a job&apos;s pay
        </button>
      )}
    </li>
  );
}

function RentCalculator({ job, rent, setRent }: { job: JobCard | null; rent: string; setRent: (v: string) => void }) {
  const [payMin, setPayMin] = useState("");
  const [payMax, setPayMax] = useState("");
  const [period, setPeriod] = useState<NonNullable<Pay["period"]>>("hour");
  const [hours, setHours] = useState("");
  const [result, setResult] = useState<HousingComparisonResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!job) return;
    setPayMin(job.pay.min?.toString() ?? "");
    setPayMax(job.pay.max?.toString() ?? "");
    if (job.pay.period) setPeriod(job.pay.period);
    setHours(job.pay.hours_basis === "stated" && job.pay.hours_per_week ? String(job.pay.hours_per_week) : "");
    setResult(null);
  }, [job]);

  const num = (s: string) => (s.trim() === "" || Number.isNaN(Number(s)) || Number(s) <= 0 ? null : Number(s));

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await compareHousing({
        pay_min: num(payMin), pay_max: num(payMax), pay_period: period,
        hours_per_week: num(hours), monthly_rent: num(rent),
      }));
    } catch (err) {
      setResult(null);
      setError(err instanceof TypeError ? "Can't reach the Phoenix server right now." : (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-line bg-card p-4 sm:p-5" aria-labelledby="calc">
      <h3 id="calc" className="text-lg font-semibold">Compare pay with rent</h3>
      <p className="mt-1 text-sm text-muted">
        See what share of a job&apos;s advertised pay would go to rent.
        {job && <> Filled in from <span className="font-medium text-ink">{job.title}</span> ({payText(job.pay)}).</>}
      </p>
      <form onSubmit={run} className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
        <label className="text-sm font-medium">Pay from
          <input className={`${input} mt-1`} inputMode="decimal" value={payMin} onChange={(e) => setPayMin(e.target.value)} placeholder="20" />
        </label>
        <label className="text-sm font-medium">Pay to
          <input className={`${input} mt-1`} inputMode="decimal" value={payMax} onChange={(e) => setPayMax(e.target.value)} placeholder="Optional" />
        </label>
        <label className="text-sm font-medium">Per
          <select className={`${input} mt-1`} value={period} onChange={(e) => setPeriod(e.target.value as typeof period)}>
            {["hour", "day", "week", "month", "year"].map((p) => <option key={p}>{p}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium">Hours per week
          <input className={`${input} mt-1`} inputMode="decimal" value={hours} onChange={(e) => setHours(e.target.value)} placeholder="40 if blank" />
        </label>
        <label className="text-sm font-medium">Monthly rent
          <input className={`${input} mt-1`} inputMode="decimal" value={rent} onChange={(e) => setRent(e.target.value)} placeholder="1650" />
        </label>
        <button type="submit" disabled={busy}
          className="col-span-2 rounded-lg bg-brand px-4 py-2.5 font-semibold text-white hover:bg-brand-dark disabled:opacity-60 sm:col-span-5 sm:justify-self-start">
          {busy ? "Calculating…" : "Compare"}
        </button>
      </form>

      {error && <p className="mt-3 text-sm font-medium text-brand-dark">{error}</p>}
      {result && (
        <div className="mt-4 rounded-lg bg-paper p-4" aria-live="polite">
          {result.status === "ok" && result.rent_burden_min != null && result.rent_burden_max != null ? (
            <>
              <p className="text-2xl font-semibold">
                {result.rent_burden_min === result.rent_burden_max
                  ? pct(result.rent_burden_max)
                  : `${pct(result.rent_burden_min)} to ${pct(result.rent_burden_max)}`}{" "}
                <span className="text-base font-normal">of pay before taxes would go to rent</span>
              </p>
              <p className="mt-1 text-sm text-muted">
                Based on {result.annual_gross_min === result.annual_gross_max
                  ? money(result.annual_gross_min)
                  : `${money(result.annual_gross_min)}–${money(result.annual_gross_max)}`} a year.
                Many housing programs use 30% as a guide.
              </p>
            </>
          ) : (
            <p className="font-semibold">Unknown. Enter both pay and rent to compare.</p>
          )}
          <ul className="mt-2 list-disc pl-5 text-sm text-muted">
            {result.assumptions.map((a, i) => <li key={i}>{a}</li>)}
            <li>{result.caveat}</li>
          </ul>
        </div>
      )}
    </section>
  );
}

export default function HousingTab({ data, job }: { data: HousingSection; job: JobCard | null }) {
  const [rent, setRent] = useState("");
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        Rent ranges by ZIP code or neighborhood. Phoenix never shows street addresses, and these are not live listings.
      </p>
      <Notes notes={data.status === "not_integrated" ? [] : data.notes} />
      {data.status === "not_integrated" ? (
        <EmptyState title="Neighborhood rent ranges aren't connected yet">
          This tab will show typical rents by ZIP code and the services near each area. The calculator below works now.
        </EmptyState>
      ) : data.areas.length === 0 ? (
        <EmptyState title="Not enough rental listings here">Try a nearby city or ZIP code.</EmptyState>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {data.areas.map((a) => <AreaCard key={a.area_id} a={a} onUse={(r) => setRent(String(r))} />)}
        </ul>
      )}
      <RentCalculator job={job} rent={rent} setRent={setRent} />
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { compareHousing, money } from "@/lib/api";
import type { HousingArea, HousingComparisonResponse, HousingSection, PayComparisonJob, Pay } from "@/lib/types";
import { payText } from "@/lib/jobs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Badge, EmptyState, Notes } from "./shared";

const field = "h-10 bg-card text-base md:text-base";
const pct = (x: number) => `${Math.round(x * 100)}%`;

function AreaCard({ a, onUse }: { a: HousingArea; onUse: (rent: number) => void }) {
  return (
    <li>
      <Card className="h-full gap-0 p-4 text-base">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div>
          <h4 className="text-lg font-semibold">{a.label}</h4>
          <p className="text-sm text-muted-foreground">
            {a.usable_rental_records.toLocaleString()} rental record{a.usable_rental_records === 1 ? "" : "s"}
          </p>
        </div>
        {a.median_monthly_rent != null && !a.suppressed && (
          <p className="text-right">
            <span className="block text-xl font-semibold">{money(a.median_monthly_rent)}</span>
            <span className="text-sm text-muted-foreground">typical monthly rent</span>
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
        <ul className="mt-2 text-sm text-muted-foreground">
          {a.nearby_services.map((s) => (
            <li key={s.family}>
              {s.family_label}: {s.count_within_1_mile ?? "unknown"} within 1 mile
              {s.nearest_miles != null && `, nearest about ${s.nearest_miles} mi`}
            </li>
          ))}
        </ul>
      )}
      {a.source_note && <p className="mt-2 text-sm text-muted-foreground">{a.source_note}</p>}
      {a.median_monthly_rent != null && !a.suppressed && (
        <Button type="button" variant="outline" size="lg" className="mt-3 self-start" onClick={() => onUse(a.median_monthly_rent!)}>
          Compare this rent with a job&apos;s pay
        </Button>
      )}
      </Card>
    </li>
  );
}

function RentCalculator({ job, rent, setRent }: { job: PayComparisonJob | null; rent: string; setRent: (v: string) => void }) {
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
    <Card role="region" aria-labelledby="calc" className="text-base">
      <CardHeader>
        <CardTitle id="calc" className="text-lg">Compare pay with rent</CardTitle>
        <CardDescription>
          See what share of a job&apos;s advertised pay would go to rent.
          {job && <> Filled in from <span className="font-medium text-foreground">{job.title}</span> ({payText(job.pay)}).</>}
        </CardDescription>
      </CardHeader>
      <CardContent>
      <form onSubmit={run} className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div className="space-y-1.5">
          <Label htmlFor="pay-min">Pay from</Label>
          <Input id="pay-min" className={field} inputMode="decimal" value={payMin} onChange={(e) => setPayMin(e.target.value)} placeholder="20" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pay-max">Pay to</Label>
          <Input id="pay-max" className={field} inputMode="decimal" value={payMax} onChange={(e) => setPayMax(e.target.value)} placeholder="Optional" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pay-period">Per</Label>
          <NativeSelect id="pay-period" className="w-full [&_select]:h-10 [&_select]:bg-card [&_select]:text-base"
            value={period} onChange={(e) => setPeriod(e.target.value as typeof period)}>
            {["hour", "day", "week", "month", "year"].map((p) => <NativeSelectOption key={p} value={p}>{p}</NativeSelectOption>)}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="hours">Hours per week</Label>
          <Input id="hours" className={field} inputMode="decimal" value={hours} onChange={(e) => setHours(e.target.value)} placeholder="40 if blank" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rent">Monthly rent</Label>
          <Input id="rent" className={field} inputMode="decimal" value={rent} onChange={(e) => setRent(e.target.value)} placeholder="1650" />
        </div>
        <Button type="submit" disabled={busy} className="col-span-2 h-11 px-5 text-base font-semibold sm:col-span-5 sm:justify-self-start">
          {busy ? "Calculating…" : "Compare"}
        </Button>
      </form>

      {error && <p className="mt-3 text-sm font-medium text-destructive">{error}</p>}
      {result && (
        <div className="mt-4 rounded-lg bg-muted p-4" aria-live="polite">
          {result.status === "ok" && result.rent_burden_min != null && result.rent_burden_max != null ? (
            <>
              <p className="text-2xl font-semibold">
                {result.rent_burden_min === result.rent_burden_max
                  ? pct(result.rent_burden_max)
                  : `${pct(result.rent_burden_min)} to ${pct(result.rent_burden_max)}`}{" "}
                <span className="text-base font-normal">of pay before taxes would go to rent</span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Based on {result.annual_gross_min === result.annual_gross_max
                  ? money(result.annual_gross_min)
                  : `${money(result.annual_gross_min)}–${money(result.annual_gross_max)}`} a year.
                Many housing programs use 30% as a guide.
              </p>
            </>
          ) : (
            <p className="font-semibold">Unknown. Enter both pay and rent to compare.</p>
          )}
          <ul className="mt-2 list-disc pl-5 text-sm text-muted-foreground">
            {result.assumptions.map((a, i) => <li key={i}>{a}</li>)}
            <li>{result.caveat}</li>
          </ul>
        </div>
      )}
      </CardContent>
    </Card>
  );
}

export default function HousingTab({ data, job }: { data: HousingSection; job: PayComparisonJob | null }) {
  const [rent, setRent] = useState("");
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
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

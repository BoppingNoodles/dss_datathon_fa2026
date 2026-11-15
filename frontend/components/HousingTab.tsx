"use client";

import { useEffect, useMemo, useState } from "react";
import { compareHousing, money } from "@/lib/api";
import type { HousingArea, HousingComparisonResponse, HousingSection, JobCard, MappedPlace, PayComparisonJob, Pay, ServiceMapPoint } from "@/lib/types";
import { payText } from "@/lib/jobs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Badge, EmptyState, Notes } from "./shared";
import AreaMap from "./AreaMap";
import { cn } from "@/lib/utils";

const field = "h-10 bg-card text-base md:text-base";
const pct = (x: number) => `${Math.round(x * 100)}%`;

function AreaCard({ a, selected, onSelect }: { a: HousingArea; selected: boolean; onSelect: () => void }) {
  const range = !a.suppressed && a.rent_p25 != null && a.rent_p75 != null;
  const places = a.nearby_places?.slice(0, 3) ?? [];
  return (
    <li>
      <Card className={cn("relative gap-3 transition-shadow", selected ? "ring-2 ring-primary/60" : "hover:ring-2 hover:ring-primary/40")}>
        <button type="button" aria-pressed={selected} aria-label={`Show ${a.label} on map`} onClick={onSelect}
          className="absolute inset-0 cursor-pointer rounded-xl focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-[-2px]" />
        <CardHeader className="pointer-events-none">
          <div className="flex items-start justify-between gap-3">
            <CardTitle><h4 className="text-lg font-semibold">{a.label}</h4></CardTitle>
            {selected && <span className="shrink-0 text-xs font-medium text-brand-text">On map</span>}
          </div>
          {a.recommendation?.recommended && <div><Badge tone="ok">Suggested area #{a.recommendation.rank}</Badge></div>}
          <p className="mt-1 text-xl font-semibold">
            {range ? `${money(a.rent_p25)}–${money(a.rent_p75)}` : "Rent range unavailable"}
            {range && <span className="ml-1 text-sm font-normal text-muted-foreground">/ month</span>}
          </p>
          {a.rent_basis === "rent_estimate" && <p className="text-xs text-warn">Estimated rents</p>}
        </CardHeader>
        <CardContent className="pointer-events-none flex flex-col gap-2">
          {a.recommendation?.recommended && <ul className="mb-2 flex flex-col gap-1 text-xs text-muted-foreground" aria-label={`Why ${a.label} is suggested`}>
            {a.recommendation.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>}
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Nearby places</p>
          {places.length ? <ul className="flex flex-col gap-2.5">
            {places.map((place, index) => <li key={place.place_id} className="flex min-w-0 items-start gap-2 text-sm">
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-brand-text" aria-hidden="true">{index + 1}</span>
              <div className="min-w-0">
              {place.maps_url ? <a href={place.maps_url} target="_blank" rel="noopener noreferrer" className="pointer-events-auto relative font-medium hover:text-brand-text hover:underline">{place.name} <span aria-hidden="true">↗</span></a>
                : <p className="font-medium">{place.name}</p>}
              <p className="truncate text-xs text-muted-foreground" title={place.family_label}>{place.family_label.split(" (")[0]}</p>
              </div>
            </li>)}
          </ul> : <p className="text-sm text-muted-foreground">Nearby place details aren&apos;t available for this area yet.</p>}
        </CardContent>
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

const NO_MAP_POINTS: ServiceMapPoint[] = [];

export default function HousingTab({ data, job, selectedJob = null, mapPoints = NO_MAP_POINTS }: { data: HousingSection; job: PayComparisonJob | null; selectedJob?: JobCard | null; mapPoints?: ServiceMapPoint[] }) {
  const [rent, setRent] = useState("");
  const zipAreas = data.areas.filter((area) => area.area_type === "zip");
  const areas = zipAreas.length ? zipAreas : data.areas;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = areas.find((area) => area.area_id === selectedId) ?? areas[0];
  const zip = selected?.area_type === "zip" ? selected.label.match(/\b\d{5}\b/)?.[0] ?? null : null;
  const places = useMemo<MappedPlace[]>(() => {
    const byId = new Map(mapPoints.map((point) => [point.place_id, point]));
    return (selected?.nearby_places ?? []).flatMap((place, index) => {
      const point = byId.get(place.place_id);
      return point && Number.isFinite(point.lat) && Number.isFinite(point.lon)
        ? [{ ...place, ...point, number: index + 1 }] : [];
    });
  }, [mapPoints, selected]);
  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-muted-foreground">Monthly rent ranges and three nearby places to know. Ranges cover the middle half of snapshot rents, across home sizes.</p>
      {data.ranking_note && <p className="text-sm text-muted-foreground">{data.ranking_note}</p>}
      <Notes notes={data.status === "not_integrated" ? [] : data.notes} />
      {data.status === "not_integrated" ? <EmptyState title="Neighborhood rent ranges aren't connected yet" />
        : areas.length === 0 ? <EmptyState title="Not enough rental listings here">Try a nearby city or ZIP code.</EmptyState>
        : <div className="grid items-start gap-5 lg:gap-6 lg:grid-cols-[minmax(20rem,0.85fr)_minmax(0,1.65fr)]">
          <div className="order-first lg:sticky lg:top-5 lg:order-last">
            <AreaMap zip={zip} label={selected?.label ?? "Your area"} places={places} job={selectedJob} />
          </div>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
            {areas.map((area) => <AreaCard key={area.area_id} a={area} selected={area.area_id === selected?.area_id} onSelect={() => {
              setSelectedId(area.area_id);
              if (window.innerWidth < 1024) requestAnimationFrame(() => document.getElementById("housing-map")?.scrollIntoView({ behavior: "smooth", block: "start" }));
            }} />)}
          </ul>
        </div>}
      <details className="group" open={job ? true : undefined}>
        <summary className="cursor-pointer text-sm font-medium text-brand-text">Compare pay with rent</summary>
        <div className="mt-3"><RentCalculator job={job} rent={rent} setRent={setRent} /></div>
      </details>
    </div>
  );
}

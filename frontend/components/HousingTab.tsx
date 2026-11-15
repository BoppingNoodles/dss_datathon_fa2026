"use client";

import { useMemo, useState } from "react";
import { money } from "@/lib/api";
import type { HousingArea, HousingSection, JobCard, MappedPlace, ServiceMapPoint } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, EmptyState, Notes } from "./shared";
import AreaMap from "./AreaMap";
import { cn } from "@/lib/utils";
import ResourceActions, { useResources } from "./ResourceActions";
import ResourceCandidates from "./ResourceCandidates";


function AreaCard({ a, selected, onSelect }: { a: HousingArea; selected: boolean; onSelect: () => void }) {
  const range = !a.suppressed && a.rent_p25 != null && a.rent_p75 != null;
  const places = a.nearby_places?.slice(0, 3) ?? [];
  return (
    <li>
      <Card className={cn("relative cursor-pointer gap-3 transition-shadow", selected ? "ring-2 ring-primary/60" : "hover:ring-2 hover:ring-primary/40")} onClick={event => {
        if (!(event.target as HTMLElement).closest("a, button, input, [role='group']")) onSelect();
      }}>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <CardTitle><h4 className="text-lg font-semibold"><button type="button" aria-pressed={selected} aria-label={`Show ${a.label} on map`} onClick={onSelect} className="rounded text-left focus-visible:outline-2 focus-visible:outline-ring">{a.label}</button></h4></CardTitle>
            {selected && <span className="shrink-0 text-xs font-medium text-brand-text">On map</span>}
          </div>
          {a.recommendation?.recommended && <div><Badge tone="ok">Suggested area #{a.recommendation.rank}</Badge></div>}
          <p className="mt-1 text-xl font-semibold">
            {range ? `${money(a.rent_p25)}–${money(a.rent_p75)}` : "Rent range unavailable"}
            {range && <span className="ml-1 text-sm font-normal text-muted-foreground">/ month</span>}
          </p>
          {a.rent_basis === "rent_estimate" && <p className="text-xs text-warn">Estimated rents</p>}
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
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
        <div className="relative z-10 px-6"><ResourceActions id={`area:${a.area_id}`} /></div>
      </Card>
    </li>
  );
}

const NO_MAP_POINTS: ServiceMapPoint[] = [];

export default function HousingTab({ data, selectedJob = null, mapPoints = NO_MAP_POINTS }: { data: HousingSection; selectedJob?: JobCard | null; mapPoints?: ServiceMapPoint[] }) {
  const { session } = useResources();
  const hidden = new Set(session?.dismissedRecommendationIds ?? []);
  const zipAreas = data.areas.filter((area) => area.area_type === "zip");
  const areas = (zipAreas.length ? zipAreas : data.areas).filter((a) => !hidden.has(`area:${a.area_id}`));
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
      <ResourceCandidates mode="temporary_housing" />
      <h3 className="text-lg font-semibold">Rent by area</h3>
      <Notes notes={data.status === "not_integrated" ? [] : ["Ranges show the middle half of snapshot rents, across home sizes. They are not available listings.", ...(data.ranking_note ? [data.ranking_note] : []), ...data.notes]} />
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

    </div>
  );
}

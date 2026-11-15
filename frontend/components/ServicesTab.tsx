"use client";

import ResourceActions, { useResources } from "./ResourceActions";
import ResourceCandidates from "./ResourceCandidates";

import type { ServiceCard, ServiceSort, ServicesSection } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, EmptyState, Notes, SortToggle } from "./shared";

function Stars({ rating }: { rating: number }) {
  const pct = Math.max(0, Math.min(100, (rating / 5) * 100));
  return (
    <span className="relative inline-block text-lg leading-none" aria-hidden>
      <span className="text-border">★★★★★</span>
      <span className="absolute inset-0 overflow-hidden whitespace-nowrap text-star" style={{ width: `${pct}%` }}>
        ★★★★★
      </span>
    </span>
  );
}

function StarBars({ dist, label }: { dist: Record<string, number>; label: string }) {
  const total = Object.values(dist).reduce((a, b) => a + b, 0);
  if (!total) return null;
  return (
    <div>
      <p className="mb-1 text-sm font-medium">{label}</p>
      <div className="space-y-0.5">
        {[5, 4, 3, 2, 1].map((s) => {
          const n = dist[String(s)] ?? 0;
          return (
            <div key={s} className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="w-10 shrink-0">{s} star</span>
              <span className="h-2 flex-1 overflow-hidden rounded bg-border">
                <span className="block h-full rounded bg-star" style={{ width: `${(n / total) * 100}%` }} />
              </span>
              <span className="w-8 shrink-0 text-right tabular-nums">{n}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function verificationBadge(v: ServiceCard["verification"]) {
  if (v.status === "verified_public_community")
    return <Badge tone="ok">{v.provider_type === "public" ? "Public" : "Community"} provider</Badge>;
  if (v.status === "verified_private") return <Badge tone="neutral">Verified private provider</Badge>;
  return <Badge tone="neutral">Not verified yet</Badge>;
}

function ServiceItem({ c }: { c: ServiceCard }) {
  const { session } = useResources();
  const resource = session?.recommendations.find((r) => r.id === `service:${c.place_id}`);
  if (resource && (resource.userStatus === "dismissed" || resource.userStatus === "rejected")) return null;
  const r = c.rating;
  const ev = c.review_evidence;
  const ageTone = c.eligibility.age_status === "outside_published_age_criterion" ? "warn"
    : c.eligibility.age_status === "meets_published_age_criterion" ? "ok" : "neutral";
  return (
    <li>
      <Card className="h-full gap-3">
      <CardHeader>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <CardTitle><h4 className="text-lg font-semibold break-words">{c.name}</h4></CardTitle>
          <p className="text-sm text-muted-foreground">{c.family_label.split(" (")[0]}</p>
        </div>
        {c.distance.miles != null && (
          <p className="shrink-0 text-sm font-medium" title={c.distance.measure ?? undefined}>
            About {c.distance.miles} mi
          </p>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {verificationBadge(c.verification)}
        {c.availability.temporarily_closed && <Badge tone="warn">Temporarily closed</Badge>}
        {r.overall_rating != null ? (
          <span className="flex items-center gap-1.5 text-sm">
            <Stars rating={r.overall_rating} />
            <span className="font-semibold">{r.overall_rating.toFixed(1)}</span>
            <span className="text-muted-foreground">({r.overall_review_count?.toLocaleString()})</span>
          </span>
        ) : (
          <span className="text-sm text-muted-foreground">No Google rating yet</span>
        )}
      </div>

      {ageTone === "warn" && <p className="mt-2 text-sm text-warn">Check the provider&apos;s age requirements before visiting.</p>}
      </CardHeader>
      <CardContent>
      <details className="text-sm">
        <summary className="cursor-pointer font-medium text-brand-text">Hours, eligibility, and reviews</summary>
        <div className="mt-3 flex flex-col gap-3">
          <p>{c.eligibility.note}</p>
          {c.verification.cost_eligibility_notes && <p>{c.verification.cost_eligibility_notes}</p>}
          <p><span className="font-medium">Hours: </span>{c.availability.hours_text}</p>
          {c.contact.address && <p><span className="font-medium">Address: </span>{c.contact.address}</p>}
          {c.distance.miles != null && <p className="text-muted-foreground">Distance is a straight line from the {c.distance.reference_point}, not travel time.</p>}
          {r.overall_star_distribution && <StarBars dist={r.overall_star_distribution} label="All Google reviews" />}
          {ev.sampled_review_count > 0 && <div className="rounded-lg bg-muted p-3">
            <StarBars dist={ev.star_distribution} label={`Sample of ${ev.sampled_review_count} reviews`} />
            {ev.snippets.map((s, i) => <blockquote key={i} className="mt-2 border-l-2 border-border pl-3">{s.attribution}: &ldquo;{s.text}&rdquo;</blockquote>)}
          </div>}
          {c.verification.checked_on && <p className="text-muted-foreground">Provider details checked {c.verification.checked_on}.</p>}
          <p className="text-muted-foreground">{c.confirm_prompt}</p>
        </div>
      </details>
      </CardContent>

      <CardFooter className="mt-auto flex-wrap gap-2">
        {c.contact.phone && (
          <Button asChild variant="outline" size="lg"><a href={`tel:${c.contact.phone.replace(/[^\d+]/g, "")}`}>
            Call {c.contact.phone}
          </a></Button>
        )}
        {(c.verification.official_url ?? c.contact.website) && (
          <Button asChild variant="outline" size="lg"><a target="_blank" rel="noopener noreferrer"
            href={(c.verification.official_url ?? c.contact.website)!}>
            Website
          </a></Button>
        )}
        {c.contact.maps_url && (
          <Button asChild variant="outline" size="lg"><a target="_blank" rel="noopener noreferrer"
            href={c.contact.maps_url}>
            Map
          </a></Button>
        )}
        <ResourceActions id={`service:${c.place_id}`} />
      </CardFooter>
      </Card>
    </li>
  );
}

export default function ServicesTab({ data, loading, onSort }: {
  data: ServicesSection; loading: boolean; onSort: (s: ServiceSort) => void;
}) {
  return (
    <div className="flex flex-col gap-5">
      <ResourceCandidates mode="service" excludeIds={data.groups.flatMap((g) => g.items.map((c) => `service:${c.place_id}`))} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xl font-semibold">Services</h3>
        <SortToggle
          label="Sort services" value={data.sort} disabled={loading} onChange={onSort}
          options={[{ value: "highly_rated", label: "Highly rated" }, { value: "nearest", label: "Nearest" }]}
        />
      </div>

      <Notes notes={[`${data.need_label} services ${data.search_area}.`, `Highly rated: ${data.ranking_settings.highly_rated_min_rating}+ stars and ${data.ranking_settings.highly_rated_min_reviews}+ reviews.`, ...data.notes, ...data.groups.flatMap(group => group.note ? [group.note] : [])]} />

      {data.groups.length === 0 ? (
        <EmptyState title="No services found for this need here">
          Try a nearby city, a different ZIP code, or another need.
        </EmptyState>
      ) : (
        data.groups.map((g) => (
          <section key={g.key} aria-labelledby={`g-${g.key}`}>
            <div className="mb-2">
              <h3 id={`g-${g.key}`} className="text-lg font-semibold">
                {g.label}{" "}
                <span className="text-sm font-normal text-muted-foreground">
                  {g.total > g.items.length ? `showing ${g.items.length} of ${g.total}` : g.total}
                </span>
              </h3>
            </div>
            <ul className="grid gap-4 md:grid-cols-2">
              {g.items.map((c) => <ServiceItem key={c.place_id} c={c} />)}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}

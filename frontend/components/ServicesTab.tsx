"use client";

import type { ServiceCard, ServiceSort, ServicesSection } from "@/lib/types";
import { Badge, EmptyState, Notes, SortToggle } from "./ui";

function Stars({ rating }: { rating: number }) {
  const pct = Math.max(0, Math.min(100, (rating / 5) * 100));
  return (
    <span className="relative inline-block text-lg leading-none" aria-hidden>
      <span className="text-line">★★★★★</span>
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
            <div key={s} className="flex items-center gap-2 text-xs text-muted">
              <span className="w-10 shrink-0">{s} star</span>
              <span className="h-2 flex-1 overflow-hidden rounded bg-line">
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
    return <Badge tone="ok">Verified {v.provider_type === "public" ? "public" : "community"} provider</Badge>;
  if (v.status === "verified_private") return <Badge tone="neutral">Verified private provider</Badge>;
  return <Badge tone="neutral">Not verified yet</Badge>;
}

function Card({ c }: { c: ServiceCard }) {
  const r = c.rating;
  const ev = c.review_evidence;
  const ageTone = c.eligibility.age_status === "outside_published_age_criterion" ? "warn"
    : c.eligibility.age_status === "meets_published_age_criterion" ? "ok" : "neutral";
  return (
    <li className="rounded-xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <h4 className="text-lg font-semibold break-words">{c.name}</h4>
          <p className="text-sm text-muted">{c.family_label}</p>
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
            <span className="text-muted">({r.overall_review_count?.toLocaleString()} Google reviews)</span>
          </span>
        ) : (
          <span className="text-sm text-muted">No Google rating yet</span>
        )}
      </div>

      <p className={`mt-2 text-sm ${ageTone === "warn" ? "text-warn" : ageTone === "ok" ? "text-ok" : "text-muted"}`}>
        {c.eligibility.note}
      </p>
      {c.verification.cost_eligibility_notes && (
        <p className="mt-1 text-sm">{c.verification.cost_eligibility_notes}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-2 text-sm font-medium">
        {c.contact.phone && (
          <a className="rounded-lg border border-line px-3 py-1.5 hover:border-brand" href={`tel:${c.contact.phone.replace(/[^\d+]/g, "")}`}>
            Call {c.contact.phone}
          </a>
        )}
        {(c.verification.official_url ?? c.contact.website) && (
          <a className="rounded-lg border border-line px-3 py-1.5 hover:border-brand" target="_blank" rel="noopener noreferrer"
            href={(c.verification.official_url ?? c.contact.website)!}>
            Website
          </a>
        )}
        {c.contact.maps_url && (
          <a className="rounded-lg border border-line px-3 py-1.5 hover:border-brand" target="_blank" rel="noopener noreferrer"
            href={c.contact.maps_url}>
            Map
          </a>
        )}
      </div>

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer font-medium text-brand-text">Hours, address, and reviews</summary>
        <div className="mt-2 space-y-3">
          <p><span className="font-medium">Hours: </span>{c.availability.hours_text}</p>
          {c.contact.address && <p><span className="font-medium">Address: </span>{c.contact.address}</p>}
          {c.distance.miles != null && (
            <p className="text-muted">Distance is a straight line from the {c.distance.reference_point}, not travel time.</p>
          )}
          {r.overall_star_distribution && <StarBars dist={r.overall_star_distribution} label="All Google reviews" />}
          {ev.sampled_review_count > 0 && (
            <div className="rounded-lg bg-paper p-3">
              <StarBars dist={ev.star_distribution}
                label={`Sample of ${ev.sampled_review_count} reviews${ev.date_min ? ` (${ev.date_min.slice(0, 4)}–${ev.date_max?.slice(0, 4)})` : ""}`} />
              {ev.snippets.map((s, i) => (
                <blockquote key={i} className="mt-2 border-l-2 border-line pl-3">
                  {s.attribution}: &ldquo;{s.text}&rdquo;
                </blockquote>
              ))}
            </div>
          )}
          {c.verification.checked_on && (
            <p className="text-muted">Checked against the provider&apos;s official page on {c.verification.checked_on}.</p>
          )}
        </div>
      </details>

      <p className="mt-3 border-t border-line pt-2 text-sm text-muted">{c.confirm_prompt}</p>
    </li>
  );
}

export default function ServicesTab({ data, loading, onSort }: {
  data: ServicesSection; loading: boolean; onSort: (s: ServiceSort) => void;
}) {
  const s = data.ranking_settings;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          {data.need_label} services {data.search_area}.
        </p>
        <SortToggle
          label="Sort services" value={data.sort} disabled={loading} onChange={onSort}
          options={[{ value: "highly_rated", label: "Highly rated" }, { value: "nearest", label: "Nearest" }]}
        />
      </div>

      <Notes notes={data.notes} />

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
                <span className="text-sm font-normal text-muted">
                  {g.total > g.items.length ? `showing ${g.items.length} of ${g.total}` : g.total}
                </span>
              </h3>
              {g.key === "highly_rated" && (
                <p className="text-sm text-muted">
                  {s.highly_rated_min_rating}+ stars with {s.highly_rated_min_reviews}+ Google reviews. A rating shows
                  how visitors felt. It doesn&apos;t prove a service is free or right for you.
                </p>
              )}
              {g.note && <p className="text-sm text-muted">{g.note}</p>}
            </div>
            <ul className="grid gap-3 lg:grid-cols-2">
              {g.items.map((c) => <Card key={c.place_id} c={c} />)}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}

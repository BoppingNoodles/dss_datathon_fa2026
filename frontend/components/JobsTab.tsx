"use client";

import { money } from "@/lib/api";
import type { JobCard, JobSort, JobsSection, Pay } from "@/lib/types";
import { Badge, EmptyState, Notes, SortToggle } from "./ui";

const TIER = {
  strong_match: { label: "Strong match", tone: "ok" },
  possible_match: { label: "Possible match — confirm details", tone: "brand" },
  known_gaps: { label: "Has requirements you may not meet yet", tone: "warn" },
} as const;

const REQ_LABEL: Record<string, string> = {
  education_required: "Education",
  experience_required: "Experience",
  certification_required: "License or certificate",
};

export function payText(p: Pay): string {
  if (p.min == null && p.max == null) return p.raw_text ?? "Pay not listed";
  const digits = p.period === "hour" ? 2 : 0;
  const lo = money(p.min ?? p.max, digits);
  const hi = money(p.max ?? p.min, digits);
  return `${lo === hi ? lo : `${lo}–${hi}`}${p.period ? ` per ${p.period}` : " (pay period not stated)"}`;
}

function Card({ j, onCompare }: { j: JobCard; onCompare: (j: JobCard) => void }) {
  const tier = TIER[j.suitability_tier];
  const hasPay = j.pay.min != null || j.pay.max != null;
  return (
    <li className="rounded-xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <h4 className="text-lg font-semibold break-words">{j.title}</h4>
          <p className="text-sm text-muted">
            {[j.employer, j.location.city ?? j.location.text].filter(Boolean).join(" · ") || "Employer not listed"}
          </p>
        </div>
        <p className="shrink-0 font-semibold">{payText(j.pay)}</p>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Badge tone={tier.tone}>{tier.label}</Badge>
        {j.posted_date && <span className="text-sm text-muted">Posted {j.posted_date}</span>}
        <span className="text-sm text-muted">
          {j.location.distance_miles != null
            ? `About ${j.location.distance_miles} mi from the ${j.location.reference_point}`
            : "Exact distance unknown"}
        </span>
      </div>

      <p className="mt-2 text-sm">{j.rank_explanation}</p>
      {j.pay.conversion_note && <p className="mt-1 text-sm text-muted">{j.pay.conversion_note}</p>}

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer font-medium text-brand-dark">Requirements and how you match</summary>
        <div className="mt-2 space-y-2">
          {j.matches.length > 0 && <p><span className="font-medium text-ok">Matches: </span>{j.matches.join("; ")}</p>}
          {j.gaps.length > 0 && <p><span className="font-medium text-warn">Possible gaps: </span>{j.gaps.join("; ")}</p>}
          {j.unknowns.length > 0 && <p><span className="font-medium">To confirm: </span>{j.unknowns.join("; ")}</p>}
          {j.requirements.map((r) => (
            <div key={r.label} className="rounded-lg bg-paper p-3">
              <p className="font-medium">
                {REQ_LABEL[r.label] ?? r.label}:{" "}
                {r.status === "required" ? "required" : r.status === "preferred" ? "preferred, not required"
                  : r.status === "not_found" ? "none found in the posting" : "unclear"}
              </p>
              {r.evidence && <p className="mt-1 text-muted">From the posting: &ldquo;{r.evidence}&rdquo;</p>}
            </div>
          ))}
          <p className="text-muted">
            Requirements are read from the posting by a model and can be wrong. Check the original posting.
          </p>
        </div>
      </details>

      <div className="mt-3 flex flex-wrap gap-2 text-sm font-medium">
        {j.url && (
          <a className="rounded-lg bg-brand px-3 py-1.5 text-white hover:bg-brand-dark" href={j.url} target="_blank" rel="noopener noreferrer">
            View original posting
          </a>
        )}
        {hasPay && (
          <button type="button" className="rounded-lg border border-line px-3 py-1.5 hover:border-brand" onClick={() => onCompare(j)}>
            Compare this pay with rent
          </button>
        )}
      </div>
    </li>
  );
}

export default function JobsTab({ data, loading, onSort, onCompare }: {
  data: JobsSection; loading: boolean; onSort: (s: JobSort) => void; onCompare: (j: JobCard) => void;
}) {
  if (data.status === "not_integrated")
    return (
      <EmptyState title="Job matching isn't connected yet">
        This tab will list jobs that fit your experience, with pay and requirements from each posting.
      </EmptyState>
    );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">A listing doesn&apos;t guarantee the job is still open. Age is never used to rank jobs.</p>
        <SortToggle
          label="Sort jobs" value={data.sort} disabled={loading} onChange={onSort}
          options={[{ value: "highest_pay", label: "Highest pay" }, { value: "nearest", label: "Nearest" }]}
        />
      </div>
      <Notes notes={data.notes} />
      {data.groups.every((g) => g.items.length === 0) ? (
        <EmptyState title="No matching jobs found here">Try a nearby city or add more skills to your answers.</EmptyState>
      ) : (
        data.groups.filter((g) => g.items.length > 0).map((g) => (
          <section key={g.key}>
            <h3 className="mb-2 text-lg font-semibold">
              {g.label}{" "}
              <span className="text-sm font-normal text-muted">
                {g.total > g.items.length ? `showing ${g.items.length} of ${g.total}` : g.total}
              </span>
            </h3>
            <ul className="grid gap-3 lg:grid-cols-2">
              {g.items.map((j) => <Card key={j.job_id} j={j} onCompare={onCompare} />)}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}

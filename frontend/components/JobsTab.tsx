"use client";

import { payText } from "@/lib/jobs";
import type { JobCard, JobSort, JobsSection } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, EmptyState, Notes, SortToggle } from "./shared";

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

function JobItem({ j, selected, loading, onSelect, onCompare }: {
  j: JobCard; selected: boolean; loading: boolean;
  onSelect: (j: JobCard) => void; onCompare: (j: JobCard) => void;
}) {
  const tier = TIER[j.suitability_tier];
  const hasPay = j.pay.period != null && (j.pay.min != null || j.pay.max != null);
  const ruleBased = j.requirements.some((r) => r.source === "rule_extraction");
  const unrankedSnapshot = j.source?.dataset === "Indeed";
  return (
    <li>
      <Card className="h-full gap-0 p-4 text-base">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <h4 className="text-lg font-semibold break-words">{j.title}</h4>
          <p className="text-sm text-muted-foreground">
            {[j.employer, j.location.city ?? j.location.text].filter(Boolean).join(" · ") || "Employer not listed"}
          </p>
        </div>
        <p className="shrink-0 font-semibold">{payText(j.pay)}</p>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Badge tone={tier.tone}>{unrankedSnapshot ? "Confirm fit" : tier.label}</Badge>
        {j.posted_date && <span className="text-sm text-muted-foreground">Posted {j.posted_date}</span>}
        <span className="text-sm text-muted-foreground">
          {j.location.distance_miles != null
            ? `About ${j.location.distance_miles} mi from the ${j.location.reference_point}`
            : "Exact distance unknown"}
        </span>
      </div>

      <p className="mt-2 text-sm">{j.rank_explanation}</p>
      {j.pay.conversion_note && <p className="mt-1 text-sm text-muted-foreground">{j.pay.conversion_note}</p>}

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer font-medium text-brand-text">{unrankedSnapshot ? "Requirements from the posting" : "Requirements and how you match"}</summary>
        <div className="mt-2 space-y-2">
          {j.matches.length > 0 && <p><span className="font-medium text-ok">Matches: </span>{j.matches.join("; ")}</p>}
          {j.gaps.length > 0 && <p><span className="font-medium text-warn">Possible gaps: </span>{j.gaps.join("; ")}</p>}
          {j.unknowns.length > 0 && <p><span className="font-medium">To confirm: </span>{j.unknowns.join("; ")}</p>}
          {j.requirements.map((r) => (
            <div key={r.label} className="rounded-lg bg-muted p-3">
              <p className="font-medium">
                {REQ_LABEL[r.label] ?? r.label}:{" "}
                {r.status === "required" ? (ruleBased ? "requirement detected" : "required")
                  : r.status === "preferred" ? "preferred, not required"
                  : r.status === "not_found" ? "not detected in the posting" : "unknown"}
              </p>
              {r.evidence && <p className="mt-1 text-muted-foreground">From the posting: &ldquo;{r.evidence}&rdquo;</p>}
            </div>
          ))}
          <p className="text-muted-foreground">
            {ruleBased ? "Requirement flags come from an automated text scan. Check the original posting."
              : "Requirements are read from the posting by a model and can be wrong. Check the original posting."}
          </p>
        </div>
      </details>

      <div className="mt-3 flex flex-wrap gap-2 text-sm font-medium">
        <Button type="button" variant={selected ? "secondary" : "default"} size="lg"
          disabled={loading || j.selectable === false} aria-pressed={selected}
          aria-label={`${selected ? "Selected target" : "Choose target"}: ${j.title}`}
          onClick={() => onSelect(j)}>
          {selected ? "Selected target job" : "Choose as target job"}
        </Button>
        {j.url && (
          <Button asChild variant="outline" size="lg">
            <a href={j.url} target="_blank" rel="noopener noreferrer">View original posting</a>
          </Button>
        )}
        {hasPay && (
          <Button type="button" variant="outline" size="lg" onClick={() => onCompare(j)}>
            Compare this pay with rent
          </Button>
        )}
      </div>
      </Card>
    </li>
  );
}

export default function JobsTab({ data, loading, selectedJobId, onSelect, onSort, onCompare }: {
  data: JobsSection; loading: boolean; onSort: (s: JobSort) => void; onCompare: (j: JobCard) => void;
  selectedJobId: string | null; onSelect: (j: JobCard) => void;
}) {
  if (data.status === "not_integrated")
    return (
      <EmptyState title="Jobs are unavailable">
        {data.notes.join(" ")}
      </EmptyState>
    );
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Choose a target job to build your 30-day plan. You can choose one with requirements you still need to work toward.
      </p>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">A listing doesn&apos;t guarantee the job is still open. Age is never used to rank jobs.</p>
        <SortToggle
          label="Sort jobs" value={data.sort} disabled={loading} onChange={onSort}
          options={[{ value: "highest_pay", label: "Highest pay" }, { value: "nearest", label: "Nearest" }]}
        />
      </div>
      <Notes notes={data.notes} />
      {data.groups.every((g) => g.items.length === 0) ? (
        <EmptyState title="No job listings found for this location" />
      ) : (
        data.groups.filter((g) => g.items.length > 0).map((g) => (
          <section key={g.key}>
            <h3 className="mb-2 text-lg font-semibold">
              {g.label}{" "}
              <span className="text-sm font-normal text-muted-foreground">
                {g.total > g.items.length ? `showing ${g.items.length} of ${g.total}` : g.total}
              </span>
            </h3>
            <ul className="grid gap-3 lg:grid-cols-2">
              {g.items.map((j) => <JobItem key={j.job_id} j={j} selected={j.job_id === selectedJobId}
                loading={loading} onSelect={onSelect} onCompare={onCompare} />)}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}

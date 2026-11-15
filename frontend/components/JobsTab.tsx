"use client";

import { payText } from "@/lib/jobs";
import { matchLabel, qualificationProgress } from "@/lib/qualifications";
import type { JobCard, JobSort, JobsSection } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge, EmptyState, Notes, SortToggle } from "./shared";

const CHECK_STATUS = {
  reported_met: "Reported met", gap: "Needs preparation", needs_confirmation: "Confirm", preferred: "Preferred",
} as const;
const REQ_LABEL: Record<string, string> = {
  education_required: "Education", experience_required: "Experience", certification_required: "License or certificate",
};

function groupLabel(key: string, fallback: string) {
  const [tier, basis] = key.split(":");
  const labels: Record<string, string> = { strong_match: "Reported requirements align", possible_match: "Requirements to confirm", known_gaps: "Preparation needed" };
  const pay = basis === "USD/hour" ? "Hourly pay" : basis === "USD/year" ? "Annual pay"
    : basis === "pay_needs_confirmation" ? "Pay to confirm" : basis?.replace("USD/", "Pay per ");
  return labels[tier] ? `${labels[tier]}${pay ? ` · ${pay}` : ""}` : fallback;
}

function JobItem({ j, selected, loading, onSelect, onCompare, onQualificationChange }: {
  j: JobCard; selected: boolean; loading: boolean;
  onSelect: (j: JobCard) => void; onCompare: (j: JobCard) => void;
  onQualificationChange: (job: JobCard, key: string, checked: boolean) => void;
}) {
  const relevance = matchLabel(j);
  const progress = qualificationProgress(j);
  const hasPay = !j.pay.needs_confirmation && j.pay.period != null && (j.pay.min != null || j.pay.max != null);
  const requirements = j.requirements.filter((r) => r.status === "required" || r.status === "preferred");
  const checks = j.qualification_checks ?? [];
  return (
    <li>
      <Card className="h-full gap-3">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <CardTitle><h4 className="text-lg font-semibold leading-snug break-words">{j.title}</h4></CardTitle>
            {j.location.distance_miles != null && (
              <span className="text-xs text-muted-foreground" title={`From ${j.location.reference_point ?? "the area center"}; straight-line distance`}>
                {j.location.distance_miles.toFixed(1)} mi
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {[j.employer, j.location.city ?? j.location.text].filter(Boolean).join(" · ") || "Employer not listed"}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Relevance</span>
            <Badge tone={relevance === "Clear match" ? "ok" : relevance === "Needs preparation" ? "warn" : "brand"}>{relevance}</Badge>
            {relevance === "Clear match" && <span className="text-xs text-muted-foreground">To listed mandatory requirements</span>}
          </div>
          <div className="mt-2 flex flex-col gap-2">
            <p className="text-sm font-medium">Qualifications you have</p>
            {progress.total > 0 && <p className="text-xs text-muted-foreground" aria-live="polite">
              {progress.required > 0 ? `${progress.requiredMet} of ${progress.required} required met · ` : ""}{progress.reported} of {progress.total} listed reported
            </p>}
            {checks.length === 0 && <p className="text-sm text-muted-foreground">Specific requirements need employer confirmation.</p>}
            <ul className="flex flex-col gap-2" aria-label={`Qualifications for ${j.title}`}>
              {checks.map((check) => (
                <li key={check.key} className="flex items-start gap-2 text-sm">
                  <Checkbox id={`${j.job_id}-${check.key}`} className="mt-0.5" disabled={loading} checked={check.status === "reported_met"}
                    aria-label={`I have ${check.label}`} onCheckedChange={(value) => onQualificationChange(j, check.key, value === true)} />
                  <label htmlFor={`${j.job_id}-${check.key}`} className="cursor-pointer leading-snug">
                    {check.label}<span className="block text-xs text-muted-foreground">{check.requirement_kind === "required" ? "Required" : check.requirement_kind === "preferred" ? "Preferred" : "Confirm with employer"} · {CHECK_STATUS[check.status]}</span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
          <p className="mt-2 text-lg font-semibold">{payText(j.pay)}</p>
        </CardHeader>
        <CardContent>
          <details className="text-sm">
            <summary className="cursor-pointer font-medium text-brand-text">Job description</summary>
            <div className="mt-3 flex flex-col gap-3">
              {j.description ? (
                <p className="max-h-72 overflow-y-auto overscroll-contain whitespace-pre-line leading-relaxed text-muted-foreground">{j.description}</p>
              ) : <p className="text-muted-foreground">Read the original posting for the full job description.</p>}
              <div className="flex flex-col gap-2">
                <h5 className="font-semibold">What you&apos;ll need</h5>
                {checks.map((check) => <p key={check.key}><span className="font-medium">{check.label}: </span>{check.detail}</p>)}
                {requirements.length ? requirements.map((r, index) => (
                  <p key={`${r.label}-${index}`}>
                    <span className="font-medium">{REQ_LABEL[r.label] ?? r.label}</span>
                    {r.status === "preferred" ? " (preferred)" : " (required)"}
                    {r.evidence && <span className="block text-muted-foreground">{r.evidence}</span>}
                  </p>
                )) : <p className="text-muted-foreground">Confirm qualifications with the employer.</p>}
                {j.gaps.length > 0 && <p className="text-warn">To work on: {j.gaps.join("; ")}</p>}
                {j.matches.length > 0 && <p className="text-ok">Relevant skills: {j.matches.join(", ")}</p>}
              </div>
              <details className="text-muted-foreground">
                <summary className="cursor-pointer">Listing and match details</summary>
                <div className="mt-2 flex flex-col gap-2">
                  {j.posted_date && <p>Posted {j.posted_date.slice(0, 10)}</p>}
                  <p>{j.rank_explanation}</p>
                  {j.unknowns.map((note) => <p key={note}>{note}</p>)}
                  {j.pay.conversion_note && <p>{j.pay.conversion_note}</p>}
                  {j.pay.needs_confirmation && j.pay.raw_text && <p>Source pay text: {j.pay.raw_text}</p>}
                  <p>Confirm the full posting and current opening with the employer.</p>
                </div>
              </details>
              {hasPay && <Button type="button" variant="outline" className="self-start" onClick={() => onCompare(j)}>Compare pay with rent</Button>}
            </div>
          </details>
        </CardContent>
        <CardFooter className="mt-auto flex-wrap gap-2">
          <Button type="button" variant={selected ? "secondary" : "default"}
            disabled={loading || j.selectable === false} aria-pressed={selected}
            aria-label={`${selected ? "View plan" : "Make a plan"}: ${j.title}`} onClick={() => onSelect(j)}>
            {selected ? "View my plan" : "Make a plan"}
          </Button>
          {j.url && <Button asChild variant="outline"><a href={j.url} target="_blank" rel="noopener noreferrer">View posting</a></Button>}
        </CardFooter>
      </Card>
    </li>
  );
}

export default function JobsTab({ data, loading, selectedJobId, onSelect, onSort, onCompare, onQualificationChange }: {
  data: JobsSection; loading: boolean; onSort: (s: JobSort) => void; onCompare: (j: JobCard) => void;
  selectedJobId: string | null; onSelect: (j: JobCard) => void;
  onQualificationChange: (job: JobCard, key: string, checked: boolean) => void;
}) {
  if (data.status === "not_integrated") return <EmptyState title="Jobs are unavailable">{data.notes.join(" ")}</EmptyState>;
  const mainGroups = data.groups.filter((group) => group.items.length > 0);
  const otherGroups = (data.other_groups ?? []).filter((group) => group.items.length > 0);
  const otherTotal = otherGroups.reduce((total, group) => total + group.total, 0);
  const renderGroups = (groups: JobsSection["groups"]) => groups.map((g) => (
    <section key={g.key}>
      <h3 className="mb-3 flex flex-wrap items-baseline gap-2 text-base font-semibold">
        {groupLabel(g.key, g.label)}
        <span className="text-sm font-normal text-muted-foreground">{g.total > g.items.length ? `${g.items.length} of ${g.total}` : g.total}</span>
      </h3>
      <ul className="grid gap-4 md:grid-cols-2">
        {g.items.map((j) => <JobItem key={j.job_id} j={j} selected={j.job_id === selectedJobId}
          loading={loading} onSelect={onSelect} onCompare={onCompare} onQualificationChange={onQualificationChange} />)}
      </ul>
    </section>
  ));
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-md text-sm text-muted-foreground">Find a role to work toward. Choose one to build your 30-day plan.</p>
        <SortToggle label="Sort jobs" value={data.sort} disabled={loading} onChange={onSort}
          options={[{ value: "highest_pay", label: "Highest pay" }, { value: "nearest", label: "Nearest" }]} />
      </div>
      <details className="text-sm text-muted-foreground">
        <summary className="cursor-pointer font-medium text-brand-text">How relevance and qualifications work</summary>
        <div className="mt-2 flex flex-col gap-2">
          <p><strong>Relevance:</strong> overlap between your reported work areas and the job title. It does not establish that you meet the job&apos;s requirements.</p>
          <p><strong>Clear match:</strong> you report meeting every listed mandatory qualification. We may not have extracted every requirement; confirm the full posting and vacancy.</p>
          <p><strong>Needs preparation:</strong> none of the listed mandatory qualifications is reported met, and at least one is reported missing. Skipped answers alone do not create this label.</p>
          <p>Check only qualifications you already have. Uncheck any you do not have. Your choices update this job&apos;s match and plan while you browse.</p>
          <p>Preferred qualifications are optional and do not block a clear match. The employer still needs to verify your qualifications.</p>
        </div>
      </details>
      <Notes notes={data.notes} />
      {!mainGroups.length ? <EmptyState title={otherGroups.length ? "No roles matched your reported experience" : "No job listings found for this location"} />
        : renderGroups(mainGroups)}
      {otherGroups.length > 0 && (
        <details>
          <summary className="cursor-pointer py-3 font-semibold text-brand-text focus-visible:outline-offset-4">
            Explore other nearby roles ({otherTotal.toLocaleString()})
          </summary>
          <p className="mt-1 mb-4 text-sm text-muted-foreground">
            These roles differ from your reported work areas. Check transferable skills and qualifications, or choose one to build a preparation plan.
          </p>
          <div className="flex flex-col gap-5">{renderGroups(otherGroups)}</div>
        </details>
      )}
    </div>
  );
}

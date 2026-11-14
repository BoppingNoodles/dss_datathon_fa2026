"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { interimPay, payText } from "@/lib/jobs";
import type { InterimJob, PlanLink, ThirtyDayPlan } from "@/lib/types";

const TRACKS = {
  job_confirmation: "Confirm the job",
  credential: "Training and credentials",
  interim_work: "Interim work",
  application: "Apply and follow up",
  experience: "Build experience",
};
const REQUIREMENTS = {
  required: "Required in the posting",
  preferred: "Preferred in the posting",
  alternative: "One possible qualification pathway",
  uncertain: "Confirm whether this is needed",
};

function PlanLinks({ links }: { links: PlanLink[] }) {
  if (!links.length) return null;
  return (
    <ul className="flex flex-col items-start gap-2">
      {links.map((link) => (
        <li key={`${link.role}:${link.url}`}>
          <a href={link.url} target="_blank" rel="noopener noreferrer" className="text-brand-text underline">
            {link.label}
          </a>
        </li>
      ))}
    </ul>
  );
}

export default function JobPlan({ plan, loading, completed, onToggleStep, onSelectInterim, onClear, onCompareInterim }: {
  plan: ThirtyDayPlan;
  loading: boolean;
  completed: string[];
  onToggleStep: (stepId: string, checked: boolean) => void;
  onSelectInterim: (jobId: string | null) => void;
  onClear: () => void;
  onCompareInterim: (job: InterimJob) => void;
}) {
  const selectedInterim = plan.interim_jobs.find((job) => job.job_id === plan.selected_interim_job_id);
  const checkedCount = plan.steps.filter((step) => completed.includes(step.step_id)).length;
  const stepTitles = new Map(plan.steps.map((step) => [step.step_id, step.title]));

  return (
    <Card id="job-plan" role="region" tabIndex={-1} aria-labelledby="job-plan-title" aria-busy={loading} className="mb-6 scroll-mt-4">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <CardTitle><h2 id="job-plan-title" className="text-xl font-semibold">Your 30-day plan</h2></CardTitle>
          <Button type="button" variant="outline" disabled={loading} onClick={onClear}>Clear target and plan</Button>
        </div>
        <CardDescription>
          Target job: <strong className="text-foreground">{plan.target_job_title}</strong>
        </CardDescription>
        <p className="text-sm text-muted-foreground">
          This is a preparation plan. Hiring, funding, and certification within 30 days need confirmation.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {plan.credential_paths.length > 0 && (
          <section aria-labelledby="credential-paths" className="flex flex-col gap-3">
            <h3 id="credential-paths" className="font-semibold">Credentials to check</h3>
            {plan.credential_paths.map((path) => (
              <details key={path.credential} className="text-sm">
                <summary className="cursor-pointer">
                  <span className="font-medium">{path.credential}</span>{" · "}
                  {path.user_status === "reported_held" ? "You reported holding this" : REQUIREMENTS[path.requirement_kind]}
                </summary>
                <div className="mt-2 flex flex-col gap-3 pl-4">
                  <p>{path.job_evidence}</p>
                  <PlanLinks links={path.links} />
                </div>
              </details>
            ))}
          </section>
        )}

        <fieldset className="min-w-0">
          <legend className="mb-2 font-semibold">Work while preparing (optional)</legend>
          <p id="interim-help" className="mb-3 text-sm text-muted-foreground">
            Choose an interim job to pursue while working toward your target. Confirm the full requirements, opening, and shifts with the employer.
          </p>
          <ToggleGroup type="single" variant="outline" orientation="vertical" spacing={2}
            aria-label="Interim job" aria-describedby="interim-help" disabled={loading}
            value={plan.selected_interim_job_id ?? "none"} className="w-full"
            onValueChange={(value) => {
              const id = value && value !== "none" ? value : null;
              if (id !== plan.selected_interim_job_id) onSelectInterim(id);
            }}>
            <ToggleGroupItem value="none" className="h-auto w-full justify-start whitespace-normal px-3 py-3 text-left">
              No interim job for now
            </ToggleGroupItem>
            {plan.interim_jobs.map((job) => (
              <ToggleGroupItem key={job.job_id} value={job.job_id} aria-label={`Interim job: ${job.title} at ${job.company}`}
                className="h-auto w-full min-w-0 flex-col items-start gap-1 whitespace-normal px-3 py-3 text-left">
                <span className="font-semibold">{job.title}</span>
                <span>{job.company} · {payText(interimPay(job))}</span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {plan.interim_jobs.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              No interim matches were identified. Use the job-center link in your plan to ask about other options.
            </p>
          )}
          {selectedInterim && (
            <div className="mt-3 flex flex-col items-start gap-3 text-sm" role="region" aria-label="Selected interim job">
              <p><strong>Selected interim job:</strong> {selectedInterim.title} · {selectedInterim.company}</p>
              <ul className="flex list-disc flex-col gap-1 pl-5">
                {selectedInterim.confirmation_needed.map((note) => <li key={note}>{note}</li>)}
              </ul>
              <div className="flex flex-wrap gap-2">
                {selectedInterim.source_url && (
                  <Button asChild variant="outline">
                    <a href={selectedInterim.source_url} target="_blank" rel="noopener noreferrer">View interim posting</a>
                  </Button>
                )}
                <Button type="button" variant="outline" disabled={loading} onClick={() => onCompareInterim(selectedInterim)}>
                  Compare interim pay with rent
                </Button>
              </div>
            </div>
          )}
        </fieldset>

        <section aria-labelledby="plan-steps" className="flex flex-col gap-3">
          <h3 id="plan-steps" className="font-semibold">Your steps</h3>
          <p className="text-sm text-muted-foreground" role="status">
            {checkedCount} of {plan.steps.length} steps checked. Expand a step for instructions and links. Progress clears when you refresh.
          </p>
          <ol className="flex flex-col gap-4">
            {plan.steps.map((step, index) => (
              <li key={step.step_id} className="flex items-start gap-3">
                <Checkbox id={`plan-step-${step.step_id}`} aria-label={`Mark step complete: ${step.title}`}
                  className="mt-1 size-5 shrink-0" checked={completed.includes(step.step_id)}
                  onCheckedChange={(value) => onToggleStep(step.step_id, value === true)} />
                <details className="min-w-0 flex-1" open={index === 0 || undefined}>
                  <summary className="cursor-pointer">
                    <span className="text-sm text-muted-foreground">Days {step.day_start}–{step.day_end} · {TRACKS[step.track]}</span>
                    <span className="block font-medium">{step.title}</span>
                  </summary>
                  <div className="mt-2 flex flex-col gap-3 text-sm">
                    <p>{step.action}</p>
                    {step.depends_on.length > 0 && (
                      <p className="text-muted-foreground">
                        Before this step: {step.depends_on.map((id) => stepTitles.get(id) ?? id).join("; ")}.
                      </p>
                    )}
                    <PlanLinks links={step.links} />
                  </div>
                </details>
              </li>
            ))}
          </ol>
        </section>

        <details className="text-sm text-muted-foreground">
          <summary className="cursor-pointer font-medium">About this plan</summary>
          <ul className="mt-2 flex list-disc flex-col gap-2 pl-5">
            {plan.notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </details>
      </CardContent>
    </Card>
  );
}

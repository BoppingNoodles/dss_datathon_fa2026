"use client";

import JobPlan from "@/components/JobPlan";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { savedPlanDate } from "@/lib/saved-session";
import type { Need, ReentryPlan as Plan, ReentryTask, Tab } from "@/lib/types";

const STAGES = [
  { key: "immediate_stability", label: "Immediate stability" },
  { key: "removing_barriers", label: "Removing barriers" },
  { key: "building_independence", label: "Building independence" },
] as const;
const SERVICE_LABELS: Record<Need, string> = { housing: "housing support", work: "employment support", food: "food support", health_care: "health care", transportation: "transportation support", community_support: "community support" };

const safeUrl = (url: string | null) => url && /^https?:\/\//i.test(url) ? url : null;

function Task({ task, tasks, disabled, prefix, onToggle, onOpenResources }: {
  task: ReentryTask; tasks: ReentryTask[]; disabled: boolean; prefix: string;
  onToggle: (id: string, checked: boolean) => void;
  onOpenResources?: (tab: Tab, need?: Need) => void;
}) {
  const inputId = `${prefix}-${task.task_id}`;
  return <li className="flex items-start gap-3 rounded-lg border border-border bg-card p-4">
    <Checkbox id={inputId} className="mt-1 shrink-0" checked={task.status === "completed"}
      disabled={disabled || task.status === "waiting"} onCheckedChange={(v) => {
        onToggle(task.task_id, v === true);
        // Completing a next step removes that card. Keep keyboard navigation in
        // the next-step list instead of losing focus to the page body.
        if (prefix === "next" && v === true) requestAnimationFrame(() => {
          document.querySelector<HTMLButtonElement>('[aria-label="Next recommended steps"] [role="checkbox"]')?.focus({ preventScroll: true });
        });
      }} />
    <div className="flex min-w-0 flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={inputId} className={cn("cursor-pointer font-semibold", task.status === "completed" && "text-muted-foreground line-through")}>{task.title}</label>
        <Badge variant={task.priority === "immediate" ? "destructive" : "secondary"} className="capitalize">{task.priority}</Badge>
      </div>
      <p>{task.action}</p>
      <p className="text-muted-foreground">Why: {task.rationale}</p>
      {onOpenResources && task.resource_tab && <Button type="button" disabled={disabled} variant="link" className="h-auto self-start whitespace-normal p-0 text-left text-brand-text" onClick={() => onOpenResources(task.resource_tab!, task.resource_need ?? undefined)}>{task.resource_tab === "jobs" ? "Explore jobs for this step" : task.resource_tab === "housing" ? "Explore housing costs" : `Find ${SERVICE_LABELS[task.resource_need ?? "community_support"]}`}</Button>}
      {task.deadline && <p className="text-muted-foreground">Plan by {task.deadline} · based on your reported timing</p>}
      {task.prerequisites.length > 0 && <p className="text-muted-foreground">First: {task.prerequisites.map((id) => tasks.find((t) => t.task_id === id)?.title ?? id).join("; ")}{task.status === "waiting" ? " (waiting)" : ""}.</p>}
      {task.confirmations.length > 0 && <details className="text-muted-foreground"><summary className="cursor-pointer">What to confirm</summary><ul className="mt-2 flex list-disc flex-col gap-1 pl-4">{task.confirmations.map((text) => <li key={text}>{text}</li>)}</ul></details>}
      {task.links.filter((link) => safeUrl(link.url)).map((link) => <a key={link.url} className="inline-block text-brand-text underline underline-offset-4" href={link.url} target="_blank" rel="noopener noreferrer">{link.label}</a>)}
      {task.referrals.length > 0 && <details>
        <summary className="cursor-pointer font-medium text-brand-text">Candidate resources · contact to confirm ({task.referrals.length})</summary>
        <ul className="mt-3 flex flex-col gap-3">
          {task.referrals.map((referral) => <li key={referral.resource_id} className="flex flex-col gap-1">
            {safeUrl(referral.url) ? <a className="font-medium text-brand-text underline underline-offset-4" href={referral.url!} target="_blank" rel="noopener noreferrer">{referral.name}</a> : <p className="font-medium">{referral.name}</p>}
            <p className="text-xs text-muted-foreground">{referral.verification === "verified_reentry_scope" ? "Reentry service scope checked" : referral.verification === "verified_general_service" ? "General service checked; reentry scope unverified" : "Unverified resource"}{referral.checked_on ? ` · ${referral.checked_on}` : ""}</p>
            <p className="text-muted-foreground">{referral.scope}</p>
            <p className="text-muted-foreground">{referral.confirmation}</p>
            {safeUrl(referral.source_url) && <a className="text-xs text-brand-text underline" href={referral.source_url!} target="_blank" rel="noopener noreferrer">Scope source</a>}
          </li>)}
        </ul>
      </details>}
    </div>
  </li>;
}

export default function ReentryPlan({ plan, disabled, onToggle, heading = "Your Reentry Plan", onOpenResources }: {
  plan: Plan; disabled: boolean; onToggle: (id: string, checked: boolean) => void;
  heading?: string; onOpenResources?: (tab: Tab, need?: Need) => void;
}) {
  const next = plan.next_task_ids.flatMap((id) => plan.tasks.filter((t) => t.task_id === id));
  const dayTasks = Object.fromEntries(plan.daily_actions.map((day) => [day.action_id, plan.tasks.filter((task) => day.task_ids.includes(task.task_id))]));
  const blocked = plan.daily_actions.filter((day) => dayTasks[day.action_id].some((task) => task.status === "waiting")).map((day) => day.action_id);
  const start = savedPlanDate(plan.start_date);
  return <Card className="mt-5 gap-4" aria-labelledby="reentry-plan-title">
    <CardHeader className="gap-2">
      <CardTitle><h2 id="reentry-plan-title" className="text-xl">{heading}</h2></CardTitle>
      <p className="text-sm text-muted-foreground">Start with these next steps. You can work on independent steps together.</p>
      <p role="status" className="text-sm text-muted-foreground">{plan.tasks.filter((task) => task.status === "completed").length} of {plan.tasks.length} steps marked complete</p>
      {plan.synthetic && <p className="text-sm font-medium text-warn">Fictional demo resources — for testing only.</p>}
    </CardHeader>
    <CardContent className="flex flex-col gap-5">
      <ol aria-label="Reentry priorities" className="grid gap-3 md:grid-cols-3">{STAGES.map((stage, index) => {
        const tasks = plan.tasks.filter((task) => task.stage === stage.key);
        const completed = tasks.filter((task) => task.status === "completed").length;
        return <li key={stage.key} className="rounded-lg bg-muted/50 p-3 text-sm"><p className="font-semibold">{index + 1}. {stage.label}</p><p className="mt-1 text-xs text-muted-foreground">{tasks.length ? `${completed} of ${tasks.length} steps marked complete` : "No steps from your answers"}</p></li>;
      })}</ol>
      <ol aria-label="Next recommended steps" className="grid gap-3 md:grid-cols-3">{next.map((task) => <Task key={task.task_id} task={task} tasks={plan.tasks} disabled={disabled} prefix="next" onToggle={onToggle} onOpenResources={onOpenResources} />)}</ol>
      {next.length === 0 && <p className="text-sm">You have marked these steps complete. Review your progress and update your answers when your needs change.</p>}
      <p className="text-xs text-muted-foreground">Contact to confirm services, cost, eligibility, and availability. A positive review does not confirm reentry eligibility.</p>
      <details><summary className="cursor-pointer text-sm font-medium text-brand-text">All steps and prerequisites</summary>
        <ul className="mt-3 flex flex-col gap-3">{plan.tasks.map((task) => <Task key={task.task_id} task={task} tasks={plan.tasks} disabled={disabled} prefix="all" onToggle={onToggle} onOpenResources={onOpenResources} />)}</ul>
      </details>
      <details><summary className="cursor-pointer text-sm font-medium text-brand-text">Open your 30-day roadmap</summary>
        {start && <div className="mt-4"><JobPlan key={plan.start_date} idPrefix="reentry-calendar"
          plan={{ daily_actions: plan.daily_actions, credential_paths: [], steps: [], notes: plan.notes, target_job_title: "Your next reentry steps" }}
          startDate={start} loading={disabled} completed={plan.completed_ids} onToggleStep={onToggle} dayTasks={dayTasks} blockedActionIds={blocked} /></div>}
      </details>
      <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">How to use this plan</summary><ul className="mt-2 flex list-disc flex-col gap-1 pl-4">{plan.notes.map((note) => <li key={note}>{note}</li>)}</ul></details>
    </CardContent>
  </Card>;
}

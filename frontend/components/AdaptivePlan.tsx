"use client";

import { useEffect, useMemo, useState } from "react";
import type { PlanTask, UserEvent } from "@/lib/domain";
import { userEvent } from "@/lib/domain";
import { circumstances, planTasks, resourceLabel, stableTaskOrder, taskProgress } from "@/lib/plan-view";
import { Button } from "./ui/button";
import PlanTaskCard, { TASK_STATUS, type TaskActions } from "./PlanTaskCard";
import ResourceActions from "./ResourceActions";

export default function AdaptivePlan(props: TaskActions & { onOpenCalendar: () => void; onEditSituation: () => void }) {
  const { session } = props;
  const progress = taskProgress(session);
  const targets = session.recommendations.filter(r => session.selectedRecommendationIds.includes(r.id) && !["dismissed", "rejected"].includes(r.userStatus));
  const chosen = (label: string) => targets.filter(r => label === "Housing" ? r.category === "housing" : label === "Employment" ? r.category === "job" : false).map(r => r.title).join(", ");
  const [taskOrder, setTaskOrder] = useState(() => planTasks(session).map(task => task.id));
  const tasks = useMemo(() => stableTaskOrder(planTasks(session), taskOrder), [session, taskOrder]);
  const [openIds, setOpenIds] = useState<string[]>([]);
  const [startError, setStartError] = useState<{ taskId: string; message: string } | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const ids = tasks.map(task => task.id);
    setTaskOrder(previous => previous.length === ids.length && previous.every((id, i) => id === ids[i]) ? previous : ids);
  }, [tasks]);
  function open(task: PlanTask) {
    setOpenIds(previous => previous.includes(task.id) ? previous : [...previous, task.id]);
    setStartError(null); setNotice("");
  }
  async function start(task: PlanTask) {
    open(task);
    if (task.status !== "in_progress") {
      const saved = await props.onEvent(userEvent("task_status", { taskId: task.id, status: "in_progress", notes: task.notes }));
      if (!saved) setStartError({ taskId: task.id, message: "The start could not be saved. Try again." });
    }
  }
  async function update(event: UserEvent) {
    const saved = await props.onEvent(event);
    if (saved && ["completed", "blocked", "skipped"].includes(String(event.payload.status))) {
      setNotice(event.payload.status === "completed" ? "Step completed." : event.payload.status === "blocked" ? "Step marked blocked." : "Step skipped.");
    }
    return saved;
  }
  const card = (task: PlanTask) => <PlanTaskCard key={task.id} task={task} {...props} onEvent={update} onStart={task => { void start(task); }} onOpen={open} open={openIds.includes(task.id)} startError={startError?.taskId === task.id ? startError.message : ""} onClose={() => setOpenIds(previous => previous.filter(id => id !== task.id))} />;
  return <div className="mt-4 space-y-6">
    <section aria-label="Plan summary" className="rounded-xl border bg-card p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 aria-live="polite" aria-atomic="true" className="text-lg font-semibold">{progress.left} {progress.left === 1 ? "step" : "steps"} left <span className="font-normal text-muted-foreground">· {progress.completed} complete</span></h2><Button type="button" variant="outline" onClick={props.onOpenCalendar}>View calendar</Button></div>
      <div role="progressbar" aria-label="Completed tasks" aria-valuemin={0} aria-valuemax={progress.total || 1} aria-valuenow={progress.completed} aria-valuetext={`${progress.completed} of ${progress.total} tasks completed`} className="mt-4 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-ok transition-[width] motion-reduce:transition-none" style={{ width: `${progress.percent}%` }} /></div>
      <p className="mt-2 text-xs text-muted-foreground">{progress.percent}% complete{progress.skipped ? ` · ${progress.skipped} skipped` : ""}</p>
      <div className="mt-4 flex items-center justify-between border-t pt-3"><p className="text-xs font-medium text-muted-foreground">Reported situation</p><Button type="button" variant="link" size="sm" onClick={props.onEditSituation}>Edit</Button></div>
      <dl aria-label="Current reported circumstances" className="mt-2 grid grid-cols-2 gap-3 lg:grid-cols-5">{circumstances(session.profile).map(item => <div key={item.label}><dt className="text-xs text-muted-foreground">{item.label}</dt><dd className="mt-1 text-sm"><span className="block min-h-10">{item.value}</span>{chosen(item.label) && <span className="mt-1 line-clamp-2 text-xs text-brand-text" title={chosen(item.label)}>Plan: {chosen(item.label)}</span>}</dd></div>)}</dl>
    </section>
    <p role="status" className="sr-only">{notice}</p>
    <section aria-labelledby="tasks-title"><div className="mb-3 flex flex-wrap items-center justify-between gap-3"><h2 id="tasks-title" className="text-lg font-semibold">Tasks</h2><p aria-label="Task status key" className="flex flex-wrap gap-3 text-xs text-muted-foreground"><span>○ Not started</span><span className="text-brand-text">● In progress</span><span className="text-ok">✓ Completed</span></p></div>{tasks.length ? <ul className="space-y-2">{tasks.map(task => <li key={task.id}>{card(task)}</li>)}</ul> : <p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">No steps right now. Update your situation when something changes.</p>}</section>
  </div>;
}

export function SelectedOpportunities({ session, onOpenResource }: Pick<TaskActions, "session" | "onOpenResource">) {
  if (!session.selectedRecommendationIds.length) return null;
  return <details className="my-4"><summary className="cursor-pointer text-sm font-medium text-brand-text">Selected options ({session.selectedRecommendationIds.length})</summary><ul className="mt-3 grid gap-3 md:grid-cols-2">{session.recommendations.filter(r => session.selectedRecommendationIds.includes(r.id)).map(r => <li key={r.id} className="space-y-2 rounded-lg border p-3"><Button variant="link" className="h-auto whitespace-normal p-0 text-left font-medium" onClick={() => onOpenResource(r.id)}>{r.title}</Button><p className="text-xs text-muted-foreground">{resourceLabel(r)}{!r.active ? " · historical selection" : ""}</p><ResourceActions id={r.id} /></li>)}</ul></details>;
}

export function PlanHistory(props: TaskActions) {
  const { session } = props;
  const historyTasks = session.tasks.filter(t => t.archived && t.status !== "completed");
  return <section aria-labelledby="history-title" className="mt-6 border-t pt-5"><details><summary id="history-title" className="cursor-pointer font-semibold">History</summary><div className="mt-4 space-y-4">
    <ul className="space-y-2">{historyTasks.map(task => <li key={task.id}><details><summary className="cursor-pointer rounded-lg border p-3 text-sm">{task.title}<span className="ml-2 text-xs text-muted-foreground">{TASK_STATUS[task.status]}{task.archived ? " · archived" : ""}</span></summary><div className="mt-2"><PlanTaskCard task={task} {...props} open onStart={next => { void props.onEvent(userEvent("task_status", { taskId: next.id, status: "in_progress", notes: next.notes })); }} /></div></details></li>)}</ul>
    <details><summary className="cursor-pointer text-sm text-brand-text">Plan changes ({session.changes.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{session.changes.map((change, i) => <li key={i}>{change.reason}</li>)}</ul></details>
    <details><summary className="cursor-pointer text-sm text-brand-text">Updates ({session.events.length})</summary><ul className="mt-2 space-y-2 text-xs text-muted-foreground">{[...session.events].reverse().map(event => <li key={event.id}>{new Date(event.timestamp).toLocaleString()} · {event.type.replaceAll("_", " ")}</li>)}</ul></details>
    <details><summary className="cursor-pointer text-sm text-brand-text">Earlier options</summary><ul className="mt-3 grid gap-3 md:grid-cols-2">{session.recommendations.filter(r => !r.active || ["dismissed", "rejected"].includes(r.userStatus) || r.userReportedAvailability === "unavailable").map(r => <li key={r.id} className="space-y-2 rounded-lg border p-3"><p className="font-medium">{r.title}</p><ResourceActions id={r.id} /></li>)}</ul></details>
    {!!session.warnings.length && <details><summary className="cursor-pointer text-xs text-muted-foreground">Data and model limitations</summary>{session.warnings.map(w => <p key={w} className="mt-2 text-xs text-muted-foreground">{w}</p>)}</details>}
  </div></details></section>;
}

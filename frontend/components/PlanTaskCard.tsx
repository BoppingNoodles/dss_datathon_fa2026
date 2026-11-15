"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { PhoenixSession, PlanTask, TaskStatus, UserEvent } from "@/lib/domain";
import { userEvent } from "@/lib/domain";
import { taskPrerequisites, taskResourceLabel, taskResources, taskResult } from "@/lib/plan-view";
import { Button } from "./ui/button";

export const TASK_STATUS: Record<TaskStatus, string> = { not_started: "Not started", in_progress: "In progress", blocked: "Blocked", completed: "Completed", skipped: "Skipped" };
export const STAGES = [["immediate_stability", "Immediate stability"], ["removing_barriers", "Removing barriers"], ["building_independence", "Building independence"]] as const;
export interface TaskActions {
  session: PhoenixSession; disabled: boolean;
  onEvent: (event: UserEvent) => Promise<boolean>;
  onOpenResource: (id: string) => void;
}
const safeUrl = (url: string | null | undefined): url is string => !!url && /^https?:\/\//i.test(url);

export default function PlanTaskCard({ task, session, disabled, onEvent, onOpenResource, onStart, onOpen, open = false, startError = "", onClose }: TaskActions & {
  task: PlanTask; onStart?: (task: PlanTask) => void; onOpen?: (task: PlanTask) => void; open?: boolean; startError?: string; onClose?: () => void;
}) {
  const titleId = useId();
  const cardRef = useRef<HTMLElement>(null);
  const [minimumHeight, setMinimumHeight] = useState<number>();
  const [notes, setNotes] = useState(task.notes);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => { setNotes(task.notes); }, [task.notes]);
  useEffect(() => { if (!open) setMinimumHeight(undefined); }, [open]);
  const keepPosition = () => { if (cardRef.current) setMinimumHeight(cardRef.current.getBoundingClientRect().height); };
  const prerequisites = taskPrerequisites(task, session);
  const waiting = prerequisites.length > 0 || task.prerequisiteTaskIds.some(id => !session.tasks.some(t => t.id === id));
  const resources = taskResources(task, session);
  const primary = resources[0];
  const stage = STAGES.find(([key]) => key === task.stage)?.[1];
  const completed = task.status === "completed";
  const urgent = task.priority === "critical";
  const marker = { not_started: "○", in_progress: "●", completed: "✓", blocked: "!", skipped: "−" }[task.status];
  const statusColor = completed ? "text-ok" : task.status === "in_progress" ? "text-brand-text" : "text-muted-foreground";
  const result = taskResult(task, session.profile);
  async function save(status?: TaskStatus, recordResult = false) {
    keepPosition();
    setError(""); setNotice("");
    const saved = await onEvent(userEvent("task_status", { taskId: task.id, ...(status ? { status } : {}), ...(recordResult && result ? { outcome: result.outcome } : {}), notes }));
    if (!saved) setError("This change could not be saved. Try again.");
    else if (!status) setNotice("Note saved.");
  }
  return <article ref={cardRef} style={{ minHeight: open ? minimumHeight : undefined }} data-task-id={task.id} data-task-status={task.status} aria-label={task.title} className={`rounded-xl border border-l-4 px-4 py-3 ${completed ? "border-l-ok bg-ok-soft" : task.status === "in_progress" ? "border-l-primary bg-primary/5" : "border-border border-l-transparent bg-card"}`}>
    <h3 id={titleId} className="text-base font-medium">{onOpen || onClose ? <button type="button" aria-expanded={open} aria-label={`${task.title}. ${TASK_STATUS[task.status]}. ${urgent ? "Urgent" : "Not urgent"}`} className="flex w-full items-center gap-3 rounded text-left focus-visible:outline-2 focus-visible:outline-ring" onClick={() => open ? onClose?.() : onOpen?.(task)}><span aria-hidden="true" className={`w-5 shrink-0 text-center text-lg ${statusColor}`}>{marker}</span><span className={`min-w-0 flex-1 ${completed ? statusColor : ""}`}>{task.title}</span><span className={`shrink-0 rounded-full px-2 py-1 text-xs font-normal ${completed ? "text-ok" : urgent ? "bg-primary/10 text-brand-text" : "text-muted-foreground"}`}>{urgent ? "Urgent" : "Not urgent"}</span><span aria-hidden="true" className="text-muted-foreground">{open ? "−" : "+"}</span></button> : task.title}</h3>
    {open && <div role="region" aria-label={`Current step: ${task.title}`} className="mt-4 space-y-4 border-t pt-4">
      <p role="status" className={`text-xs font-medium ${statusColor}`}>{disabled && task.status !== "in_progress" ? "Saving your step…" : TASK_STATUS[task.status]}</p>
      <p className="max-w-3xl text-sm leading-relaxed">{task.description}</p>
      {waiting && <p className="rounded-lg bg-muted/50 p-3 text-sm">Do this first: {prerequisites.length ? prerequisites.map(t => t.title).join("; ") : "Confirm the earlier step in your plan."}</p>}
      {primary && <Button type="button" variant="outline" className="h-auto max-w-full whitespace-normal py-2 text-left" onClick={() => onOpenResource(primary.id)}>View resource · {primary.title}</Button>}
      {!primary && <p className="text-xs text-muted-foreground">{task.resourceEmptyState ?? (task.allowedResourceTypes?.length ? "No matching resource is available. Ask your support person for a referral." : "Use your own confirmed information or support person for this step.")}</p>}
      <details className="text-xs"><summary className="cursor-pointer font-medium text-brand-text">Why this step and resource details</summary>{stage && <p className="mt-2 text-muted-foreground">{stage}{task.deadline ? ` · Your date: ${task.deadline}` : ""}</p>}<p className="mt-2 leading-relaxed">{task.rationale}</p><ul className="mt-3 space-y-3">{resources.map(r => <li key={r.id}><Button type="button" variant="link" className="h-auto whitespace-normal p-0 text-left text-xs" onClick={() => onOpenResource(r.id)}>{r.title}</Button><p className="mt-1 text-muted-foreground">{taskResourceLabel(task, r)} · {task.resourceMatchReasons?.[r.id] ?? r.matchReasons[0]}</p></li>)}</ul>{!!task.referenceLinks?.length && <div className="mt-3"><p className="font-medium">Original source context</p><ul className="mt-1 space-y-2">{task.referenceLinks.filter(link => safeUrl(link.url)).map(link => <li key={link.url}><a href={link.url} target="_blank" rel="noopener noreferrer" className="text-brand-text underline">{link.label}</a></li>)}</ul></div>}</details>
      <details><summary className="cursor-pointer text-xs font-medium text-brand-text">Notes{task.notes ? " · saved" : " (optional)"}</summary><label htmlFor={`${titleId}-note`} className="sr-only">My notes (optional)</label><textarea id={`${titleId}-note`} rows={2} maxLength={1000} value={notes} disabled={disabled || task.archived} onChange={e => { setNotes(e.target.value); setNotice(""); }} className="mt-2 w-full rounded-lg border border-input bg-card p-3 text-sm focus-visible:outline-2 focus-visible:outline-ring" /><Button type="button" variant="link" className="px-0 text-xs" disabled={disabled || task.archived || notes === task.notes} onClick={() => { void save(); }}>Save note</Button>{notice && <p role="status" className="text-xs text-muted-foreground">{notice}</p>}</details>
      {(error || startError) && <p role="alert" className="text-sm text-destructive">{error || startError}</p>}
      {!task.archived && <div className="flex flex-wrap gap-2">{completed ? <>{result && !result.recorded && <Button type="button" disabled={disabled} onClick={() => { void save("completed", true); }}>Record: {result.label}</Button>}<Button type="button" variant="outline" disabled={disabled} onClick={() => { void save("not_started"); }}>Reopen</Button></> : <>{task.status !== "in_progress" && <Button type="button" disabled={disabled || waiting} onClick={() => { keepPosition(); onStart?.(task); }}>Start step</Button>}<Button type="button" variant={task.status === "in_progress" ? "default" : "outline"} disabled={disabled || waiting} onClick={() => { void save("completed", !!result); }}>{result ? `Done · ${result.label}` : "Done"}</Button><Button type="button" variant="outline" disabled={disabled || task.status === "blocked"} onClick={() => { void save("blocked"); }}>Blocked</Button><Button type="button" variant="ghost" disabled={disabled || task.status === "skipped"} onClick={() => { void save("skipped"); }}>Skip</Button></>}</div>}
      {!completed && result && <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">I finished the search, but still need help</summary><Button type="button" variant="link" className="mt-1 h-auto px-0 text-xs" disabled={disabled || waiting} onClick={() => { void save("completed"); }}>Complete the action only</Button></details>}
    </div>}
  </article>;
}

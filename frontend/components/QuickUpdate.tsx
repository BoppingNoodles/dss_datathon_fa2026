"use client";

import { useState } from "react";
import type { PhoenixSession, ReentryProfile, UserEvent } from "@/lib/domain";
import { quickProposal, type QuickChange } from "@/lib/quick-update";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";

const CHANGES: [QuickChange, string][] = [["stable_housing", "I found stable housing"], ["temporary_housing", "I found temporary housing"], ["lost_housing", "I lost my housing"], ["housing_ending", "My temporary housing is ending"], ["started_work", "I started employment"], ["lost_work", "My employment ended"], ["transport_gained", "I now have transportation"], ["transport_lost", "I lost transportation"], ["id_obtained", "I obtained identification"], ["task_completed", "I completed a task"], ["provider_unavailable", "A housing provider is unavailable"], ["application_rejected", "A job application was declined"], ["appointment", "I have a new appointment"]];
const selectStyle = "min-h-11 w-full rounded-md border border-input bg-card px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring";
export default function QuickUpdate({ session, pending, onPreview }: { session: PhoenixSession; pending: boolean; onPreview: (profile: ReentryProfile, event?: Pick<UserEvent, "type" | "payload">) => void }) {
  const [kind, setKind] = useState<QuickChange | "">("");
  const [resourceId, setResourceId] = useState("");
  const [taskId, setTaskId] = useState("");
  const [endDate, setEndDate] = useState("");
  const [label, setLabel] = useState("");
  const [date, setDate] = useState("");
  const [location, setLocation] = useState("");
  const [error, setError] = useState("");
  const resources = session.recommendations.filter(r => r.active && (kind === "provider_unavailable" ? r.mode === "temporary_housing" : r.mode === "job"));
  const tasks = session.tasks.filter(t => !t.archived && t.status !== "completed" && t.prerequisiteTaskIds.every(id => session.tasks.find(p => p.id === id)?.status === "completed"));
  function submit(e: React.FormEvent) {
    e.preventDefault(); setError("");
    if (!kind) { setError("Choose what changed first."); return; }
    try { const proposal = quickProposal(kind, { resourceId, taskId, endDate, appointmentId: crypto.randomUUID(), appointmentLabel: label, appointmentDate: date, appointmentLocation: location }, session); onPreview(proposal.profile, proposal.event); }
    catch (failure) { setError((failure as Error).message); }
  }
  return <form onSubmit={submit} className="space-y-4 rounded-lg border bg-card p-5"><h2 className="text-lg font-semibold">Quick Update</h2><p className="text-sm text-muted-foreground">Report one change. You’ll review its effect on your plan before saving.</p>
    <div className="space-y-2"><Label htmlFor="quick-change">What changed?</Label><select id="quick-change" value={kind} disabled={pending} className={selectStyle} onChange={e => { setKind(e.target.value as QuickChange); setResourceId(""); setError(""); }}><option value="">Choose a change</option>{CHANGES.map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></div>
    {(kind === "temporary_housing" || kind === "housing_ending") && <div className="space-y-2"><Label htmlFor="quick-end">Housing end date{kind === "temporary_housing" ? " (if known)" : ""}</Label><Input id="quick-end" type="date" value={endDate} disabled={pending} onChange={e => setEndDate(e.target.value)} /></div>}
    {(kind === "provider_unavailable" || kind === "application_rejected") && <div className="space-y-2"><Label htmlFor="quick-resource">Which opportunity?</Label><select id="quick-resource" className={selectStyle} value={resourceId} disabled={pending} onChange={e => setResourceId(e.target.value)}><option value="">Choose an opportunity</option>{resources.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select>{!resources.length && <p className="text-sm text-muted-foreground">No matching opportunity is in this plan yet. Review Your opportunities to save or select one.</p>}</div>}
    {kind === "task_completed" && <div className="space-y-2"><Label htmlFor="quick-task">Which step did you complete?</Label><select id="quick-task" className={selectStyle} value={taskId} disabled={pending} onChange={e => setTaskId(e.target.value)}><option value="">Choose a step</option>{tasks.map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select><p className="text-xs text-muted-foreground">Completing a step records an action. It does not change your reported housing or employment.</p></div>}
    {kind === "appointment" && <div className="grid gap-3 sm:grid-cols-2"><div className="space-y-2 sm:col-span-2"><Label htmlFor="quick-appointment">Appointment label</Label><Input id="quick-appointment" value={label} maxLength={100} disabled={pending} onChange={e => setLabel(e.target.value)} placeholder="A short label, without private details" /></div><div className="space-y-2"><Label htmlFor="quick-date">Date (if known)</Label><Input id="quick-date" type="date" value={date} disabled={pending} onChange={e => setDate(e.target.value)} /></div><div className="space-y-2"><Label htmlFor="quick-location">General location (optional)</Label><Input id="quick-location" value={location} maxLength={100} disabled={pending} onChange={e => setLocation(e.target.value)} /></div></div>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}<Button type="submit" disabled={pending || !kind}>{pending ? "Preparing preview…" : "Preview updated plan"}</Button>
  </form>;
}

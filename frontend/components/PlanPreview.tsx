"use client";

import type { PhoenixSession } from "@/lib/domain";
import { circumstanceChanges, comparePlans, readyTasks, resourceLabel } from "@/lib/plan-view";

export default function PlanPreview({ before, after }: { before: PhoenixSession; after: PhoenixSession }) {
  const changes = comparePlans(before, after);
  const fields = circumstanceChanges(before.profile, after.profile);
  const snapshots: [string, PhoenixSession][] = [["Current priorities", before], ["Updated priorities", after]];
  const taskChanges: [string, typeof changes.added][] = [["Added", changes.added], ["Reprioritized", changes.reprioritized], ["Archived", changes.archived]];
  return <div className="space-y-4" aria-label="Before and after plan preview">
    <div><h2 className="text-xl font-semibold">Review changes</h2><p className="mt-1 text-xs text-muted-foreground">Your plan changes when you confirm.</p></div>
    {!!fields.length && <div className="overflow-x-auto rounded-lg border"><table className="w-full text-left text-sm"><caption className="sr-only">Situation before and after this update</caption><thead className="bg-muted/50"><tr><th className="p-3">Situation</th><th className="p-3">Before</th><th className="p-3">After</th></tr></thead><tbody>{fields.map(field => <tr key={field.label} className="border-t"><th scope="row" className="p-3 font-medium">{field.label}</th><td className="p-3 text-muted-foreground">{field.before}</td><td className="p-3">{field.after}</td></tr>)}</tbody></table></div>}
    <div className="grid gap-3 sm:grid-cols-2">{snapshots.map(([label, state]) => {
      const priorities = readyTasks(state).slice(0, 3);
      return <section key={label} className="rounded-lg border p-4"><h3 className="text-sm font-semibold">{label}</h3>{priorities.length ? <ol className="mt-2 list-decimal space-y-1 pl-4 text-sm">{priorities.map(task => <li key={task.id}>{task.title}</li>)}</ol> : <p className="mt-2 text-sm text-muted-foreground">No steps ready.</p>}</section>;
    })}</div>
    <p className="text-sm text-ok">{changes.retained.length} completed steps kept. Notes and history stay saved.</p>
    <details className="text-sm"><summary className="cursor-pointer text-brand-text">Plan details · {changes.added.length} added · {changes.archived.length} archived</summary><div className="mt-3 space-y-4">
      {!!after.changes.length && <ul className="list-disc space-y-1 pl-4">{after.changes.map((change, index) => <li key={index}>{change.reason}</li>)}</ul>}
      {taskChanges.map(([label, tasks]) => tasks.length > 0 && <div key={label}><h3 className="font-medium">{label}</h3><ul className="mt-1 space-y-1">{tasks.map(task => <li key={task.id}>{task.title}</li>)}</ul></div>)}
      <div><h3 className="font-medium">Resources</h3><ul className="mt-1 space-y-1">{changes.newResources.map(resource => <li key={resource.id}>Added: {resource.title} · {resourceLabel(resource)}</li>)}{changes.unavailableResources.map(resource => <li key={resource.id}>Unavailable: {resource.title} · kept in history</li>)}</ul>{!changes.newResources.length && !changes.unavailableResources.length && <p className="text-muted-foreground">No resources added or removed.</p>}</div>
      <p className="text-xs text-muted-foreground">{changes.preservedSelections.length} selections and {changes.unchanged.length} unchanged tasks kept.</p>
    </div></details>
  </div>;
}

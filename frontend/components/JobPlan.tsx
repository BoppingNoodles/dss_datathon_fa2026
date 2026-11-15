"use client";

import { useState } from "react";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { buildDailyPlan, dateKey, monthCells, type CalendarPlan } from "@/lib/plan";
import { cn } from "@/lib/utils";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const formatDate = (date: Date) => date.toLocaleDateString("en-US", { month: "short", day: "numeric" });

export default function JobPlan({ plan, startDate, loading, completed, onToggleStep, onClear,
  idPrefix = "job-plan", dayTasks = {}, blockedActionIds = [], reviewOnlyActionIds = [] }: {
  plan: CalendarPlan; startDate: Date; loading: boolean; completed: string[];
  onToggleStep: (stepId: string, checked: boolean) => void; onClear?: () => void;
  idPrefix?: string;
  dayTasks?: Record<string, { title: string; action: string }[]>;
  blockedActionIds?: string[];
  reviewOnlyActionIds?: string[];
}) {
  const [month, setMonth] = useState(() => new Date(startDate.getFullYear(), startDate.getMonth(), 1, 12));
  const [selectedDay, setSelectedDay] = useState(1);
  const days = buildDailyPlan(plan, startDate);
  const selected = days[selectedDay - 1];
  const byDate = new Map(days.map((day) => [dateKey(day.date), day]));
  const done = new Set(completed);
  const count = days.filter((day) => done.has(day.id)).length;
  const actionDays = days.filter(day => !reviewOnlyActionIds.includes(day.id)).length;
  const end = days[29].date;
  const firstMonth = startDate.getFullYear() * 12 + startDate.getMonth();
  const lastMonth = end.getFullYear() * 12 + end.getMonth();
  const currentMonth = month.getFullYear() * 12 + month.getMonth();

  function moveMonth(direction: number) {
    const next = new Date(month.getFullYear(), month.getMonth() + direction, 1, 12);
    setMonth(next);
    const first = days.find((day) => day.date.getMonth() === next.getMonth() && day.date.getFullYear() === next.getFullYear());
    if (first) setSelectedDay(first.day);
  }

  return (
    <div id={idPrefix} role="region" tabIndex={-1} aria-labelledby={`${idPrefix}-title`} aria-busy={loading} className="flex scroll-mt-4 flex-col gap-5 outline-none">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 id={`${idPrefix}-title`} className="text-xl font-semibold">Your 30-day plan</h2>
          {idPrefix !== "reentry-calendar" && <p className="max-w-xl text-sm text-muted-foreground">{plan.target_job_title}</p>}
        </div>
        {onClear && <Button type="button" variant="outline" disabled={loading} onClick={onClear}>Change goal</Button>}
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap justify-between gap-2 text-sm text-muted-foreground">
          <span>{formatDate(startDate)} – {formatDate(end)}</span>
          <span role="status">{count} of {actionDays} {reviewOnlyActionIds.length ? "action days" : "days"} complete</span>
        </div>
        <div role="progressbar" aria-label="Plan progress" aria-valuenow={count} aria-valuemin={0} aria-valuemax={actionDays || 1} className="h-1.5 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${actionDays ? count / actionDays * 100 : 0}%` }} />
        </div>
      </div>
      <Card className="gap-0 py-0">
        <CardHeader className="flex flex-row items-center justify-between gap-3 py-4">
          <CardTitle><h3 className="text-lg font-semibold" aria-live="polite">{month.toLocaleDateString("en-US", { month: "long", year: "numeric" })}</h3></CardTitle>
          <div className="flex gap-1">
            <Button type="button" variant="ghost" size="icon" aria-label="Previous month" disabled={currentMonth <= firstMonth} onClick={() => moveMonth(-1)}><ChevronLeft /></Button>
            <Button type="button" variant="ghost" size="icon" aria-label="Next month" disabled={currentMonth >= lastMonth} onClick={() => moveMonth(1)}><ChevronRight /></Button>
          </div>
        </CardHeader>
        <CardContent className="px-0">
          <div className="grid grid-cols-7 border-y border-border bg-muted/40" aria-hidden="true">
            {WEEKDAYS.map((day) => <div key={day} className="py-2 text-center text-xs font-medium text-muted-foreground">{day}</div>)}
          </div>
          <div className="grid grid-cols-7 gap-px bg-border" role="group" aria-label="Daily plan calendar">
            {monthCells(month).map((date) => {
              const day = byDate.get(dateKey(date));
              const inMonth = date.getMonth() === month.getMonth();
              const active = day?.day === selectedDay;
              const finished = day ? done.has(day.id) : false;
              const today = dateKey(date) === dateKey(new Date());
              const label = <>
                <span className="flex w-full items-center justify-between gap-1">
                  <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-full text-xs sm:text-sm", today && "bg-foreground text-background")}>{date.getDate()}</span>
                  {finished && <Check className="size-3.5 shrink-0 text-ok" aria-hidden="true" />}
                </span>
                {day && <>
                  <span className="hidden text-xs leading-snug font-medium sm:block">{day.title}</span>
                  <span className="mt-auto text-[10px] text-muted-foreground sm:text-xs">Day {day.day}</span>
                </>}
              </>;
              return day ? (
                <button key={dateKey(date)} type="button" disabled={loading} aria-pressed={active}
                  aria-label={`${formatDate(date)}, day ${day.day}: ${day.title}${finished ? ", complete" : ""}`}
                  onClick={() => {
                    setSelectedDay(day.day);
                    if (window.innerWidth < 640) requestAnimationFrame(() => document.getElementById(`${idPrefix}-daily-card`)?.scrollIntoView({ behavior: "smooth", block: "start" }));
                  }}
                  className={cn("relative flex min-h-20 min-w-0 flex-col items-start gap-2 bg-card p-1.5 text-left transition-colors hover:bg-muted focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-[-2px] sm:min-h-28 sm:p-3",
                    active && "bg-accent ring-2 ring-primary ring-inset", finished && !active && "bg-ok-soft/40", !inMonth && "opacity-60")}>
                  {label}
                </button>
              ) : <div key={dateKey(date)} className={cn("flex min-h-20 flex-col bg-background p-1.5 text-muted-foreground/60 sm:min-h-28 sm:p-3", !inMonth && "opacity-40")}>{label}</div>;
            })}
          </div>
        </CardContent>
      </Card>
      <Card id={`${idPrefix}-daily-card`} role="region" aria-labelledby={`${idPrefix}-daily-action`} aria-live="polite" className="gap-3 scroll-mt-4">
        <CardHeader>
          <p className="text-xs font-medium text-brand-text">Day {selected.day} · {formatDate(selected.date)} · {selected.phase}</p>
          <CardTitle><h3 id={`${idPrefix}-daily-action`} className="text-lg font-semibold">{selected.title}</h3></CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {!(dayTasks[selected.id]?.length > 1) && <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{selected.action}</p>}
          {dayTasks[selected.id]?.length > 1 && <ul className="space-y-3 text-sm">
            {dayTasks[selected.id].map((task) => <li key={task.title}><p className="font-medium">{task.title}</p><p className="text-muted-foreground">{task.action}</p></li>)}
          </ul>}
          {selected.links.length > 0 && <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
            {selected.links.map((link) => <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer" className="text-brand-text underline underline-offset-4">{link.label}</a>)}
          </div>}
          {reviewOnlyActionIds.includes(selected.id) ? <p className="text-sm text-muted-foreground">Review day · no tasks due.</p> : <div className="flex items-center gap-2.5">
            <Checkbox id={`${idPrefix}-complete-day`} disabled={loading || blockedActionIds.includes(selected.id)} checked={done.has(selected.id)} onCheckedChange={(value) => onToggleStep(selected.id, value === true)} />
            <label htmlFor={`${idPrefix}-complete-day`} className="cursor-pointer text-sm font-medium">Mark day {selected.day} complete</label>
          </div>}
          {blockedActionIds.includes(selected.id) && <p className="text-sm text-muted-foreground">Complete the prerequisite steps in your overview first.</p>}
        </CardContent>
      </Card>
      {plan.credential_paths.length > 0 && <details className="text-sm">
        <summary className="cursor-pointer font-medium text-brand-text">Credentials for this goal</summary>
        <ul className="mt-3 flex flex-col gap-3">
          {plan.credential_paths.map((path) => <li key={path.credential} className="flex flex-col gap-1">
            <p className="font-medium">{path.credential} · {path.user_status === "reported_held" ? "Verify your existing credential" : path.requirement_kind === "required" ? "Required" : "Confirm with employer"}</p>
            <p className="text-muted-foreground">{path.job_evidence}</p>
          </li>)}
        </ul>
      </details>}
      <p className="text-xs text-muted-foreground">Suggested dates are flexible. Confirm appointments with the provider.</p>
    </div>
  );
}

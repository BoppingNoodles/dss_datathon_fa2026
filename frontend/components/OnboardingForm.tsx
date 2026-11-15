"use client";

import { useEffect, useRef, useState } from "react";
import { CERTIFICATE_PRESETS } from "@/lib/certificates";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import PhoenixThinking from "./PhoenixThinking";
import type { RecommendationRequest, ReentrySituation } from "@/lib/types";
import { onboardingDraft, type OnboardingDraft } from "@/lib/saved-session";
import { onboardingErrors, onboardingRequest } from "@/lib/onboarding";
import { GOAL_PRESETS, SUPPORT_OPTIONS, goalLines, ownGoals, replaceOwnGoals, toggleGoal } from "@/lib/onboarding-choices";

const WORK = ["Warehouse", "Food service", "Retail", "Customer service", "Construction", "Cleaning", "Driving", "Landscaping", "Office work", "Caregiving"];
const EDUCATION = [["no_diploma", "No diploma yet"], ["high_school_or_ged", "High school diploma or GED"], ["some_college", "Some college"], ["associate", "Associate degree"], ["bachelor", "Bachelor's degree"], ["graduate", "Graduate degree"], ["not_sure", "Not sure / prefer not to answer"]];
const YES_NO = [["yes", "Yes"], ["no", "No"], ["unsure", "Unsure"], ["prefer_not_to_say", "Prefer not to answer"]];
const STEPS = ["About you", "Daily needs", "Work", "Goals"];
const STEP_KEYS = [
  ["release-status", "location", "release-date"],
  ["housing", "housingEnd", "housingBudget", "has_immediate_housing", "has_id", "has_transportation", "has_phone_access", "phone", "internet"],
  ["employment-goal", "experience", "years", "level", "certificates"],
  ["need", "has_required_appointment", "appointments"],
];
const field = "h-11 bg-card text-base";
const choiceCard = (selected: boolean) => `flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${selected ? "border-primary bg-primary/10" : "border-border hover:bg-muted/50"}`;

function Choice({ id, label, value, options, onChange, invalid = false }: {
  id: string; label: string; value?: string | null; options: string[][]; onChange: (value: string) => void; invalid?: boolean;
}) {
  return <div className="flex flex-col gap-2">
    <Label htmlFor={id}>{label}</Label>
    <Select value={value ?? ""} onValueChange={onChange}>
      <SelectTrigger id={id} aria-required="true" aria-invalid={invalid} className="w-full data-[size=default]:h-11"><SelectValue placeholder="Choose an answer" /></SelectTrigger>
      <SelectContent position="popper" className="max-h-72 w-(--radix-select-trigger-width)"><SelectGroup>{options.map(([key, text]) => <SelectItem key={key} value={key}>{text}</SelectItem>)}</SelectGroup></SelectContent>
    </Select>
  </div>;
}

export default function OnboardingForm({ initial, draft, loading, onDraftChange, onSubmit, submitLabel = "Build my reentry plan", mode = "onboarding" }: {
  initial: RecommendationRequest | null; draft: OnboardingDraft | null; loading: boolean;
  onDraftChange: (answers: OnboardingDraft) => void; onSubmit: (req: RecommendationRequest) => void; submitLabel?: string; mode?: "onboarding" | "edit";
}) {
  const [answers, setAnswers] = useState<OnboardingDraft>(() => ({
    ...onboardingDraft(initial), ...draft, reentryEnabled: true, adaptive: true,
    need: draft?.need ?? initial?.priority_need ?? "work",
    reentry: { has_required_appointment: "unsure", ...initial?.reentry, ...draft?.reentry },
  }));
  const [step, setStep] = useState(0);
  const [tried, setTried] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const editing = mode === "edit";
  useEffect(() => { onDraftChange(answers); }, [answers, onDraftChange]);
  const errors = onboardingErrors(answers);
  const r = answers.reentry ?? {};
  const experienceDisabled = answers.noExp || answers.expUnsure;
  function update(patch: Partial<OnboardingDraft>) { setAnswers((a) => ({ ...a, ...patch })); }
  function updateReentry(patch: Partial<ReentrySituation>) { setAnswers((a) => ({ ...a, reentry: { ...a.reentry, ...patch } })); }
  function communication(key: "phone" | "internet", value: string) {
    setAnswers((a) => {
      const next = { ...a, [key]: value };
      return { ...next, reentry: { ...a.reentry, has_phone_access: next.phone === "yes" || next.internet === "yes" ? "yes" : next.phone === "no" && next.internet === "no" ? "no" : "unsure" } };
    });
  }
  const invalid = (key: string) => tried && !!errors[key];
  const errorList = (editing ? Object.keys(errors) : STEP_KEYS[step]).flatMap((key) => invalid(key) ? [errors[key]] : []);
  function next() {
    setTried(true);
    if (STEP_KEYS[step].some((key) => errors[key])) return;
    setStep((s) => s + 1); setTried(false);
    window.scrollTo({ top: 0 });
  }
  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!editing && step < 3) { next(); return; }
    setTried(true);
    const failing = STEP_KEYS.findIndex((keys) => keys.some((key) => errors[key]));
    if (failing !== -1) {
      if (!editing) setStep(failing);
      else requestAnimationFrame(() => formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    onSubmit(onboardingRequest(answers, initial));
  }
  return <form ref={formRef} id={editing ? "current-situation-form" : undefined} onSubmit={submit} noValidate className="flex flex-col gap-4">
    {!editing && <ol aria-label="Onboarding steps" className="grid grid-cols-4 gap-2 text-xs">{STEPS.map((name, index) => <li key={name} aria-current={step === index ? "step" : undefined} className={step === index ? "rounded-lg bg-accent p-3 font-semibold" : "rounded-lg bg-muted/50 p-3 text-muted-foreground"}>{index + 1}. {name}</li>)}</ol>}
    {errorList.length > 0 && <Alert variant="destructive" role="alert"><AlertDescription><ul className="list-disc pl-4">{[...new Set(errorList)].map((message) => <li key={message}>{message}</li>)}</ul></AlertDescription></Alert>}
    <fieldset disabled={loading} className="contents"><Card>
      <CardHeader><CardTitle><h2 className="text-xl">{editing ? "Your information" : STEPS[step]}</h2></CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-5">
        {(editing || step === 0) && <>
          {editing && <h3 className="font-semibold">Release and location</h3>}
          <Choice id="release-status" label="Are you preparing for release or already in the community?" value={r.release_status} invalid={invalid("release-status")}
            options={[["preparing_for_release", "Preparing for release"], ["already_released", "Already released"], ["unsure", "Unsure"], ["prefer_not_to_say", "Prefer not to answer"]]}
            onChange={(v) => updateReentry({ release_status: v as ReentrySituation["release_status"] })} />
          <div className="flex flex-col gap-2"><Label htmlFor="release-date">Release date (optional)</Label><Input id="release-date" type="date" value={r.release_date ?? ""} className={field} onChange={(e) => updateReentry({ release_date: e.target.value || null })} /></div>
          <div className="flex flex-col gap-2"><Label htmlFor="location">City or ZIP code</Label><Input id="location" required maxLength={80} className={field} placeholder="Oakland or 94612" value={answers.location} aria-invalid={invalid("location")} onChange={(e) => update({ location: e.target.value })} /></div>
        </>}
        {(editing || step === 1) && <>
          {editing && <h3 className="border-t pt-5 font-semibold">Housing and everyday needs</h3>}
          <Choice id="housing-status" label="Do you have a confirmed place to stay?" value={answers.housingStatus} invalid={invalid("housing")}
            options={[["stable", "Yes, stable housing"], ["temporary", "Yes, temporary housing"], ["no_confirmed_housing", "No confirmed housing"], ["unsure", "Unsure / prefer not to answer"]]}
            onChange={(v) => { update({ housingStatus: v as OnboardingDraft["housingStatus"] }); updateReentry({ has_immediate_housing: v === "stable" || v === "temporary" ? "yes" : v === "no_confirmed_housing" ? "no" : "unsure" }); }} />
          {answers.housingStatus === "temporary" && <div className="flex flex-col gap-2"><Label htmlFor="housing-end">When does your arrangement end? (optional)</Label><Input id="housing-end" type="date" className={field} value={answers.housingEnd ?? ""} onChange={(e) => update({ housingEnd: e.target.value })} /></div>}
          <div className="flex flex-col gap-2"><Label htmlFor="housing-budget">Monthly housing budget, if known (optional)</Label><Input id="housing-budget" type="number" min="0" max="100000" className={field} value={answers.housingBudget ?? ""} onChange={(e) => update({ housingBudget: e.target.value })} /></div>
          <div className="grid grid-cols-2 gap-4">
            <Choice id="food-access" label="Do you have access to food?" value={answers.food ?? "unsure"} options={YES_NO} onChange={food => update({ food })} />
            <Choice id="has_id" label="Do you have government identification?" value={r.has_id} options={YES_NO} invalid={invalid("has_id")} onChange={(v) => updateReentry({ has_id: v as ReentrySituation["has_id"] })} />
            <Choice id="has_transportation" label="Do you have reliable transportation?" value={r.has_transportation} options={YES_NO} invalid={invalid("has_transportation")} onChange={(v) => updateReentry({ has_transportation: v as ReentrySituation["has_transportation"] })} />
            <Choice id="phone" label="Can you use a phone to receive messages?" value={answers.phone} options={[...YES_NO, ["limited", "Limited access"]]} invalid={invalid("phone")} onChange={(v) => communication("phone", v)} />
            <Choice id="internet" label="Can you access the internet?" value={answers.internet} options={[...YES_NO, ["limited", "Limited access"]]} invalid={invalid("internet")} onChange={(v) => communication("internet", v)} />
          </div>
        </>}
        {(editing || step === 2) && <>
          {editing && <h3 className="border-t pt-5 font-semibold">Work and education</h3>}
          <Choice id="employment-goal" label="What is your current work situation?" value={r.employment_goal} invalid={invalid("employment-goal")}
            options={[["find_work", "Unemployed and looking for work"], ["keep_work", "Employed"], ["prepare_for_work", "Seeking training"], ["not_now", "Not seeking work now"], ["unsure", "Unsure / prefer not to answer"]]}
            onChange={(v) => updateReentry({ employment_goal: v as ReentrySituation["employment_goal"] })} />
          <fieldset><legend className="mb-2 font-medium">What kind of work interests you? (optional)</legend><ToggleGroup type="multiple" variant="outline" spacing={2} aria-label="Preferred job types" value={answers.preferredJobs ?? []} onValueChange={(preferredJobs) => update({ preferredJobs })} className="w-full flex-wrap">{WORK.map((s) => <ToggleGroupItem key={s} value={s} className="rounded-full px-3">{s}</ToggleGroupItem>)}</ToggleGroup></fieldset>
          <fieldset className="flex flex-col gap-3"><legend className="mb-2 font-medium">What skills or experience do you have?</legend><p className="text-xs text-muted-foreground">Include work, training and volunteering before or during incarceration.</p>
            <ToggleGroup type="multiple" variant="outline" spacing={2} aria-label="Skills and work areas" value={answers.skills} disabled={!!experienceDisabled} onValueChange={(skills) => update({ skills })} className="w-full flex-wrap">{WORK.map((s) => <ToggleGroupItem key={s} value={s} className="rounded-full px-3">{s}</ToggleGroupItem>)}</ToggleGroup>
            <Label htmlFor="exp">Another skill or experience (optional)</Label><Input id="exp" className={field} maxLength={300} disabled={!!experienceDisabled} value={answers.expText} onChange={(e) => update({ expText: e.target.value })} />
            <Label htmlFor="years">Years of relevant experience, if known</Label><Input id="years" type="number" min="0" max="60" step="0.5" className={field} disabled={!!experienceDisabled} value={answers.years} onChange={(e) => update({ years: e.target.value })} />
            <div className="flex items-center gap-2"><Checkbox id="noexp" checked={answers.noExp} onCheckedChange={(v) => update({ noExp: v === true, expUnsure: false, ...(v === true ? { skills: [], expText: "", years: "" } : {}) })} /><Label htmlFor="noexp">None yet</Label></div>
            <div className="flex items-center gap-2"><Checkbox id="experience-unsure" checked={answers.expUnsure ?? false} onCheckedChange={(v) => update({ expUnsure: v === true, noExp: false, ...(v === true ? { skills: [], expText: "", years: "" } : {}) })} /><Label htmlFor="experience-unsure">Unsure / prefer not to answer</Label></div>
          </fieldset>
          <Choice id="level" label="What education have you completed?" value={answers.level} options={EDUCATION} invalid={invalid("level")} onChange={(level) => update({ level })} />
          <fieldset className="flex flex-col gap-3"><legend className="mb-2 font-medium">Certificates or licenses you already hold</legend>
            <details className="rounded-lg border border-input p-3"><summary className="cursor-pointer font-medium text-brand-text">Select certificates or licenses ({answers.certs.length})</summary><div className="mt-3 flex max-h-60 flex-col gap-3 overflow-y-auto p-1">{[...new Set([...CERTIFICATE_PRESETS, ...answers.certs])].map((certificate, index) => <div key={certificate} className="flex items-center gap-2"><Checkbox id={`certificate-${index}`} checked={answers.certs.includes(certificate)} onCheckedChange={(v) => update({ certs: v === true ? [...answers.certs, certificate] : answers.certs.filter((c) => c !== certificate), noCerts: false, certsUnsure: false })} /><Label htmlFor={`certificate-${index}`}>{certificate}</Label></div>)}</div></details>
            <div className="flex items-center gap-2"><Checkbox id="no-certificates" checked={answers.noCerts} onCheckedChange={(v) => update({ noCerts: v === true, certsUnsure: false, ...(v === true ? { certs: [], otherCerts: "" } : {}) })} /><Label htmlFor="no-certificates">None yet</Label></div>
            <div className="flex items-center gap-2"><Checkbox id="certificates-unsure" checked={answers.certsUnsure ?? false} onCheckedChange={(v) => update({ certsUnsure: v === true, noCerts: false, ...(v === true ? { certs: [], otherCerts: "" } : {}) })} /><Label htmlFor="certificates-unsure">Unsure / prefer not to answer</Label></div>
            <Label htmlFor="creds">Another certificate or license (optional)</Label><Input id="creds" className={field} disabled={answers.noCerts || answers.certsUnsure} value={answers.otherCerts} placeholder="Separate more than one with commas" onChange={(e) => update({ otherCerts: e.target.value })} />
          </fieldset>
        </>}
        {(editing || step === 3) && <>
          {editing && <h3 className="border-t pt-5 font-semibold">Support and goals</h3>}
          <fieldset className="space-y-3"><legend className="font-semibold">What do you need help with now?</legend><p className="text-sm text-muted-foreground">Choose any that apply.</p><div className="grid gap-2 sm:grid-cols-2">{SUPPORT_OPTIONS.map(([key, label, example]) => <label key={key} htmlFor={`support-${key}`} className={choiceCard((answers.supportNeeds ?? []).includes(key))}><Checkbox id={`support-${key}`} className="mt-0.5" checked={(answers.supportNeeds ?? []).includes(key)} onCheckedChange={value => update({ supportNeeds: value === true ? [...new Set([...(answers.supportNeeds ?? []), key])] : (answers.supportNeeds ?? []).filter(v => v !== key), supportChoice: undefined })} /><span><span className="block text-sm font-medium">{label}</span><span className="mt-1 block text-xs text-muted-foreground">{example}</span></span></label>)}</div><div className="grid gap-2 sm:grid-cols-2">{[["unsure", "Not sure yet"], ["none", "No additional support right now"]].map(([value, label]) => <label key={value} htmlFor={`support-${value}`} className={choiceCard(answers.supportChoice === value)}><Checkbox id={`support-${value}`} checked={answers.supportChoice === value} onCheckedChange={checked => update({ supportChoice: checked === true ? value as "unsure" | "none" : undefined, supportNeeds: [] })} /><span className="text-sm">{label}</span></label>)}</div></fieldset>
          <fieldset className="space-y-3 border-t pt-5"><legend className="pt-5 font-semibold">What would you like to work toward?</legend><p className="text-sm text-muted-foreground">Your goals for the next 30 days.</p><div className="grid gap-2 sm:grid-cols-2">{GOAL_PRESETS.map((goal, i) => <label key={goal} htmlFor={`goal-${i}`} className={choiceCard(goalLines(answers.goals ?? "").includes(goal))}><Checkbox id={`goal-${i}`} checked={goalLines(answers.goals ?? "").includes(goal)} onCheckedChange={checked => update({ goals: toggleGoal(answers.goals ?? "", goal, checked === true), goalsUnsure: false })} /><span className="text-sm">{goal}</span></label>)}</div><label htmlFor="goals-unsure" className={choiceCard(answers.goalsUnsure === true)}><Checkbox id="goals-unsure" checked={answers.goalsUnsure ?? false} onCheckedChange={checked => update({ goalsUnsure: checked === true, ...(checked === true ? { goals: "" } : {}) })} /><span className="text-sm">Not sure yet</span></label><div className="flex flex-col gap-2"><Label htmlFor="goals">My own goal (optional)</Label><textarea id="goals" rows={2} maxLength={1000} value={ownGoals(answers.goals ?? "")} onChange={e => update({ goals: replaceOwnGoals(answers.goals ?? "", e.target.value), goalsUnsure: false })} placeholder="For example, arrange a ride to my first appointment" className="rounded-lg border border-input bg-card p-3 text-base" /></div></fieldset>
          <details className="rounded-lg border p-4"><summary className="cursor-pointer font-medium">Appointments and dates (optional)</summary><div className="mt-4 space-y-4"><Choice id="has_required_appointment" label="Any upcoming appointments or deadlines to plan around?" value={r.has_required_appointment} options={YES_NO} invalid={invalid("has_required_appointment")} onChange={(v) => { updateReentry({ has_required_appointment: v as ReentrySituation["has_required_appointment"] }); if (v !== "yes") update({ appointments: [] }); }} />
          {r.has_required_appointment === "yes" && <div className="flex flex-col gap-3"><p className="text-xs text-muted-foreground">Use a general label such as “Appointment.” Dates and location are optional. Avoid case numbers or supervision details.</p>{(answers.appointments ?? []).map((a, i) => <div key={a.id} className="grid grid-cols-1 items-end gap-3 sm:grid-cols-[1fr_10rem_auto]"><div className="flex flex-col gap-2"><Label htmlFor={`appointment-${i}`}>Short label</Label><Input id={`appointment-${i}`} value={a.label} maxLength={120} onChange={(e) => update({ appointments: answers.appointments!.map((item) => item.id === a.id ? { ...item, label: e.target.value } : item) })} /></div><div className="flex flex-col gap-2"><Label htmlFor={`appointment-date-${i}`}>Date (optional)</Label><Input id={`appointment-date-${i}`} type="date" value={a.date ?? ""} onChange={(e) => update({ appointments: answers.appointments!.map((item) => item.id === a.id ? { ...item, date: e.target.value || null } : item) })} /></div><Button type="button" variant="ghost" onClick={() => update({ appointments: answers.appointments!.filter((item) => item.id !== a.id) })}>Remove</Button><div className="flex flex-col gap-2 sm:col-span-3"><Label htmlFor={`appointment-place-${i}`}>Location (optional)</Label><Input id={`appointment-place-${i}`} maxLength={160} value={a.location ?? ""} onChange={(e) => update({ appointments: answers.appointments!.map((item) => item.id === a.id ? { ...item, location: e.target.value || null } : item) })} /></div></div>)}<Button type="button" variant="outline" disabled={(answers.appointments?.length ?? 0) >= 20} onClick={() => update({ appointments: [...(answers.appointments ?? []), { id: crypto.randomUUID(), label: "Appointment", date: null, location: null }] })}>Add an appointment</Button></div>}
          </div></details>
        </>}
      </CardContent>
    </Card>
    {!editing && <p className="text-xs text-muted-foreground">Demo · Use fictional details.</p>}
    <div className="flex gap-3">{!editing && step > 0 && <Button type="button" variant="outline" disabled={loading} onClick={() => { setStep((s) => s - 1); setTried(false); }}>Back</Button>}{!editing && step < 3 ? <Button key="continue" type="button" className="h-12 flex-1" onClick={(event) => { event.preventDefault(); next(); }}>Continue</Button> : <Button key="submit" type="submit" variant={loading ? "outline" : "default"} className="h-12 flex-1 disabled:opacity-100" disabled={loading}>{loading ? <PhoenixThinking /> : submitLabel}</Button>}</div></fieldset>
  </form>;
}

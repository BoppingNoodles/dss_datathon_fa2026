"use client";

import { useState } from "react";
import type { Need, RecommendationRequest } from "@/lib/types";

const NEEDS: { value: Need; label: string; hint: string }[] = [
  { value: "work", label: "Work", hint: "Jobs and job help" },
  { value: "housing", label: "Housing", hint: "Shelter and rent" },
  { value: "food", label: "Food", hint: "Pantries and meals" },
  { value: "health_care", label: "Health care", hint: "Clinics and recovery" },
  { value: "transportation", label: "Transportation", hint: "Transit nearby" },
  { value: "community_support", label: "Community support", hint: "ID, legal, services" },
];

const SKILLS = [
  "Warehouse", "Food service", "Retail", "Customer service", "Construction",
  "Cleaning", "Driving", "Landscaping", "Office work", "Caregiving",
];

const EDUCATION = [
  { value: "", label: "Choose one (optional)" },
  { value: "no_diploma", label: "No diploma yet" },
  { value: "high_school_or_ged", label: "High school diploma or GED" },
  { value: "some_college", label: "Some college" },
  { value: "associate", label: "Associate degree" },
  { value: "bachelor", label: "Bachelor's degree" },
  { value: "graduate", label: "Graduate degree" },
  { value: "not_sure", label: "Not sure" },
];

const input =
  "w-full rounded-lg border border-line bg-card px-3 py-2.5 text-base placeholder:text-muted/70";

function Question({ n, title, optional, children }: {
  n: number; title: string; optional?: boolean; children: React.ReactNode;
}) {
  return (
    <fieldset className="rounded-xl border border-line bg-card p-4 sm:p-5">
      <legend className="float-left mb-3 w-full text-lg font-semibold">
        <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-brand text-sm text-white">
          {n}
        </span>
        {title}
        {optional && <span className="ml-2 text-sm font-normal text-muted">Optional</span>}
      </legend>
      <div className="clear-both">{children}</div>
    </fieldset>
  );
}

export default function OnboardingForm({ initial, loading, onSubmit }: {
  initial: RecommendationRequest | null;
  loading: boolean;
  onSubmit: (req: RecommendationRequest) => void;
}) {
  const [location, setLocation] = useState(initial?.location ?? "");
  const [need, setNeed] = useState<Need | null>(initial?.priority_need ?? null);
  const [age, setAge] = useState(initial?.age?.toString() ?? "");
  const [skills, setSkills] = useState<string[]>(initial?.experience.skills ?? []);
  const [expText, setExpText] = useState(initial?.experience.text ?? "");
  const [years, setYears] = useState(initial?.experience.years?.toString() ?? "");
  const [noExp, setNoExp] = useState(initial?.experience.no_experience_yet ?? false);
  const [level, setLevel] = useState(initial?.education.level ?? "");
  const [creds, setCreds] = useState(initial?.education.credentials.join(", ") ?? "");
  const [tried, setTried] = useState(false);

  const locationOk = location.trim().length >= 2;
  const ageNum = age.trim() === "" ? null : Number(age);
  const ageOk = ageNum === null || (Number.isInteger(ageNum) && ageNum >= 14 && ageNum <= 110);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setTried(true);
    if (!locationOk || !need || !ageOk) return;
    onSubmit({
      age: ageNum,
      location: location.trim(),
      priority_need: need,
      experience: {
        skills: noExp ? [] : skills,
        text: noExp || !expText.trim() ? null : expText.trim(),
        years: noExp || years.trim() === "" ? null : Number(years),
        no_experience_yet: noExp,
      },
      education: {
        level: level || null,
        credentials: creds.split(",").map((c) => c.trim()).filter(Boolean),
      },
      service_sort: initial?.service_sort ?? "highly_rated",
      job_sort: initial?.job_sort ?? "highest_pay",
    });
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <Question n={1} title="Where will you be living?">
        <label htmlFor="location" className="sr-only">City or ZIP code</label>
        <input
          id="location" className={input} value={location} autoComplete="postal-code"
          placeholder="City or ZIP code, like Oakland or 94612"
          onChange={(e) => setLocation(e.target.value)}
          aria-invalid={tried && !locationOk}
        />
        <p className="mt-2 text-sm text-muted">
          Phoenix covers Oakland and nearby East Bay cities. No street address needed.
        </p>
        {tried && !locationOk && <p className="mt-1 text-sm font-medium text-brand-text">Enter a city or ZIP code.</p>}
      </Question>

      <Question n={2} title="What do you need help with first?">
        <div role="radiogroup" aria-label="Immediate need" className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {NEEDS.map((o) => (
            <button
              type="button" role="radio" aria-checked={need === o.value} key={o.value}
              onClick={() => setNeed(o.value)}
              className={`rounded-lg border px-3 py-3 text-left transition-colors ${
                need === o.value ? "border-brand bg-brand-soft" : "border-line bg-card hover:border-brand/50"
              }`}
            >
              <span className="block font-semibold">{o.label}</span>
              <span className="block text-sm text-muted">{o.hint}</span>
            </button>
          ))}
        </div>
        {tried && !need && <p className="mt-2 text-sm font-medium text-brand-text">Choose one to start.</p>}
      </Question>

      <Question n={3} title="How old are you?" optional>
        <label htmlFor="age" className="sr-only">Age in years</label>
        <input
          id="age" className={`${input} max-w-36`} inputMode="numeric" value={age} placeholder="Age"
          onChange={(e) => setAge(e.target.value.replace(/[^\d]/g, ""))} aria-invalid={!ageOk}
        />
        <p className="mt-2 text-sm text-muted">
          Only used to check age rules that a service has published. Leave blank to skip.
        </p>
        {!ageOk && <p className="mt-1 text-sm font-medium text-brand-text">Enter an age from 14 to 110, or leave it blank.</p>}
      </Question>

      <Question n={4} title="What work have you done or skills have you learned?" optional>
        <p className="mb-3 text-sm text-muted">Include work or training completed while incarcerated.</p>
        <div className={`flex flex-wrap gap-2 ${noExp ? "opacity-40" : ""}`}>
          {SKILLS.map((s) => {
            const on = skills.includes(s);
            return (
              <button
                type="button" key={s} disabled={noExp} aria-pressed={on}
                onClick={() => setSkills(on ? skills.filter((x) => x !== s) : [...skills, s])}
                className={`rounded-full border px-3 py-1.5 text-sm ${
                  on ? "border-brand bg-brand text-white" : "border-line bg-card hover:border-brand/50"
                }`}
              >
                {s}
              </button>
            );
          })}
        </div>
        <div className={`mt-3 grid gap-3 sm:grid-cols-[1fr_9rem] ${noExp ? "opacity-40" : ""}`}>
          <div>
            <label htmlFor="exp" className="mb-1 block text-sm font-medium">Anything else?</label>
            <input id="exp" className={input} value={expText} disabled={noExp} maxLength={300}
              placeholder="Like forklift, kitchen prep, welding" onChange={(e) => setExpText(e.target.value)} />
          </div>
          <div>
            <label htmlFor="years" className="mb-1 block text-sm font-medium">About how many years?</label>
            <input id="years" className={input} inputMode="numeric" value={years} disabled={noExp}
              onChange={(e) => setYears(e.target.value.replace(/[^\d]/g, "").slice(0, 2))} />
          </div>
        </div>
        <label className="mt-3 flex items-center gap-2">
          <input type="checkbox" className="h-5 w-5 accent-brand" checked={noExp} onChange={(e) => setNoExp(e.target.checked)} />
          <span>No experience yet</span>
        </label>
      </Question>

      <Question n={5} title="What education or qualifications do you have?" optional>
        <label htmlFor="level" className="sr-only">Highest education level</label>
        <select id="level" className={input} value={level} onChange={(e) => setLevel(e.target.value)}>
          {EDUCATION.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <label htmlFor="creds" className="mt-3 mb-1 block text-sm font-medium">Certificates or licenses</label>
        <input id="creds" className={input} value={creds} placeholder="Like ServSafe, forklift, CDL"
          onChange={(e) => setCreds(e.target.value)} />
      </Question>

      <p className="rounded-lg bg-info-soft px-4 py-3 text-sm text-info">
        We never ask about convictions, your Social Security number, or your exact address. No account needed, and
        your answers aren&apos;t saved.
      </p>

      <button
        type="submit" disabled={loading}
        className="w-full rounded-lg bg-brand px-5 py-3.5 text-lg font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
      >
        {loading ? "Finding results…" : "Show my results"}
      </button>
    </form>
  );
}

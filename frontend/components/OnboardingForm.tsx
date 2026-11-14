"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Need, RecommendationRequest } from "@/lib/types";

const NEEDS: { value: Need; label: string }[] = [
  { value: "work", label: "Work" },
  { value: "housing", label: "Housing" },
  { value: "food", label: "Food" },
  { value: "health_care", label: "Health care" },
  { value: "transportation", label: "Transportation" },
  { value: "community_support", label: "Community support" },
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

// shadcn's default controls are compact; this form uses larger touch targets.
const field = "h-11 bg-card text-base md:text-base";
const problem = "text-sm font-medium text-destructive";

function Question({ n, title, optional, children }: {
  n: number; title: string; optional?: boolean; children: React.ReactNode;
}) {
  return (
    <Card role="group" aria-labelledby={`q${n}`}>
      <CardHeader>
        <CardTitle id={`q${n}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-lg">
          <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm text-primary-foreground">
            {n}
          </span>
          {title}
          {optional && <span className="text-sm font-normal text-muted-foreground">Optional</span>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">{children}</CardContent>
    </Card>
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
        <Label htmlFor="location" className="sr-only">City or ZIP code</Label>
        <Input
          id="location" className={field} value={location} autoComplete="postal-code"
          placeholder="City or ZIP code, like Oakland or 94612"
          onChange={(e) => setLocation(e.target.value)} aria-invalid={tried && !locationOk}
        />
        {tried && !locationOk && <p className={problem}>Enter a city or ZIP code.</p>}
      </Question>

      <Question n={2} title="What do you need help with first?">
        <ToggleGroup
          type="single" variant="outline" spacing={2} aria-label="Immediate need"
          value={need ?? ""} onValueChange={(v) => v && setNeed(v as Need)}
          className="grid w-full grid-cols-2 sm:grid-cols-3"
        >
          {NEEDS.map((o) => (
            <ToggleGroupItem
              key={o.value} value={o.value}
              className="h-auto min-h-12 w-full bg-card px-3 py-3 whitespace-normal data-[state=on]:border-primary data-[state=on]:bg-accent"
            >
              <span className="text-base font-semibold text-foreground">{o.label}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {tried && !need && <p className={problem}>Choose one to start.</p>}
      </Question>

      <Question n={3} title="How old are you?" optional>
        <Label htmlFor="age" className="sr-only">Age in years</Label>
        <Input
          id="age" className={`${field} max-w-36`} inputMode="numeric" value={age} placeholder="Age"
          onChange={(e) => setAge(e.target.value.replace(/[^\d]/g, ""))} aria-invalid={!ageOk}
        />
        {!ageOk && <p className={problem}>Enter an age from 14 to 110, or leave it blank.</p>}
      </Question>

      <Question n={4} title="What work have you done or skills have you learned?" optional>
        <ToggleGroup
          type="multiple" variant="outline" spacing={2} aria-label="Skills and work areas" disabled={noExp}
          value={skills} onValueChange={setSkills} className="w-full flex-wrap"
        >
          {SKILLS.map((s) => (
            <ToggleGroupItem
              key={s} value={s}
              className="h-9 rounded-full bg-card px-3 data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
            >
              {s}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <div className="grid gap-3 sm:grid-cols-[1fr_11rem]">
          <div className="space-y-1.5">
            <Label htmlFor="exp">Anything else?</Label>
            <Input id="exp" className={field} value={expText} disabled={noExp} maxLength={300}
              placeholder="Like forklift, kitchen prep, welding" onChange={(e) => setExpText(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="years">About how many years?</Label>
            <Input id="years" className={field} inputMode="numeric" value={years} disabled={noExp}
              onChange={(e) => setYears(e.target.value.replace(/[^\d]/g, "").slice(0, 2))} />
          </div>
        </div>
        <div className="flex items-center gap-2.5 pt-1">
          <Checkbox id="noexp" className="size-5" checked={noExp} onCheckedChange={(v) => setNoExp(v === true)} />
          <Label htmlFor="noexp" className="text-base font-normal">No experience yet</Label>
        </div>
      </Question>

      <Question n={5} title="What education or qualifications do you have?" optional>
        <Label htmlFor="level" className="sr-only">Highest education level</Label>
        <NativeSelect id="level" className="w-full [&_select]:h-11 [&_select]:bg-card [&_select]:text-base"
          value={level} onChange={(e) => setLevel(e.target.value)}>
          {EDUCATION.map((o) => <NativeSelectOption key={o.value} value={o.value}>{o.label}</NativeSelectOption>)}
        </NativeSelect>
        <div className="space-y-1.5">
          <Label htmlFor="creds">Certificates or licenses</Label>
          <Input id="creds" className={field} value={creds} placeholder="Like ServSafe, forklift, CDL"
            onChange={(e) => setCreds(e.target.value)} />
        </div>
      </Question>

      <Alert role="note" className="border-transparent bg-info-soft px-4 py-3">
        <AlertDescription className="text-info">
          We never ask about convictions, your Social Security number, or your exact address. No account needed, and
          your answers aren&apos;t saved.
        </AlertDescription>
      </Alert>

      <Button type="submit" disabled={loading} className="h-13 w-full text-lg font-semibold">
        {loading ? "Finding results…" : "Show my results"}
      </Button>
    </form>
  );
}

"use client";

import { useEffect, useState } from "react";
import { CERTIFICATE_PRESETS } from "@/lib/certificates";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Need, RecommendationRequest } from "@/lib/types";
import { onboardingDraft, type OnboardingDraft } from "@/lib/saved-session";

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

export default function OnboardingForm({ initial, draft, loading, onDraftChange, onSubmit }: {
  initial: RecommendationRequest | null;
  draft: OnboardingDraft | null;
  loading: boolean;
  onDraftChange: (answers: OnboardingDraft) => void;
  onSubmit: (req: RecommendationRequest) => void;
}) {
  const answers = draft ?? onboardingDraft(initial);
  const [location, setLocation] = useState(answers.location);
  const [need, setNeed] = useState<Need | null>(answers.need);
  const [age, setAge] = useState(answers.age);
  const [skills, setSkills] = useState<string[]>(answers.skills);
  const [expText, setExpText] = useState(answers.expText);
  const [years, setYears] = useState(answers.years);
  const [noExp, setNoExp] = useState(answers.noExp);
  const [level, setLevel] = useState(answers.level);
  const [certs, setCerts] = useState<string[]>(answers.certs);
  const [otherCerts, setOtherCerts] = useState(answers.otherCerts);
  const [noCerts, setNoCerts] = useState(answers.noCerts);
  const [tried, setTried] = useState(false);

  useEffect(() => {
    onDraftChange({ location, need, age, skills, expText, years, noExp, level, certs, otherCerts, noCerts });
  }, [location, need, age, skills, expText, years, noExp, level, certs, otherCerts, noCerts, onDraftChange]);

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
        credentials: noCerts ? [] : [...new Set([...certs, ...otherCerts.split(",").map((c) => c.trim()).filter(Boolean)])],
        no_credentials: noCerts,
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
        <Select value={level || "skip"} onValueChange={(value) => setLevel(value === "skip" ? "" : value)}>
          <SelectTrigger id="level" className="w-full bg-card text-base data-[size=default]:h-11">
            <SelectValue placeholder="Choose one (optional)" />
          </SelectTrigger>
          <SelectContent position="popper" align="start" className="max-h-72 w-(--radix-select-trigger-width)">
            <SelectGroup>
              {EDUCATION.map((o) => <SelectItem key={o.value || "skip"} value={o.value || "skip"} className="min-h-10">{o.label}</SelectItem>)}
            </SelectGroup>
          </SelectContent>
        </Select>
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-2 text-sm font-medium">Certificates or licenses you already have</legend>
          <details className="rounded-lg border border-input bg-card p-3">
            <summary className="cursor-pointer font-medium text-brand-text">
              Select certificates or licenses{certs.length ? ` (${certs.length} selected)` : ""}
            </summary>
            <div className="mt-3 flex max-h-60 flex-col gap-3 overflow-y-auto p-1">
              {[...new Set([...CERTIFICATE_PRESETS, ...certs])].map((certificate, index) => (
                <div key={certificate} className="flex items-center gap-2.5">
                  <Checkbox id={`certificate-${index}`} checked={certs.includes(certificate)}
                    onCheckedChange={(checked) => {
                      setCerts((current) => checked === true ? [...current, certificate] : current.filter((item) => item !== certificate));
                      setNoCerts(false);
                    }} />
                  <Label htmlFor={`certificate-${index}`} className="font-normal">{certificate}</Label>
                </div>
              ))}
            </div>
          </details>
          <div className="flex items-center gap-2.5">
            <Checkbox id="no-certificates" checked={noCerts} onCheckedChange={(checked) => {
              setNoCerts(checked === true);
              if (checked === true) { setCerts([]); setOtherCerts(""); }
            }} />
            <Label htmlFor="no-certificates" className="font-normal">I don&apos;t have any certificates or licenses yet</Label>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="creds">Another certificate or license (optional)</Label>
            <Input id="creds" className={field} value={otherCerts} disabled={noCerts} placeholder="Separate more than one with commas"
              onChange={(e) => setOtherCerts(e.target.value)} />
          </div>
          <p className="text-xs text-muted-foreground">Choose all that you already hold, or select none. Add anything unlisted below.</p>
        </fieldset>
      </Question>

      <Alert role="note" className="border-transparent bg-info-soft px-4 py-3">
        <AlertDescription className="text-info">
          We never ask about convictions, your Social Security number, or your exact address. No account needed. Your answers save automatically as you type in this browser,
          along with your plan progress, so you can continue after a refresh.
        </AlertDescription>
      </Alert>

      <Button type="submit" disabled={loading} className="h-13 w-full text-lg font-semibold">
        {loading ? "Finding results…" : "Show my results"}
      </Button>
    </form>
  );
}

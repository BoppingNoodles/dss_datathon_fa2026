"use client";

import { useEffect, useRef, useState } from "react";
import HousingTab from "@/components/HousingTab";
import JobPlan from "@/components/JobPlan";
import JobsTab from "@/components/JobsTab";
import OnboardingForm from "@/components/OnboardingForm";
import ServicesTab from "@/components/ServicesTab";
import ThemeToggle from "@/components/ThemeToggle";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getRecommendations } from "@/lib/api";
import { interimPay } from "@/lib/jobs";
import sample from "@/lib/sample-response.json";
import type { InterimJob, JobCard, Need, PayComparisonJob, RecommendationRequest, RecommendationResponse, Tab } from "@/lib/types";

const TABS: { key: Tab; label: string }[] = [
  { key: "jobs", label: "Jobs" },
  { key: "housing", label: "Housing" },
  { key: "services", label: "Services" },
];
const NEEDS: Need[] = ["work", "housing", "food", "health_care", "transportation", "community_support"];

function tabCount(data: RecommendationResponse, tab: Tab): number | null {
  if (tab === "services") return data.services.groups.reduce((n, g) => n + g.total, 0);
  if (tab === "jobs") return data.jobs.status === "ok" ? data.jobs.groups.reduce((n, g) => n + g.total, 0) : null;
  return data.housing_areas.status === "ok" ? data.housing_areas.areas.length : null;
}

export default function Home() {
  const [request, setRequest] = useState<RecommendationRequest | null>(null);
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [tab, setTab] = useState<Tab>("services");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; unreachable: boolean } | null>(null);
  const [editing, setEditing] = useState(true);
  const [job, setJob] = useState<PayComparisonJob | null>(null);
  const [isSample, setIsSample] = useState(false);
  const [done, setDone] = useState<string[]>([]);
  const [planDone, setPlanDone] = useState<string[]>([]);
  const resultsRef = useRef<HTMLDivElement>(null);
  const requestVersion = useRef(0);

  async function load(req: RecommendationRequest, keepTab = false): Promise<RecommendationResponse | null> {
    const version = ++requestVersion.current;
    setLoading(true);
    setError(null);
    try {
      const res = await getRecommendations(req);
      if (version !== requestVersion.current) return null;
      setRequest(req);
      setData(res);
      setIsSample(false);
      setEditing(false);
      if (!keepTab) {
        setTab(res.open_tab);
        setJob(null);
        setDone([]);
        setPlanDone([]);
        requestAnimationFrame(() => {
          resultsRef.current?.focus({ preventScroll: true });
          resultsRef.current?.scrollIntoView({ block: "start" });
        });
      }
      return res;
    } catch (err) {
      if (version !== requestVersion.current) return null;
      const unreachable = err instanceof TypeError;
      setError({
        unreachable,
        message: unreachable ? "Can't reach the Phoenix server. Check that it's running, then try again." : (err as Error).message,
      });
      return null;
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }

  function focusPlan() {
    requestAnimationFrame(() => {
      const plan = document.getElementById("job-plan");
      plan?.focus({ preventScroll: true });
      plan?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function selectTarget(target: JobCard) {
    if (!request || isSample || loading) return;
    if (data?.selected_job_id === target.job_id) {
      focusPlan();
      return;
    }
    const res = await load({ ...request, selected_job_id: target.job_id, selected_interim_job_id: null }, true);
    if (res) {
      setPlanDone([]);
      setJob(null);
      focusPlan();
    }
  }

  async function selectInterim(id: string | null) {
    if (!request?.selected_job_id || isSample || loading) return;
    const res = await load({ ...request, selected_interim_job_id: id }, true);
    if (res) {
      const interim = res.thirty_day_plan?.interim_jobs.find((option) => option.job_id === id);
      setJob(interim ? { job_id: interim.job_id, title: interim.title, pay: interimPay(interim) } : null);
    }
  }

  async function clearTarget() {
    if (!request || isSample || loading) return;
    const res = await load({ ...request, selected_job_id: null, selected_interim_job_id: null }, true);
    if (res) {
      setPlanDone([]);
      setJob(null);
      requestAnimationFrame(() => {
        resultsRef.current?.focus({ preventScroll: true });
        resultsRef.current?.scrollIntoView({ block: "start" });
      });
    }
  }

  function compareInterim(interim: InterimJob) {
    setJob({ job_id: interim.job_id, title: interim.title, pay: interimPay(interim) });
    setTab("housing");
    requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ block: "start" }));
  }

  // Deep link for demos: /?location=Oakland&need=food
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const location = q.get("location");
    const need = q.get("need") as Need | null;
    if (location && need && NEEDS.includes(need)) {
      const age = Number(q.get("age"));
      load({
        age: Number.isInteger(age) && age >= 14 ? age : null, location, priority_need: need,
        experience: { skills: [], text: null, years: null, no_experience_yet: false },
        education: { level: null, credentials: [] },
        service_sort: "highly_rated", job_sort: "highest_pay",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function showSample() {
    const s = sample as unknown as RecommendationResponse;
    setData(s);
    setTab(s.open_tab);
    setIsSample(true);
    setEditing(false);
    setError(null);
    setJob(null);
    setPlanDone([]);
    setDone([]);
  }

  const showResults = data && !editing;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 pb-16 sm:px-6">
      <header className="flex items-center justify-between py-5">
        <p className="flex items-center gap-2.5 text-[2rem] font-bold tracking-tight sm:text-[2.625rem]">
          {/* Decorative: the name next to it is the accessible label. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {/* Slightly wider than the source 342x701 shape (about 1.4x). */}
          <img src="/phoenix-logo.png" alt="" width={342} height={701} className="h-12 w-9 object-fill sm:h-16 sm:w-11" />
          <span className="phoenix-wordmark">Phoenix</span>
        </p>
        <div className="flex items-center gap-2">
          {showResults && (
            <Button type="button" variant="outline" size="lg" disabled={loading} onClick={() => setEditing(true)}>
              Change my answers
            </Button>
          )}
          <ThemeToggle />
        </div>
      </header>

      {!showResults && (
        <main className="mx-auto max-w-2xl">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Find work, housing, and support near you</h1>
          <p className="mt-2 mb-6 text-lg text-muted-foreground">
            Answer five quick questions. Only the first two are required.
          </p>
          {error && (
            <Alert variant="destructive" className="mb-4 px-4 py-3">
              <AlertTitle className="text-base">{error.message}</AlertTitle>
              {error.unreachable && (
                <AlertDescription>
                  <Button type="button" variant="link" className="h-auto p-0 text-foreground underline" onClick={showSample}>
                    Look at sample results instead (made-up places)
                  </Button>
                </AlertDescription>
              )}
            </Alert>
          )}
          <OnboardingForm initial={request} loading={loading} onSubmit={(r) => load(r)} />
          {data && (
            <Button type="button" variant="ghost" size="lg" className="mt-3 w-full" onClick={() => setEditing(false)}>
              Back to my results
            </Button>
          )}
        </main>
      )}

      {showResults && data && (
        <main ref={resultsRef} tabIndex={-1} className="outline-none">
          {(isSample || data.data_coverage.mode === "synthetic") && (
            <Alert role="status" className="mb-4 border-transparent bg-warn-soft px-4 py-3">
              <AlertTitle className="text-base text-warn">
                {isSample ? "Sample results are fictional and for testing only."
                  : "These jobs, housing summaries, and services are fictional and for testing only."}
              </AlertTitle>
            </Alert>
          )}
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Your results{request && !isSample ? ` for ${request.location}` : ""}
          </h1>
          {loading && <p role="status" className="mt-2 text-sm text-muted-foreground">Updating your results and plan…</p>}

          <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="mt-4 gap-4">
            <TabsList variant="line" aria-label="Results" className="h-auto w-full justify-start gap-2 border-b border-border p-0 group-data-horizontal/tabs:h-auto">
              {TABS.map((t) => {
                const n = tabCount(data, t.key);
                return (
                  <TabsTrigger key={t.key} value={t.key}
                    className="h-11 flex-none px-4 text-base font-semibold data-[state=active]:text-brand-text sm:px-6">
                    {t.label}
                    {n != null && <span className="text-sm font-normal text-muted-foreground">{n.toLocaleString()}</span>}
                  </TabsTrigger>
                );
              })}
            </TabsList>
            {error && (
              <Alert variant="destructive" className="px-4 py-3">
                <AlertTitle className="text-base">{error.message}</AlertTitle>
              </Alert>
            )}
            <div aria-busy={loading} className={`text-base ${loading ? "opacity-60" : ""}`}>
              <TabsContent value="jobs" className="text-base">
                {data.thirty_day_plan && (
                  <JobPlan key={data.thirty_day_plan.target_job_id} plan={data.thirty_day_plan}
                    loading={loading || isSample} completed={planDone}
                    onSelectInterim={selectInterim} onClear={clearTarget} onCompareInterim={compareInterim}
                    onToggleStep={(id, checked) => setPlanDone((current) => checked
                      ? current.includes(id) ? current : [...current, id]
                      : current.filter((step) => step !== id))} />
                )}
                <JobsTab data={data.jobs} loading={loading || isSample}
                  selectedJobId={data.selected_job_id ?? null} onSelect={selectTarget}
                  onSort={(s) => request && load({ ...request, job_sort: s }, true)}
                  onCompare={(j) => { setJob(j); setTab("housing"); }} />
              </TabsContent>
              <TabsContent value="housing" className="text-base">
                <HousingTab data={data.housing_areas} job={job} />
              </TabsContent>
              <TabsContent value="services" className="text-base">
                <ServicesTab data={data.services} loading={loading || isSample}
                  onSort={(s) => request && load({ ...request, service_sort: s }, true)} />
              </TabsContent>
            </div>
          </Tabs>

          {data.next_steps.length > 0 && (
            <Card role="region" aria-labelledby="next" className="mt-8 text-base">
              <CardHeader>
                <CardTitle id="next" className="text-lg">Next steps</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  {data.next_steps.map((s) => (
                    <li key={s.id} className="flex items-start gap-3">
                      <Checkbox id={`step-${s.id}`} className="mt-0.5 size-5" checked={done.includes(s.id)}
                        onCheckedChange={(v) => setDone(v === true ? [...done, s.id] : done.filter((d) => d !== s.id))} />
                      <div>
                        <label htmlFor={`step-${s.id}`} className={done.includes(s.id) ? "text-muted-foreground line-through" : ""}>
                          {s.text}
                        </label>{" "}
                        <Button type="button" variant="link" className="h-auto p-0 text-brand-text underline"
                          onClick={() => { setTab(s.tab); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                          Go to {TABS.find((t) => t.key === s.tab)?.label}
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          <footer className="mt-8 space-y-2 text-sm text-muted-foreground">
            <p>{data.disclaimer}</p>
            <details>
              <summary className="cursor-pointer font-medium">About this data</summary>
              <ul className="mt-1 list-disc pl-5">
                {data.data_coverage.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            </details>
          </footer>
        </main>
      )}
    </div>
  );
}

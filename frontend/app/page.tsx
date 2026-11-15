"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import HousingTab from "@/components/HousingTab";
import JobPlan from "@/components/JobPlan";
import JobsTab from "@/components/JobsTab";
import OnboardingForm from "@/components/OnboardingForm";
import ServicesTab from "@/components/ServicesTab";
import ThemeToggle from "@/components/ThemeToggle";
import { EmptyState } from "@/components/shared";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getRecommendations } from "@/lib/api";
import { withQualificationAnswer } from "@/lib/qualifications";
import { clearOnboardingDraft, clearSavedSession, hasDraftAnswers, makeSavedSession, readOnboardingDraft, readSavedSession, savedPlanDate, writeOnboardingDraft, writeSavedSession, type OnboardingDraft } from "@/lib/saved-session";
import { cacheResults, clearCachedResults, readCachedResults } from "@/lib/results-cache";
import { cn } from "@/lib/utils";
import sample from "@/lib/sample-response.json";
import type { JobCard, Need, PayComparisonJob, RecommendationRequest, RecommendationResponse, Tab } from "@/lib/types";

const TABS: { key: Tab; label: string }[] = [
  { key: "jobs", label: "Jobs" },
  { key: "housing", label: "Housing" },
  { key: "services", label: "Services" },
  { key: "plan", label: "30-day plan" },
];
const NEEDS: Need[] = ["work", "housing", "food", "health_care", "transportation", "community_support"];

function tabCount(data: RecommendationResponse, tab: Tab): number | null {
  if (tab === "plan") return null;
  if (tab === "services") return data.services.groups.reduce((n, g) => n + g.total, 0);
  if (tab === "jobs") return data.jobs.status === "ok" ? [...data.jobs.groups, ...(data.jobs.other_groups ?? [])].reduce((n, g) => n + g.total, 0) : null;
  return data.housing_areas.status === "ok" ? (data.housing_areas.areas.filter((a) => a.area_type === "zip").length || data.housing_areas.areas.length) : null;
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
  const [planStart, setPlanStart] = useState<Date | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [draft, setDraft] = useState<OnboardingDraft | null>(null);
  const [formVersion, setFormVersion] = useState(0);
  const [storageReady, setStorageReady] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "unavailable">("idle");
  const initialized = useRef(false);
  const resultsRef = useRef<HTMLDivElement>(null);
  const requestVersion = useRef(0);
  const currentRequest = useRef<RecommendationRequest | null>(null);
  const confirmed = useRef<{ request: RecommendationRequest; data: RecommendationResponse } | null>(null);
  const qualificationVersion = useRef(0);
  const qualificationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [updatingQualifications, setUpdatingQualifications] = useState(false);

  async function load(req: RecommendationRequest, keepTab = false, background = false): Promise<RecommendationResponse | null> {
    const version = ++requestVersion.current;
    ++qualificationVersion.current;
    if (qualificationTimer.current) clearTimeout(qualificationTimer.current);
    setUpdatingQualifications(false);
    setLoading(!background);
    setRefreshing(background);
    setError(null);
    try {
      const res = await getRecommendations(req);
      if (version !== requestVersion.current || (background && currentRequest.current !== req)) return null;
      setRequest(req);
      currentRequest.current = req;
      confirmed.current = { request: req, data: res };
      setData(res);
      cacheResults(req, res);
      setIsSample(false);
      if (!background) setEditing(false);
      if (!keepTab) {
        setTab(res.open_tab);
        setJob(null);
        setDone([]);
        setPlanDone([]);
        setPlanStart(null);
        requestAnimationFrame(() => {
          resultsRef.current?.focus({ preventScroll: true });
        });
      }
      return res;
    } catch (err) {
      if (version !== requestVersion.current || (background && currentRequest.current !== req)) return null;
      const unreachable = err instanceof TypeError;
      setError({
        unreachable,
        message: background ? "Couldn't refresh results. Your saved results are still available."
          : unreachable ? "Can't reach the Phoenix server. Check that it's running, then try again." : (err as Error).message,
      });
      return null;
    } finally {
      if (version === requestVersion.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }

  function focusPlan() {
    setTab("plan");
    requestAnimationFrame(() => {
      const plan = document.getElementById("job-plan");
      plan?.focus({ preventScroll: true });
    });
  }

  async function selectTarget(target: JobCard) {
    if (!request || isSample || loading) return;
    if (data?.selected_job_id === target.job_id) {
      setPlanStart((current) => current ?? new Date());
      focusPlan();
      return;
    }
    const res = await load({ ...request, selected_job_id: target.job_id }, true);
    if (res) {
      setPlanDone([]);
      setPlanStart(new Date());
      setJob(null);
      focusPlan();
    }
  }

  async function clearTarget() {
    if (!request || isSample || loading) return;
    const res = await load({ ...request, selected_job_id: null }, true);
    if (res) {
      setPlanDone([]);
      setPlanStart(null);
      setJob(null);
      setTab("jobs");
      requestAnimationFrame(() => {
        resultsRef.current?.focus({ preventScroll: true });
      });
    }
  }

  function changeQualification(target: JobCard, key: string, checked: boolean) {
    if (!request || !data || loading || isSample) return;
    const latest = currentRequest.current ?? request;
    const next = { ...latest, qualification_answers: {
      ...latest.qualification_answers,
      [target.job_id]: { ...latest.qualification_answers?.[target.job_id], [key]: checked },
    } };
    currentRequest.current = next;
    setRequest(next);
    setData((current) => current ? { ...current, jobs: withQualificationAnswer(current.jobs, target.job_id, key, checked) } : current);
    setUpdatingQualifications(true);
    setError(null);
    const version = ++qualificationVersion.current;
    const navigation = requestVersion.current;
    if (qualificationTimer.current) clearTimeout(qualificationTimer.current);
    // Batch rapid clicks. Local checks and match feedback remain usable throughout.
    qualificationTimer.current = setTimeout(async () => {
      try {
        const result = await getRecommendations(next);
        if (version !== qualificationVersion.current || navigation !== requestVersion.current) return;
        setData(result);
        cacheResults(next, result);
        confirmed.current = { request: next, data: result };
      } catch {
        if (version !== qualificationVersion.current || navigation !== requestVersion.current) return;
        const previous = confirmed.current;
        if (previous) {
          currentRequest.current = previous.request;
          setRequest(previous.request);
          setData(previous.data);
        }
        setError({ message: "Couldn't update qualifications. Please try again.", unreachable: false });
      } finally {
        if (version === qualificationVersion.current && navigation === requestVersion.current) setUpdatingQualifications(false);
      }
    }, 300);
  }

  useEffect(() => () => {
    ++qualificationVersion.current;
    if (qualificationTimer.current) clearTimeout(qualificationTimer.current);
  }, []);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const { session, available } = readSavedSession();
    const { draft: restoredDraft, available: draftAvailable } = readOnboardingDraft();
    setDraft(restoredDraft);
    setStorageReady(true);
    if (!available || !draftAvailable) setSaveStatus("unavailable");
    if (session) {
      setRequest(session.request);
      currentRequest.current = session.request;
      setTab(session.tab);
      setDone(session.done);
      setPlanDone(session.plan?.completed ?? []);
      setPlanStart(session.plan ? savedPlanDate(session.plan.startDate)
        : session.request.selected_job_id ? new Date() : null);
      const cached = readCachedResults(session.request);
      if (cached) {
        setData(cached);
        confirmed.current = { request: session.request, data: cached };
      }
      if (restoredDraft) {
        setRestoring(false);
      } else if (cached) {
        setEditing(false);
        setRestoring(false);
        void load(session.request, true, true);
      } else {
        void load(session.request, true).finally(() => setRestoring(false));
      }
      return;
    }
    if (restoredDraft) {
      setRestoring(false);
      return;
    }
    // Demo links apply to a fresh browser; refreshes resume the saved session.
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
      }).finally(() => setRestoring(false));
    } else {
      setRestoring(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!storageReady || !request || isSample) return;
    const saved = writeSavedSession(makeSavedSession(request, tab, done, planDone, planStart));
    setSaveStatus(saved ? "saved" : "unavailable");
  }, [storageReady, request, tab, done, planDone, planStart, isSample]);

  const saveDraft = useCallback((answers: OnboardingDraft) => {
    setDraft(hasDraftAnswers(answers) ? answers : null);
    const saved = writeOnboardingDraft(answers);
    setSaveStatus(saved ? "saved" : "unavailable");
  }, []);

  async function submitAnswers(answers: RecommendationRequest) {
    const result = await load(answers);
    if (result) {
      setDraft(null);
      if (!clearOnboardingDraft()) setSaveStatus("unavailable");
    }
  }

  function backToResults() {
    setDraft(null);
    clearOnboardingDraft();
    if (data) setEditing(false);
    else if (request) void load(request, true);
  }

  function clearSavedData() {
    const sessionCleared = clearSavedSession();
    const draftCleared = clearOnboardingDraft();
    const cacheCleared = clearCachedResults();
    if (!sessionCleared || !draftCleared || !cacheCleared) {
      setError({ message: "Couldn't clear saved data. Check your browser's storage settings and try again.", unreachable: false });
      return;
    }
    ++requestVersion.current;
    ++qualificationVersion.current;
    if (qualificationTimer.current) clearTimeout(qualificationTimer.current);
    currentRequest.current = null;
    confirmed.current = null;
    setUpdatingQualifications(false);
    setRequest(null);
    setData(null);
    setDraft(null);
    setFormVersion((current) => current + 1);
    setEditing(true);
    setIsSample(false);
    setJob(null);
    setDone([]);
    setPlanDone([]);
    setPlanStart(null);
    setTab("services");
    setError(null);
    setSaveStatus("idle");
    const url = new URL(window.location.href);
    for (const key of ["location", "need", "age"]) url.searchParams.delete(key);
    window.history.replaceState(null, "", url);
    window.scrollTo({ top: 0 });
  }

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

  useEffect(() => {
    if (showResults) window.scrollTo({ top: 0 });
  }, [showResults, tab]);

  return (
    <div className={cn("mx-auto w-full px-4 pb-16 sm:px-6", showResults && tab === "housing" ? "max-w-7xl" : "max-w-5xl")}>
      <header className="grid grid-cols-[1fr_auto] items-center gap-3 py-5 sm:flex sm:justify-between">
        <p className="flex items-center gap-2.5 text-[2rem] font-bold tracking-tight sm:text-[2.625rem]">
          {/* Decorative: the name next to it is the accessible label. */}
          {/* Flame-gradient phoenix: the PNG is used as a mask, slightly wider than its 342x701 shape. */}
          <span aria-hidden className="inline-block h-12 w-9 shrink-0 sm:h-16 sm:w-11 bg-[linear-gradient(170deg,#e08a12_0%,#e8701a_38%,#c23d18_70%,#8f2410_100%)] dark:bg-[linear-gradient(170deg,#ffd56b_0%,#ff9a3c_40%,#f2643a_75%,#d9452a_100%)] [mask:url(/phoenix-logo.png)_center/100%_100%_no-repeat] drop-shadow-[0_2px_6px_rgb(240_122_26/0.3)]" />
          <span className="phoenix-wordmark">Phoenix</span>
        </p>
        <div className="contents sm:flex sm:items-center sm:gap-2">
          {showResults && (
            <Button type="button" variant="outline" size="lg" className="order-last col-span-2 w-full sm:order-none sm:w-auto" disabled={loading} onClick={() => setEditing(true)}>
              Change my answers
            </Button>
          )}
          <ThemeToggle />
        </div>
      </header>

      {restoring && <main className="mx-auto max-w-2xl py-8"><p role="status" className="text-muted-foreground">Opening your saved results…</p></main>}

      {!restoring && !showResults && (
        <main className="mx-auto max-w-2xl">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Find work, housing, and support near you</h1>
          <p className="mt-2 mb-6 text-lg text-muted-foreground">
            Answer five quick questions. Only the first two are required.
          </p>
          {error && (
            <Alert variant="destructive" className="mb-4 px-4 py-3">
              <AlertTitle className="text-base">{error.message}</AlertTitle>
              {(request || error.unreachable) && (
                <AlertDescription className="flex flex-col items-start gap-2">
                  {request && <>
                    <p>Your saved answers and plan progress are still here.</p>
                    <Button type="button" variant="link" disabled={loading} className="h-auto p-0 text-foreground underline" onClick={() => load(request, true)}>
                      Try saved results again
                    </Button>
                  </>}
                  {error.unreachable && <Button type="button" variant="link" className="h-auto p-0 text-foreground underline" onClick={showSample}>
                    Look at sample results instead (made-up places)
                  </Button>}
                </AlertDescription>
              )}
            </Alert>
          )}
          <OnboardingForm key={formVersion} initial={request} draft={draft} loading={loading} onDraftChange={saveDraft} onSubmit={submitAnswers} />
          {(data || request) && (
            <Button type="button" variant="ghost" size="lg" className="mt-3 w-full" disabled={loading} onClick={backToResults}>
              Back to my results
            </Button>
          )}
        </main>
      )}

      {!restoring && showResults && data && (
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
          {refreshing && <p role="status" className="mt-2 text-sm text-muted-foreground">Showing saved results · refreshing in the background…</p>}
          {updatingQualifications && <p role="status" className="mt-2 text-sm text-muted-foreground">Updating qualifications and plan…</p>}

          <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="mt-4 gap-4">
            <TabsList variant="line" aria-label="Results" className="h-auto w-full justify-start gap-0 border-b border-border p-0 group-data-horizontal/tabs:h-auto sm:gap-2">
              {TABS.map((t) => {
                const n = tabCount(data, t.key);
                return (
                  <TabsTrigger key={t.key} value={t.key}
                    className="h-11 min-w-0 flex-1 px-1.5 text-sm font-semibold data-[state=active]:text-brand-text sm:flex-none sm:px-5 sm:text-base">
                    {t.label}
                    {n != null && <span className="hidden text-sm font-normal text-muted-foreground sm:inline">{n.toLocaleString()}</span>}
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
                <JobsTab data={data.jobs} loading={loading || isSample}
                  selectedJobId={data.selected_job_id ?? null} onSelect={selectTarget}
                  onQualificationChange={changeQualification}
                  onSort={(s) => request && load({ ...request, job_sort: s }, true)}
                  onCompare={(j) => { setJob(j); setTab("housing"); }} />
              </TabsContent>
              <TabsContent value="plan" className="text-base">
                {data.thirty_day_plan && planStart ? (
                  <JobPlan key={data.thirty_day_plan.target_job_id} plan={data.thirty_day_plan} startDate={planStart}
                    loading={loading || isSample} completed={planDone} onClear={clearTarget}
                    onToggleStep={(id, checked) => setPlanDone((current) => checked
                      ? current.includes(id) ? current : [...current, id]
                      : current.filter((step) => step !== id))} />
                ) : (
                  <div className="flex flex-col items-center gap-4 py-6">
                    <EmptyState title="A fresh start, one day at a time">
                      Choose a job you want to work toward. Your daily steps will appear here in a 30-day calendar.
                    </EmptyState>
                    <Button type="button" onClick={() => setTab("jobs")}>Find a job to work toward</Button>
                  </div>
                )}
              </TabsContent>
              <TabsContent value="housing" className="text-base">
                <HousingTab data={data.housing_areas} job={job} mapPoints={data.service_map_points} />
              </TabsContent>
              <TabsContent value="services" className="text-base">
                <ServicesTab data={data.services} loading={loading || isSample}
                  onSort={(s) => request && load({ ...request, service_sort: s }, true)} />
              </TabsContent>
            </div>
          </Tabs>

          {data.next_steps.length > 0 && tab !== "plan" && (
            <details className="mt-6">
            <summary className="cursor-pointer text-sm font-medium text-muted-foreground">A few next steps</summary>
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
            </details>
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
      {!restoring && !isSample && (request || draft || saveStatus === "unavailable") && (
        <aside aria-label="Saved data" className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-4 text-xs text-muted-foreground">
          <p role="status">{saveStatus === "unavailable"
            ? "Saving is unavailable in this browser. Your answers and progress may be lost when you close or refresh this page."
            : "Answers and progress saved in this browser. They don't sync to other devices."}</p>
          {(request || draft) && <Button type="button" variant="link" size="sm" disabled={loading} onClick={clearSavedData}
            className="h-auto p-0 text-xs text-muted-foreground underline">Clear saved data</Button>}
        </aside>
      )}
    </div>
  );
}

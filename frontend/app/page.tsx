"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import FinancesTab from "@/components/FinancesTab";
import HousingTab from "@/components/HousingTab";
import JobPlan from "@/components/JobPlan";
import JobsTab from "@/components/JobsTab";
import OnboardingForm from "@/components/OnboardingForm";
import ReentryPlan from "@/components/ReentryPlan";
import AdaptivePlan, { PlanHistory, SelectedOpportunities } from "@/components/AdaptivePlan";
import SituationUpdate from "@/components/SituationUpdate";
import SituationChat from "@/components/SituationChat";
import PhoenixThinking from "@/components/PhoenixThinking";
import { ResourceContext } from "@/components/ResourceActions";
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
import { withReentryCompletion } from "@/lib/reentry";
import { dateKey } from "@/lib/plan";
import { adoptSession, hasRequiredReentryAnswers, ONBOARDING_VERSION } from "@/lib/onboarding";
import { userEvent, type UserEvent, type ReentryProfile } from "@/lib/domain";
import { releaseSummary } from "@/lib/plan-view";
import { clearOnboardingDraft, clearSavedSession, hasDraftAnswers, hasNewerSavedHistory, makeSavedSession, onboardingDraft, readOnboardingDraft, readSavedSession, savedPlanDate, writeOnboardingDraft, writeSavedSession, type OnboardingDraft } from "@/lib/saved-session";
import { cacheResults, clearCachedResults, readCachedResults } from "@/lib/results-cache";
import { cn } from "@/lib/utils";
import type { JobCard, Need, RecommendationRequest, RecommendationResponse, Tab } from "@/lib/types";

const TABS: { key: Tab; label: string }[] = [
  { key: "finances", label: "Finances" },
  { key: "jobs", label: "Jobs" },
  { key: "housing", label: "Housing" },
  { key: "services", label: "Services" },
  { key: "plan", label: "Calendar" },
];
const NEEDS: Need[] = ["work", "housing", "food", "health_care", "transportation", "community_support"];

function tabCount(data: RecommendationResponse, tab: Tab): number | null {
  if (tab === "plan" || tab === "finances") return null;
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
  const [updatingSituation, setUpdatingSituation] = useState(false);
  const [dashboardTab, setDashboardTab] = useState<"plan" | "resources">("plan");
  const [calendarScope, setCalendarScope] = useState<"reentry" | "job">("reentry");
  const [onboardingComplete, setOnboardingComplete] = useState(false);
  const [isSample, setIsSample] = useState(false);
  const [done, setDone] = useState<string[]>([]);
  const [planDone, setPlanDone] = useState<string[]>([]);
  const [planStart, setPlanStart] = useState<Date | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [draft, setDraft] = useState<OnboardingDraft | null>(null);
  const [formVersion, setFormVersion] = useState(0);
  const [storageReady, setStorageReady] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "unavailable" | "newer">("idle");
  const [recovery, setRecovery] = useState<string | null>(null);
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
      if (!res.reentry_plan) throw new Error("Your reentry plan could not be created. Please try again.");
      const accepted = adoptSession(req, res);
      setRequest(accepted);
      currentRequest.current = accepted;
      confirmed.current = { request: accepted, data: res };
      setData(res);
      cacheResults(accepted, res);
      setIsSample(false);
      if (!background) setEditing(false);
      if (!keepTab) {
        setTab(res.open_tab);
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
          : unreachable ? "We couldn't load your plan. Check your connection and try again." : (err as Error).message,
      });
      return null;
    } finally {
      if (version === requestVersion.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }

  function openResources(next: Tab, serviceNeed?: Need) {
    setDashboardTab("resources");
    const latest = currentRequest.current ?? request;
    if (next === "services" && serviceNeed && latest && serviceNeed !== (latest.service_need ?? latest.priority_need)) {
      void load({ ...latest, service_need: serviceNeed }, true);
    }
    setTab(next);
    requestAnimationFrame(() => {
      const resources = document.getElementById(next === "plan" ? "plan-calendar" : "plan-resources");
      resources?.focus({ preventScroll: true });
      resources?.scrollIntoView({ block: "start" });
    });
  }

  function backToPlan() {
    setDashboardTab("plan");
    requestAnimationFrame(() => resultsRef.current?.focus({ preventScroll: true }));
    window.scrollTo({ top: 0 });
  }

  async function applyEvent(event: UserEvent): Promise<boolean> {
    const latest = currentRequest.current;
    if (!latest?.phoenix_session || loading) return false;
    const id = event.payload.recommendationId;
    let selected = latest.selected_job_id;
    if (typeof id === "string" && id.startsWith("job:") && event.type === "resource_status") {
      if (event.payload.status === "selected") selected = id.slice(4);
      else if (id === `job:${selected}` && ["recommended", "saved", "dismissed", "rejected"].includes(String(event.payload.status))) selected = null;
    }
    const response = await load({ ...latest, selected_job_id: selected, user_event: event }, true);
    if (response?.selected_job_id) setPlanStart((date) => date ?? new Date());
    return !!response;
  }

  function openResource(id: string) {
    const resource = data?.phoenix_session?.recommendations.find((r) => r.id === id);
    if (!resource) return;
    openResources(resource.category === "job" ? "jobs" : resource.category === "housing" ? "housing" : "services");
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const card = Array.from(document.querySelectorAll<HTMLElement>('[data-resource-id]')).find((node) => node.dataset.resourceId === id && !!node.closest('#plan-resources'));
      if (card) { for (let parent = card.parentElement; parent; parent = parent.parentElement) if (parent instanceof HTMLDetailsElement) parent.open = true;
        card.scrollIntoView({ block: "center" }); }
    }));
  }

  async function previewProfile(profile: ReentryProfile, event?: UserEvent) {
    const latest = currentRequest.current!;
    return getRecommendations({ ...latest, profile, user_event: event ?? userEvent("profile_updated", { profile }) });
  }

  function confirmSituation(response: RecommendationResponse, returnToPlan = true) {
    if (!currentRequest.current || !response.phoenix_session) return;
    const accepted = adoptSession(currentRequest.current, response);
    currentRequest.current = accepted;
    confirmed.current = { request: accepted, data: response };
    setRequest(accepted); setData(response); cacheResults(accepted, response);
    setDraft(null);
    if (!clearOnboardingDraft()) setSaveStatus("unavailable");
    setUpdatingSituation(false);
    if (returnToPlan) backToPlan();
  }

  async function clearTarget() {
    if (!request || isSample || loading) return;
    const res = await load({ ...request, selected_job_id: null,
      ...(request.phoenix_session && request.selected_job_id ? { user_event: userEvent("resource_status", { recommendationId: `job:${request.selected_job_id}`, status: "recommended" }) } : {}) }, true);
    if (res) {
      setPlanDone([]);
      setPlanStart(null);
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
    queueUpdate(next, { ...data, jobs: withQualificationAnswer(data.jobs, target.job_id, key, checked) });
  }

  function changeReentryCompletion(id: string, checked: boolean) {
    if (!request || !data?.reentry_plan || loading || isSample) return;
    const latest = currentRequest.current ?? request;
    const plan = withReentryCompletion(data.reentry_plan, latest.reentry_completed_ids ?? [], id, checked);
    queueUpdate({ ...latest, reentry_completed_ids: plan.completed_ids }, { ...data, reentry_plan: plan });
  }

  function queueUpdate(next: RecommendationRequest, optimistic: RecommendationResponse) {
    currentRequest.current = next;
    setRequest(next);
    setData(optimistic);
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
        const accepted = adoptSession(next, result);
        currentRequest.current = accepted; setRequest(accepted);
        setData(result);
        cacheResults(accepted, result);
        confirmed.current = { request: accepted, data: result };
      } catch {
        if (version !== qualificationVersion.current || navigation !== requestVersion.current) return;
        const previous = confirmed.current;
        if (previous) {
          currentRequest.current = previous.request;
          setRequest(previous.request);
          setData(previous.data);
        }
        setError({ message: "Couldn't save your update. Please try again.", unreachable: false });
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
    const { session, available, recovery: damagedState } = readSavedSession();
    setRecovery(damagedState ?? null);
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
      const complete = session.onboardingVersion === ONBOARDING_VERSION && !!session.request.profile && hasRequiredReentryAnswers(session.request);
      setOnboardingComplete(complete);
      if (!complete) {
        setRestoring(false);
        return;
      }
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
    // Demo links prefill the required form; they cannot skip onboarding.
    const q = new URLSearchParams(window.location.search);
    const location = q.get("location");
    const need = q.get("need") as Need | null;
    if (location && need && NEEDS.includes(need)) {
      setDraft({ ...onboardingDraft(null), location, need });
    }
    setRestoring(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!storageReady || !request || isSample) return;
    const saved = writeSavedSession(makeSavedSession(request, tab, done, planDone, planStart, onboardingComplete ? ONBOARDING_VERSION : undefined));
    setSaveStatus(saved ? "saved" : hasNewerSavedHistory(request) ? "newer" : "unavailable");
  }, [storageReady, request, tab, done, planDone, planStart, isSample, onboardingComplete]);

  const saveDraft = useCallback((answers: OnboardingDraft) => {
    setDraft(hasDraftAnswers(answers) ? answers : null);
    const saved = writeOnboardingDraft(answers);
    setSaveStatus(saved ? "saved" : "unavailable");
  }, []);

  async function submitAnswers(answers: RecommendationRequest) {
    if (!hasRequiredReentryAnswers(answers)) return;
    const keepGoal = !!answers.selected_job_id && answers.selected_job_id === request?.selected_job_id;
    const result = await load({ ...answers, reentry_start_date: answers.reentry_start_date ?? dateKey(new Date()) }, keepGoal);
    if (result) {
      setOnboardingComplete(true);
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
    setOnboardingComplete(false);
    setUpdatingSituation(false);
    setDashboardTab("plan");
    setIsSample(false);
    setDone([]);
    setPlanDone([]);
    setPlanStart(null);
    setTab("services");
    setError(null);
    setSaveStatus("idle");
    setRecovery(null);
    const url = new URL(window.location.href);
    for (const key of ["location", "need", "age"]) url.searchParams.delete(key);
    window.history.replaceState(null, "", url);
    window.scrollTo({ top: 0 });
  }

  const showResults = data && !editing && onboardingComplete;
  const selectedTarget = data?.selected_job_id
    ? [...data.jobs.groups, ...(data.jobs.other_groups ?? [])].flatMap((group) => group.items).find((item) => item.job_id === data.selected_job_id) ?? null
    : null;
  const adaptive = data?.phoenix_session;
  async function completeCalendar(id: string, checked: boolean) {
    const day = adaptive?.schedule.find((d) => d.action_id === id);
    for (const taskId of day?.task_ids ?? []) {
      await applyEvent(userEvent("task_status", { taskId, status: checked ? "completed" : "not_started" }));
    }
  }

  useEffect(() => {
    if (showResults && !updatingSituation) {
      resultsRef.current?.focus({ preventScroll: true });
      window.scrollTo({ top: 0 });
    }
  }, [showResults, updatingSituation]);

  return (
    <ResourceContext.Provider value={{ session: adaptive ?? null, disabled: loading || updatingQualifications || isSample, onEvent: (event) => { void applyEvent(event); } }}>
    <div className={cn("mx-auto w-full px-4 pb-16 sm:px-6", showResults && dashboardTab === "resources" && tab === "housing" ? "max-w-7xl" : "max-w-6xl")}>
      <header className="grid grid-cols-[1fr_auto] items-center gap-3 py-5 sm:flex sm:justify-between">
        <p className="flex items-center gap-2.5 text-[2rem] font-bold tracking-tight sm:text-[2.625rem]">
          {/* Decorative: the name next to it is the accessible label. */}
          {/* Flame-gradient phoenix: the PNG is used as a mask, slightly wider than its 342x701 shape. */}
          <span aria-hidden className="inline-block h-12 w-9 shrink-0 sm:h-16 sm:w-11 bg-[linear-gradient(170deg,#e08a12_0%,#e8701a_38%,#c23d18_70%,#8f2410_100%)] dark:bg-[linear-gradient(170deg,#ffd56b_0%,#ff9a3c_40%,#f2643a_75%,#d9452a_100%)] [mask:url(/phoenix-logo.png)_center/100%_100%_no-repeat] drop-shadow-[0_2px_6px_rgb(240_122_26/0.3)]" />
          <span className="phoenix-wordmark">Phoenix</span>
        </p>
        <div className="contents sm:flex sm:items-center sm:gap-2">
          {showResults && !updatingSituation && (
            <><span className="hidden text-xs text-muted-foreground lg:inline">{adaptive ? releaseSummary(adaptive.profile) : ""}</span><Button type="button" variant={request?.phoenix_session ? "default" : "outline"} size="lg" className="order-last col-span-2 w-full sm:order-none sm:w-auto" disabled={loading || updatingQualifications || refreshing} onClick={() => request?.phoenix_session ? setUpdatingSituation(true) : setEditing(true)}>
              {request?.phoenix_session ? "View / update my situation" : "Change my answers"}
            </Button></>
          )}
          <ThemeToggle />
        </div>
      </header>

      {restoring && <main className="mx-auto max-w-2xl py-8"><p role="status" className="text-muted-foreground">Opening your reentry plan…</p></main>}
      {recovery && <Alert className="mb-4" role="alert"><AlertTitle>Your saved plan needs recovery</AlertTitle><AlertDescription><p>Some saved fields could not be read safely. The original data is preserved. Download a backup before rebuilding your plan; completed history has not been replaced.</p><Button type="button" variant="link" onClick={() => { const url = URL.createObjectURL(new Blob([recovery], { type: "application/json" })); const link = document.createElement("a"); link.href = url; link.download = "phoenix-plan-recovery.json"; link.click(); URL.revokeObjectURL(url); }}>Download saved plan backup</Button></AlertDescription></Alert>}
      {!restoring && updatingSituation && request?.phoenix_session && <main><SituationUpdate request={request} onPreview={previewProfile} onConfirm={confirmSituation} onCancel={() => { setUpdatingSituation(false); backToPlan(); }} /></main>}

      {!restoring && !showResults && (
        <main className="mx-auto max-w-2xl">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Plan your return to the community</h1>
          <p className="mt-2 mb-6 text-base text-muted-foreground">A few answers. A plan that fits your needs.</p>
          {error && (
            <Alert variant="destructive" className="mb-4 px-4 py-3">
              <AlertTitle className="text-base">{error.message}</AlertTitle>
              {request && onboardingComplete && (
                <AlertDescription className="flex flex-col items-start gap-2">
                  <>
                    <p>Your saved answers and plan progress are still here.</p>
                    <Button type="button" variant="link" disabled={loading} className="h-auto p-0 text-foreground underline" onClick={() => load(request, true)}>
                      Try my saved plan again
                    </Button>
                  </>
                </AlertDescription>
              )}
            </Alert>
          )}
          <OnboardingForm key={formVersion} initial={request} draft={draft} loading={loading} onDraftChange={saveDraft} onSubmit={submitAnswers} />
          {onboardingComplete && (data || request) && (
            <Button type="button" variant="ghost" size="lg" className="mt-3 w-full" disabled={loading} onClick={backToResults}>
              Back to my reentry plan
            </Button>
          )}
        </main>
      )}

      {!restoring && showResults && !updatingSituation && data && (
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
            Your Reentry Plan
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">{request?.location}</p>
          <div className="mt-2 min-h-5">{(loading || updatingQualifications || refreshing) && <PhoenixThinking />}</div>

          {error && <Alert variant="destructive" role="alert" className="my-3"><AlertTitle>{error.message}</AlertTitle></Alert>}
          <Tabs value={dashboardTab} onValueChange={value => {
            setDashboardTab(value as "plan" | "resources");
          }} className="mt-4 gap-4">
            <TabsList variant="line" aria-label="Dashboard" className="sticky top-0 z-10 h-12 w-full justify-start gap-2 border-b bg-background p-0">
              <TabsTrigger value="plan" className="h-12 px-5 text-base font-semibold">Plan</TabsTrigger>
              <TabsTrigger value="resources" className="h-12 px-5 text-base font-semibold">Resources</TabsTrigger>
            </TabsList>
            <TabsContent value="plan" forceMount hidden={dashboardTab !== "plan"}>
              <div>
                {adaptive ? <AdaptivePlan session={adaptive} disabled={loading || updatingQualifications || isSample} onEvent={applyEvent} onOpenResource={openResource} onEditSituation={() => setUpdatingSituation(true)} onOpenCalendar={() => { setCalendarScope("reentry"); openResources("plan"); }} />
                  : data.reentry_plan && <ReentryPlan plan={data.reentry_plan} heading="Your next steps" disabled={loading || isSample} onToggle={changeReentryCompletion} onOpenResources={openResources} />}
                {adaptive && <PlanHistory session={adaptive} disabled={loading || updatingQualifications || isSample} onEvent={applyEvent} onOpenResource={openResource} />}
              </div>

            </TabsContent>
            <TabsContent value="resources" forceMount hidden={dashboardTab !== "resources"}>
              <section id="plan-resources" tabIndex={-1} aria-labelledby="plan-resources-title" className="scroll-mt-16 outline-none">
                <h2 id="plan-resources-title" className="sr-only">Resources</h2>
                {adaptive && <SelectedOpportunities session={adaptive} onOpenResource={openResource} />}
                <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="mt-4 gap-4">
                  <div className="min-w-0 overflow-x-auto"><TabsList variant="line" aria-label="Resource categories" className="h-auto w-full min-w-max justify-start gap-0 border-b border-border p-0 group-data-horizontal/tabs:h-auto sm:gap-2">
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
                  </TabsList></div>
                  <div aria-busy={loading} className={`text-base ${loading ? "opacity-60" : ""}`}>
                    <TabsContent value="finances" className="text-base">
                      {adaptive && <FinancesTab session={adaptive} preferredJobId={data.selected_job_id} disabled={loading || updatingQualifications || isSample} onPreview={previewProfile} onConfirm={response => confirmSituation(response, false)} onOpenResource={openResource} />}
                    </TabsContent>
                    <TabsContent value="plan" className="text-base">
              <section id="plan-calendar" tabIndex={-1} aria-label="Plan calendar" className="scroll-mt-16 space-y-4 outline-none">
                {adaptive && <div className="mb-4 flex gap-2"><Button type="button" variant={calendarScope === "reentry" ? "default" : "outline"} onClick={() => setCalendarScope("reentry")}>All reentry steps</Button>{data.thirty_day_plan && <Button type="button" variant={calendarScope === "job" ? "default" : "outline"} onClick={() => setCalendarScope("job")}>Selected job preparation</Button>}</div>}
                {adaptive && (calendarScope === "reentry" || !data.thirty_day_plan) ? <JobPlan idPrefix="reentry-calendar" plan={{ daily_actions: adaptive.schedule, credential_paths: [], steps: [], notes: ["Suggested days are flexible planning slots. Only dates you entered are deadlines."], target_job_title: "Your return to the community" }}
                  startDate={savedPlanDate(adaptive.scheduleStartDate ?? request?.reentry_start_date ?? "") ?? new Date()} loading={loading || isSample}
                  completed={adaptive.schedule.filter((d) => d.task_ids.length && d.task_ids.every((id) => adaptive.tasks.find((t) => t.id === id)?.status === "completed")).map((d) => d.action_id)}
                  dayTasks={Object.fromEntries(adaptive.schedule.map((d) => [d.action_id, d.task_ids.flatMap((id) => adaptive.tasks.filter((t) => t.id === id).map((t) => ({ title: t.title, action: t.description })))]))}
                  blockedActionIds={adaptive.schedule.filter((d) => d.task_ids.some((id) => adaptive.tasks.find((t) => t.id === id)?.status === "blocked")).map((d) => d.action_id)}
                  reviewOnlyActionIds={adaptive.schedule.filter((d) => !d.task_ids.length).map((d) => d.action_id)}
                  onToggleStep={(id, checked) => { void completeCalendar(id, checked); }} /> : data.thirty_day_plan && planStart ? (
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
                    <Button type="button" onClick={() => openResources("jobs")}>Find a job to work toward</Button>
                  </div>
                )}

              </section>
                    </TabsContent>
                    <TabsContent value="jobs" className="text-base">
                      <JobsTab data={data.jobs} loading={loading || isSample}
                        onQualificationChange={changeQualification}
                        onSort={(s) => request && load({ ...request, job_sort: s }, true)} />
                    </TabsContent>

                    <TabsContent value="housing" className="text-base">
                      <HousingTab data={data.housing_areas} selectedJob={selectedTarget} mapPoints={data.service_map_points} />
                    </TabsContent>
                    <TabsContent value="services" className="text-base">
                      <ServicesTab data={data.services} loading={loading || isSample}
                        onSort={(s) => request && load({ ...request, service_sort: s }, true)} />
                    </TabsContent>
                  </div>
                </Tabs>
              </section>
            </TabsContent>
          </Tabs>

          {dashboardTab === "plan" && !data.reentry_plan && data.next_steps.length > 0 && tab !== "plan" && (
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
                          onClick={() => openResources(s.tab)}>
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

          <footer className="mt-8 space-y-2 text-xs text-muted-foreground">
            <p>Confirm availability with each provider.</p>
            <details>
              <summary className="cursor-pointer font-medium">Data &amp; sources</summary>
              <p className="mt-2">{data.disclaimer}</p>
              <ul className="mt-1 list-disc pl-5">
                {data.data_coverage.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            </details>
          </footer>
        </main>
      )}
      {showResults && !updatingSituation && request?.phoenix_session && <SituationChat request={request} disabled={loading || updatingQualifications || refreshing} onPreview={previewProfile} onConfirm={response => confirmSituation(response, false)} onEdit={() => setUpdatingSituation(true)} />}
      {!restoring && !isSample && (request || draft || saveStatus === "unavailable") && (
        <aside aria-label="Saved data" className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-4 text-xs text-muted-foreground">
          <p role="status">{saveStatus === "newer" ? "A newer plan is saved in another tab. Refresh to continue." : saveStatus === "unavailable"
            ? "Changes aren’t saving. Keep this tab open and try again."
            : "Saved on this device."}</p>
          {saveStatus === "newer" && <Button type="button" variant="link" size="sm" className="h-auto p-0 text-xs underline" onClick={() => window.location.reload()}>Refresh saved plan</Button>}
          {(request || draft) && <Button type="button" variant="link" size="sm" disabled={loading} onClick={clearSavedData}
            className="h-auto p-0 text-xs text-muted-foreground underline">Clear saved data</Button>}
        </aside>
      )}
    </div>
    </ResourceContext.Provider>
  );
}

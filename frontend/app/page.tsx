"use client";

import { useEffect, useRef, useState } from "react";
import HousingTab from "@/components/HousingTab";
import JobsTab from "@/components/JobsTab";
import OnboardingForm from "@/components/OnboardingForm";
import ServicesTab from "@/components/ServicesTab";
import ThemeToggle from "@/components/ThemeToggle";
import { getRecommendations } from "@/lib/api";
import sample from "@/lib/sample-response.json";
import type { JobCard, Need, RecommendationRequest, RecommendationResponse, Tab } from "@/lib/types";

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
  const [job, setJob] = useState<JobCard | null>(null);
  const [isSample, setIsSample] = useState(false);
  const [done, setDone] = useState<string[]>([]);
  const resultsRef = useRef<HTMLDivElement>(null);

  async function load(req: RecommendationRequest, keepTab = false) {
    setLoading(true);
    setError(null);
    setRequest(req);
    try {
      const res = await getRecommendations(req);
      setData(res);
      setIsSample(false);
      setEditing(false);
      if (!keepTab) {
        setTab(res.open_tab);
        setJob(null);
        setDone([]);
        requestAnimationFrame(() => resultsRef.current?.focus({ preventScroll: true }));
      }
    } catch (err) {
      const unreachable = err instanceof TypeError;
      setError({
        unreachable,
        message: unreachable ? "Can't reach the Phoenix server. Check that it's running, then try again." : (err as Error).message,
      });
    } finally {
      setLoading(false);
    }
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
  }

  const showResults = data && !editing;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 pb-16 sm:px-6">
      <header className="flex items-center justify-between py-5">
        <p className="text-2xl font-bold tracking-tight">
          <span className="text-brand-text">Phoenix</span>
        </p>
        <div className="flex items-center gap-2">
          {showResults && (
            <button type="button" onClick={() => setEditing(true)}
              className="rounded-lg border border-line bg-card px-3 py-1.5 text-sm font-medium hover:border-brand">
              Change my answers
            </button>
          )}
          <ThemeToggle />
        </div>
      </header>

      {!showResults && (
        <main className="mx-auto max-w-2xl">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Find work, housing, and support near you</h1>
          <p className="mt-2 mb-6 text-lg text-muted">
            Answer five quick questions. Only the first two are required.
          </p>
          {error && (
            <div role="alert" className="mb-4 rounded-lg border border-brand/40 bg-brand-soft px-4 py-3">
              <p className="font-medium text-brand-text">{error.message}</p>
              {error.unreachable && (
                <button type="button" onClick={showSample} className="mt-2 text-sm font-semibold underline">
                  Look at sample results instead (made-up places)
                </button>
              )}
            </div>
          )}
          <OnboardingForm initial={request} loading={loading} onSubmit={(r) => load(r)} />
          {data && (
            <button type="button" onClick={() => setEditing(false)} className="mt-4 w-full text-center text-sm font-medium underline">
              Back to my results
            </button>
          )}
        </main>
      )}

      {showResults && data && (
        <main ref={resultsRef} tabIndex={-1} className="outline-none">
          {(isSample || data.data_coverage.mode === "synthetic") && (
            <p role="status" className="mb-4 rounded-lg bg-warn-soft px-4 py-3 font-medium text-warn">
              Sample data: these places are made up for testing. Don&apos;t rely on them.
            </p>
          )}
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Your results{request && !isSample ? ` for ${request.location}` : ""}
          </h1>

          <div role="tablist" aria-label="Results" className="mt-4 flex gap-1 border-b border-line">
            {TABS.map((t) => {
              const n = tabCount(data, t.key);
              return (
                <button
                  key={t.key} role="tab" id={`tab-${t.key}`} aria-selected={tab === t.key} aria-controls={`panel-${t.key}`}
                  onClick={() => setTab(t.key)}
                  className={`-mb-px rounded-t-lg border-b-2 px-4 py-2.5 text-base font-semibold sm:px-6 ${
                    tab === t.key ? "border-brand text-brand-text" : "border-transparent text-muted hover:text-ink"
                  }`}
                >
                  {t.label}
                  {n != null && <span className="ml-1.5 text-sm font-normal text-muted">{n.toLocaleString()}</span>}
                </button>
              );
            })}
          </div>

          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} aria-busy={loading}
            className={`pt-4 ${loading ? "opacity-60" : ""}`}>
            {error && <p role="alert" className="mb-3 rounded-lg bg-brand-soft px-4 py-3 font-medium text-brand-text">{error.message}</p>}
            {tab === "jobs" && (
              <JobsTab data={data.jobs} loading={loading || isSample}
                onSort={(s) => request && load({ ...request, job_sort: s }, true)}
                onCompare={(j) => { setJob(j); setTab("housing"); }} />
            )}
            {tab === "housing" && <HousingTab data={data.housing_areas} job={job} />}
            {tab === "services" && (
              <ServicesTab data={data.services} loading={loading || isSample}
                onSort={(s) => request && load({ ...request, service_sort: s }, true)} />
            )}
          </div>

          {data.next_steps.length > 0 && (
            <section className="mt-8 rounded-xl border border-line bg-card p-4 sm:p-5" aria-labelledby="next">
              <h2 id="next" className="text-lg font-semibold">Next steps</h2>
              <ul className="mt-2 space-y-2">
                {data.next_steps.map((s) => (
                  <li key={s.id} className="flex items-start gap-3">
                    <input type="checkbox" id={`step-${s.id}`} className="mt-0.5 h-5 w-5 shrink-0 accent-brand"
                      checked={done.includes(s.id)}
                      onChange={(e) => setDone(e.target.checked ? [...done, s.id] : done.filter((d) => d !== s.id))} />
                    <label htmlFor={`step-${s.id}`} className={done.includes(s.id) ? "text-muted line-through" : ""}>
                      {s.text}{" "}
                      <button type="button" onClick={() => { setTab(s.tab); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                        className="text-sm font-medium text-brand-text underline">
                        Go to {TABS.find((t) => t.key === s.tab)?.label}
                      </button>
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <footer className="mt-8 space-y-2 text-sm text-muted">
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

"use client";

import { useEffect, useRef, useState } from "react";
import OnboardingForm from "./OnboardingForm";
import PlanPreview from "./PlanPreview";
import PhoenixThinking from "./PhoenixThinking";
import { Button } from "./ui/button";
import type { ReentryProfile, UserEvent } from "@/lib/domain";
import type { RecommendationRequest, RecommendationResponse } from "@/lib/types";

const ignoreDraft = () => {};
export default function SituationUpdate({ request, onPreview, onConfirm, onCancel }: {
  request: RecommendationRequest;
  onPreview: (profile: ReentryProfile, event?: UserEvent) => Promise<RecommendationResponse>;
  onConfirm: (response: RecommendationResponse) => void;
  onCancel: () => void;
}) {
  const [preview, setPreview] = useState<RecommendationResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const previewRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const operation = useRef(0);
  useEffect(() => {
    titleRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
    return () => { ++operation.current; };
  }, []);
  useEffect(() => {
    if (preview) {
      previewRef.current?.focus({ preventScroll: true });
      previewRef.current?.scrollIntoView({ block: "start" });
    }
  }, [preview]);
  async function recalculate(profile: ReentryProfile) {
    const version = ++operation.current;
    setPending(true); setError("");
    try {
      const response = await onPreview(profile);
      if (version !== operation.current) return;
      if (!response.phoenix_session) throw new Error("Your preview could not be prepared. Your saved plan is unchanged.");
      setPreview(response);
    } catch (failure) {
      if (version === operation.current) setError((failure as Error).message);
    } finally {
      if (version === operation.current) setPending(false);
    }
  }
  return <section className="mx-auto max-w-5xl space-y-5" aria-labelledby="situation-title">
    <div role="group" className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 border-b bg-background py-3" aria-label="Situation actions">
      <Button type="button" variant="outline" onClick={onCancel}>← Back to my plan</Button>
      {preview?.phoenix_session && <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={() => onConfirm(preview)}>Confirm changes</Button>
        <Button type="button" variant="outline" onClick={() => {
          setPreview(null);
          requestAnimationFrame(() => {
            formRef.current?.querySelector<HTMLElement>("input, select, textarea, button")?.focus();
            formRef.current?.scrollIntoView({ block: "start" });
          });
        }}>Edit information</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>}
      {!preview && <Button type="submit" form="current-situation-form" disabled={pending}>Review changes</Button>}
      {pending && <PhoenixThinking />}
    </div>
    <div><h1 ref={titleRef} tabIndex={-1} id="situation-title" className="text-2xl font-bold outline-none">My current situation</h1></div>
    {error && <p role="alert" className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
    {preview?.phoenix_session && <div ref={previewRef} tabIndex={-1} role="region" aria-label="Plan changes preview" className="scroll-mt-28 outline-none"><PlanPreview before={request.phoenix_session!} after={preview.phoenix_session} /></div>}
    <div ref={formRef} hidden={!!preview} aria-busy={pending} className="scroll-mt-24">
      <OnboardingForm mode="edit" initial={request} draft={null} loading={pending} onDraftChange={ignoreDraft} submitLabel="Review changes" onSubmit={next => { if (next.profile) void recalculate(next.profile); }} />
    </div>
  </section>;
}

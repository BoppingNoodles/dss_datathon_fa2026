"use client";

import { useEffect, useRef, useState } from "react";
import { MessageCircle } from "lucide-react";
import { extractSituation, type PhoenixSession, type ReentryProfile } from "@/lib/domain";
import { circumstanceChanges, comparePlans, rebaseSituation } from "@/lib/plan-view";
import type { RecommendationRequest, RecommendationResponse } from "@/lib/types";
import { Button } from "./ui/button";
import PhoenixThinking from "./PhoenixThinking";

type Message = { role: "user" | "assistant"; text: string };
export default function SituationChat({ request, disabled, onPreview, onConfirm, onEdit }: {
  request: RecommendationRequest; disabled: boolean;
  onPreview: (profile: ReentryProfile) => Promise<RecommendationResponse>;
  onConfirm: (response: RecommendationResponse) => void; onEdit: () => void;
}) {
  const session = request.phoenix_session!;
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([{ role: "assistant", text: "Tell me what changed with housing, work, food or transportation." }]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<RecommendationResponse | null>(null);
  const [base, setBase] = useState<PhoenixSession | null>(null);
  const [dateDraft, setDateDraft] = useState<ReentryProfile | null>(null);
  const [date, setDate] = useState("");
  const [unknownDate, setUnknownDate] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const operation = useRef(0);
  useEffect(() => () => { ++operation.current; }, []);
  useEffect(() => { if (open) inputRef.current?.focus({ preventScroll: true }); }, [open]);
  useEffect(() => { if (messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight; }, [messages, pending, preview]);
  const reply = (text: string) => setMessages(values => [...values, { role: "assistant", text }]);
  function close() { setOpen(false); requestAnimationFrame(() => triggerRef.current?.focus({ preventScroll: true })); }
  async function prepare(profile: ReentryProfile) {
    const version = ++operation.current;
    setPending(true); setError(""); setPreview(null); setBase(session);
    try {
      const response = await onPreview(profile);
      if (version !== operation.current) return;
      if (!response.phoenix_session) throw new Error("A plan preview could not be prepared.");
      setPreview(response); setDateDraft(null);
      reply("Review your update before applying.");
    } catch (failure) { if (version === operation.current) setError((failure as Error).message); }
    finally { if (version === operation.current) setPending(false); }
  }
  function send(event: React.FormEvent) {
    event.preventDefault();
    if (!input.trim() || pending || disabled) return;
    const text = input.trim();
    setMessages(values => [...values, { role: "user", text }]); setInput(""); setPreview(null); setError("");
    const result = extractSituation(text, session.profile);
    if (!result.understood.length) { reply("I couldn’t identify a clear update. Try “I got a job” or “I now have food and transportation.” You can also edit your information directly."); return; }
    if (result.requiresDateConfirmation) {
      setDateDraft(result.profile); setDate(""); setUnknownDate(false);
      reply("What date does your temporary housing end? Please enter the date, or choose that it’s unknown.");
    } else void prepare(result.profile);
  }
  const after = preview?.phoenix_session;
  const fields = after && base ? circumstanceChanges(base.profile, after.profile) : [];
  const changes = after && base ? comparePlans(base, after) : null;
  const stale = !!preview && base !== session;
  return <>
    {!open && <Button ref={triggerRef} type="button" aria-expanded={false} aria-controls="situation-chat" className="fixed right-4 bottom-4 z-30 gap-2 rounded-full px-4 shadow-lg" onClick={() => setOpen(true)}><MessageCircle aria-hidden="true" className="size-5" strokeWidth={2} />Chat about changes</Button>}
    {open && <aside id="situation-chat" aria-label="Chat about changes" onKeyDown={event => { if (event.key === "Escape") close(); }} className="fixed top-4 right-4 bottom-4 z-40 flex w-[25rem] max-w-[calc(100vw-2rem)] flex-col rounded-xl border bg-card shadow-xl">
      <header className="flex items-center justify-between gap-3 border-b p-4"><h2 className="flex items-center gap-2 font-semibold"><MessageCircle aria-hidden="true" className="size-5 text-brand-text" />Chat about changes</h2><Button type="button" variant="ghost" aria-label="Close change chat" onClick={close}>×</Button></header>
      <div ref={messagesRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        <ol aria-label="Change conversation" className="space-y-3">{messages.map((message, i) => <li key={i} className={`rounded-lg p-3 text-sm leading-relaxed ${message.role === "user" ? "ml-6 bg-primary/10" : "mr-3 bg-muted/50"}`}><span className="sr-only">{message.role === "user" ? "You: " : "Phoenix: "}</span>{message.text}</li>)}</ol>
        {pending && <PhoenixThinking />}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {dateDraft && <div className="space-y-3 rounded-lg border p-3"><label className="block text-sm">Housing end date<input type="date" aria-label="Housing end date for chat" value={date} disabled={unknownDate || pending} onChange={event => setDate(event.target.value)} className="mt-2 w-full rounded-md border bg-card p-2" /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={unknownDate} onChange={event => { setUnknownDate(event.target.checked); setDate(""); }} />I don’t know the date yet</label><Button type="button" disabled={pending || (!date && !unknownDate)} onClick={() => { const next = structuredClone(dateDraft); next.housing.temporaryHousingEndDate = date || null; void prepare(next); }}>Review plan changes</Button></div>}
        {after && changes && <div className="space-y-3 rounded-lg border p-3"><h3 className="text-sm font-semibold">Your situation</h3><ul className="space-y-2 text-sm">{fields.map(field => <li key={field.label}><p className="font-medium">{field.label}</p><p className="text-xs text-muted-foreground">{field.before} → {field.after}</p></li>)}</ul>{!fields.length && <p className="text-sm text-muted-foreground">Your reported information is already up to date.</p>}
          <details className="text-xs"><summary className="cursor-pointer text-brand-text">How the plan changes</summary><div className="mt-2 space-y-3"><p>{changes.retained.length} completed steps preserved.</p><div><p className="font-semibold">Before</p><ul>{changes.previousPriorities.map(task => <li key={task.id}>{task.title}</li>)}</ul></div><div><p className="font-semibold">After</p><ul>{changes.proposedPriorities.map(task => <li key={task.id}>{task.title}</li>)}</ul></div><ul>{changes.added.map(task => <li key={task.id}>Added: {task.title}</li>)}{changes.archived.map(task => <li key={task.id}>Archived: {task.title}</li>)}{changes.newResources.map(resource => <li key={resource.id}>New option: {resource.title}</li>)}{changes.unavailableResources.map(resource => <li key={resource.id}>Earlier option: {resource.title}</li>)}</ul></div></details>
          {stale && <p role="status" className="text-xs text-warn">Your plan changed while this preview was open. Review it again before applying.</p>}
          <div className="flex flex-wrap gap-2"><Button type="button" disabled={disabled || stale} onClick={() => { onConfirm(preview!); setPreview(null); reply("Saved. Your current situation and plan are updated."); inputRef.current?.focus({ preventScroll: true }); }}>Apply changes</Button>{stale && <Button type="button" variant="outline" onClick={() => { void prepare(rebaseSituation(base!.profile, after.profile, session.profile)); }}>Refresh preview</Button>}<Button type="button" variant="ghost" onClick={() => setPreview(null)}>Discard</Button></div>
        </div>}
      </div>
      <form onSubmit={send} className="space-y-2 border-t p-3"><label htmlFor="change-message" className="sr-only">Describe your changes</label><textarea ref={inputRef} id="change-message" rows={2} maxLength={1000} value={input} disabled={pending || disabled} onChange={event => setInput(event.target.value)} placeholder="What changed?" className="w-full resize-none rounded-lg border bg-background p-3 text-sm focus-visible:outline-2 focus-visible:outline-ring" /><div className="flex items-center justify-between gap-2"><Button type="button" variant="link" size="sm" onClick={onEdit}>Edit situation</Button><Button type="submit" disabled={pending || disabled || !input.trim()}>Send</Button></div></form>
    </aside>}
  </>;
}

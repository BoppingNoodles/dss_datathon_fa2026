"use client";

export function Badge({ tone, children }: { tone: "ok" | "warn" | "neutral" | "brand"; children: React.ReactNode }) {
  const cls = {
    ok: "bg-ok-soft text-ok",
    warn: "bg-warn-soft text-warn",
    neutral: "bg-paper text-muted border border-line",
    brand: "bg-brand-soft text-brand-text",
  }[tone];
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{children}</span>;
}

export function Notes({ notes }: { notes: string[] }) {
  if (!notes.length) return null;
  return (
    <ul className="space-y-1 rounded-lg bg-warn-soft px-4 py-3 text-sm text-warn">
      {notes.map((n, i) => <li key={i}>{n}</li>)}
    </ul>
  );
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-card px-5 py-8 text-center">
      <p className="text-lg font-semibold">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-md text-sm text-muted">{children}</p>}
    </div>
  );
}

export function SortToggle<T extends string>({ label, value, options, onChange, disabled }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; disabled?: boolean;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-line bg-card p-0.5 text-sm">
      {options.map((o) => (
        <button
          key={o.value} type="button" disabled={disabled} aria-pressed={value === o.value}
          onClick={() => value !== o.value && onChange(o.value)}
          className={`rounded-md px-3 py-1.5 font-medium ${value === o.value ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

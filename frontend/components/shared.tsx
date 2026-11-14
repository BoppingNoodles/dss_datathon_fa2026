"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge as UiBadge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

const TONES = {
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  neutral: "border-border bg-muted text-muted-foreground",
  brand: "bg-accent text-accent-foreground",
} as const;

/** Status badge in a Phoenix tone, built on the shadcn Badge. */
export function Badge({ tone, children }: { tone: keyof typeof TONES; children: React.ReactNode }) {
  return <UiBadge variant="outline" className={`h-auto border-transparent py-0.5 font-semibold ${TONES[tone]}`}>{children}</UiBadge>;
}

/** Caveats from the API ("threshold was not lowered", "N closed places removed"). */
export function Notes({ notes }: { notes: string[] }) {
  if (!notes.length) return null;
  return (
    <Alert role="note" className="border-transparent bg-warn-soft px-4 py-3 text-warn">
      <AlertDescription className="text-warn">
        <ul className="space-y-1">
          {notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <Card className="border border-dashed border-border py-8 text-center ring-0">
      <CardContent>
        <p className="text-lg font-semibold">{title}</p>
        {children && <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{children}</p>}
      </CardContent>
    </Card>
  );
}

export function SortToggle<T extends string>({ label, value, options, onChange, disabled }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; disabled?: boolean;
}) {
  return (
    <ToggleGroup
      type="single" variant="outline" spacing={0} aria-label={label} disabled={disabled} value={value}
      onValueChange={(v) => v && v !== value && onChange(v as T)}
    >
      {options.map((o) => (
        <ToggleGroupItem
          key={o.value} value={o.value}
          className="h-9 bg-card px-3 data-[state=on]:bg-foreground data-[state=on]:text-background"
        >
          {o.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

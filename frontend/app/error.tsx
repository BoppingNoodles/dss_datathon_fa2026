"use client";

import { Button } from "@/components/ui/button";

export default function Error({ retry }: { error: unknown; retry: () => void }) {
  return <main className="mx-auto max-w-lg space-y-4 px-6 py-16">
    <p className="phoenix-wordmark text-3xl font-bold">Phoenix</p>
    <h1 className="text-xl font-semibold">Something went wrong</h1>
    <p className="text-sm text-muted-foreground">Try opening your plan again.</p>
    <Button type="button" onClick={retry}>Try again</Button>
  </main>;
}

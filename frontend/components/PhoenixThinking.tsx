import { cn } from "@/lib/utils";

export default function PhoenixThinking({ className }: { className?: string }) {
  return <span role="status" aria-label="Phoenix is thinking" className={cn("inline-flex items-center gap-2 text-sm text-brand-text", className)}>
    <span aria-hidden="true" className="size-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none" />
    <span aria-hidden="true" className="phoenix-wordmark">Phoenix is thinking</span>
  </span>;
}

import { money } from "./api";
import type { Pay } from "./types";

export function payText(p: Pay): string {
  if (p.needs_confirmation) return "Pay needs confirmation";
  if (p.raw_text) return p.raw_text.replace(/\bpor\s+hora\b/gi, "per hour");
  if (p.currency && p.currency !== "USD") return p.raw_text || `Pay in ${p.currency}; confirm amount`;
  if (!p.period || (p.min == null && p.max == null)) return p.raw_text || "Pay not listed";
  const digits = [p.min, p.max].some((n) => n != null && !Number.isInteger(n)) ? 2 : 0;
  const lo = money(p.min ?? p.max, digits);
  const hi = money(p.max ?? p.min, digits);
  const amount = p.min == null ? `Up to ${hi}` : p.max == null ? `From ${lo}` : lo === hi ? lo : `${lo}–${hi}`;
  return `${amount} / ${{hour:"hr",day:"day",week:"wk",month:"mo",year:"yr"}[p.period]}`;
}

import { money } from "./api";
import type { InterimJob, Pay } from "./types";

export function payText(p: Pay): string {
  if (p.raw_text) return p.raw_text;
  if (p.min == null && p.max == null) return "Pay not listed";
  const digits = p.period === "hour" ? 2 : 0;
  const lo = money(p.min ?? p.max, digits);
  const hi = money(p.max ?? p.min, digits);
  return `${lo === hi ? lo : `${lo}–${hi}`}${p.period ? ` per ${p.period}` : " (pay period not stated)"}`;
}

export function interimPay(job: InterimJob): Pay {
  return {
    min: job.pay.minimum,
    max: job.pay.maximum,
    period: job.pay.period === "unknown" ? null : job.pay.period,
    raw_text: job.pay.raw,
    hours_per_week: null,
    hours_basis: "unknown",
    conversion_note: job.pay.notes.join(" ") || null,
  };
}

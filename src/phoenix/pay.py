"""Advertised pay parsing, comparable-rate groups, and explicit income scenarios."""

from __future__ import annotations

import re

from .models import Job, Pay

_AMOUNT = re.compile(r"(?<![\w.])\$?\s*(\d[\d,]*(?:\.\d+)?)\s*([kK])?(?!\w)")
_PERIODS = {
    "hour": r"\b(?:an? hour|per hour|hourly|/\s*hr|/\s*hour|por hora)\b",
    "day": r"\b(?:an? day|per day|daily|por día|por dia)\b",
    "week": r"\b(?:an? week|per week|weekly|por semana)\b",
    "month": r"\b(?:an? month|per month|monthly|por mes)\b",
    "year": r"\b(?:an? year|per year|yearly|annually|annual|per annum|por año)\b",
}


def parse_pay(raw: str | None, *, currency: str = "USD") -> Pay:
    if not raw or not raw.strip():
        return Pay()
    text = raw.strip()
    normalized = text.casefold().replace("–", "-").replace("—", "-")
    notes: list[str] = []
    if re.search(r"[£€]|\b(?:cad|aud|gbp|eur)\b|c\$|a\$", normalized):
        return Pay(source="ambiguous", raw=text, notes=["Unsupported or ambiguous currency; no conversion applied."])
    periods = [p for p, pattern in _PERIODS.items() if re.search(pattern, normalized)]
    # Also accept conventional '$25/hr' strings, without relying on word boundaries at '/'.
    if re.search(r"/\s*(?:hr|hour)\b", normalized) and "hour" not in periods:
        periods.append("hour")
    if len(periods) != 1 or re.search(r"\b(?:estimated|estimate)\b", normalized):
        return Pay(source="ambiguous", raw=text, notes=["Pay period is unclear/mixed or amount is an estimate."])
    amounts = _AMOUNT.findall(normalized)
    if any("," in n and not re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", n) for n, _ in amounts):
        return Pay(source="ambiguous", raw=text, notes=["Ambiguous numeric separators need confirmation."])
    values = [float(n.replace(",", "")) * (1000 if k else 1) for n, k in amounts]
    if not values or len(values) > 2 or any(v <= 0 for v in values):
        return Pay(source="ambiguous", raw=text, notes=["Could not identify a valid advertised base-pay amount/range."])
    low, high = values[0], values[-1]
    if low > high:
        return Pay(source="ambiguous", raw=text, notes=["Reversed pay range needs confirmation."])
    if len(values) == 1:
        if re.search(r"\b(?:up to|maximum)\b", normalized):
            low = None
            notes.append("Only an upper bound is advertised; cannot rank by a lower pay guarantee.")
        elif re.search(r"\b(?:from|starting at|at least|minimum)\b", normalized) or "+" in normalized:
            high = None
            notes.append("Only a lower bound is advertised.")
    if any(w in normalized for w in ("bonus", "commission", "tips", "ote")):
        return Pay(source="ambiguous", raw=text, notes=["Variable/total compensation requires base-pay verification."])
    return Pay(minimum=low, maximum=high, period=periods[0], currency=currency,
               source="advertised", raw=text, notes=notes)


def comparable_pay(job: Job) -> tuple[str, float | None, list[str]]:
    """Only comparable within returned basis. Never impute missing pay or work hours."""
    pay = job.pay
    if pay.source != "advertised" or pay.minimum is None or pay.currency != "USD" or pay.period == "unknown":
        return "pay_needs_confirmation", None, list(pay.notes)
    if pay.period == "year" and job.hours_per_week and job.weeks_per_year:
        rate = pay.minimum / (job.hours_per_week * job.weeks_per_year)
        return "USD/hour", rate, [f"Converted using stated {job.hours_per_week:g} hours/week and {job.weeks_per_year:g} weeks/year."]
    return f"USD/{pay.period}", pay.minimum, []


def annual_income(job: Job, *, scenario_hours_per_week: float | None = None,
                  scenario_weeks_per_year: float | None = None) -> dict:
    pay = job.pay
    assumptions: list[str] = []
    if pay.source != "advertised" or pay.currency != "USD" or pay.period == "unknown":
        return {"minimum": None, "maximum": None, "assumptions": [], "basis": "unknown"}
    if pay.period == "year":
        multiplier = 1
    elif pay.period == "hour":
        hours = job.hours_per_week or scenario_hours_per_week
        weeks = job.weeks_per_year or scenario_weeks_per_year
        if hours is None or weeks is None:
            return {"minimum": None, "maximum": None, "assumptions": [], "basis": "hours_not_provided"}
        if not 0 < hours <= 168 or not 0 < weeks <= 53:
            raise ValueError("Income scenario hours/weeks are out of range")
        multiplier = hours * weeks
        assumptions.append(f"{hours:g} hours/week × {weeks:g} weeks/year; "
                           + ("stated schedule." if job.hours_per_week and job.weeks_per_year else "hypothetical schedule, not guaranteed earnings."))
    else:
        return {"minimum": None, "maximum": None, "assumptions": [], "basis": "annual_schedule_unverified"}
    return {"minimum": None if pay.minimum is None else pay.minimum * multiplier,
            "maximum": None if pay.maximum is None else pay.maximum * multiplier,
            "assumptions": assumptions, "basis": "selected_job_gross_income_scenario"}


def rent_burden(monthly_rent: float | None, annual_gross_pay: float | None) -> float | None:
    if monthly_rent is None or annual_gross_pay is None or monthly_rent <= 0 or annual_gross_pay <= 0:
        return None
    import math
    return 12 * monthly_rent / annual_gross_pay if math.isfinite(monthly_rent) and math.isfinite(annual_gross_pay) else None

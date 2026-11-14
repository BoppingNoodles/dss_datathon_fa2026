"""Hypothetical rent-burden scenario for a selected job (Phoenix.md section 9).

    rent_burden = 12 * monthly_rent / annual_gross_pay       e.g. 12 * 1200 / 48000 = 0.30

A pay range produces a burden interval. Missing or invalid inputs produce Unknown, never 0.
This is a scenario based on advertised pay, not the person's income, and excludes taxes,
deposits, utilities, household needs, and variable hours. It does not establish affordability
or rental eligibility.
"""

from __future__ import annotations

WEEKS_PER_YEAR = 52
DEFAULT_HOURS = 40.0
DAYS_PER_WEEK_ASSUMED = 5

CAVEAT = ("Scenario only: uses advertised gross pay, not your income. Excludes taxes, deposits, utilities, "
          "and other costs, and does not mean a landlord would approve an application.")


def annualize(amount: float | None, period: str | None, hours_per_week: float | None) -> tuple[float | None, list[str]]:
    notes: list[str] = []
    if amount is None or amount <= 0 or period is None:
        return None, notes
    if period == "year":
        return amount, notes
    if period == "month":
        return amount * 12, notes
    if period == "week":
        return amount * WEEKS_PER_YEAR, notes
    hours = hours_per_week
    if hours is None:
        hours = DEFAULT_HOURS
        notes.append(f"Assumed {DEFAULT_HOURS:g} hours/week x {WEEKS_PER_YEAR} weeks/year (not stated in the posting).")
    else:
        notes.append(f"Used stated {hours:g} hours/week x {WEEKS_PER_YEAR} weeks/year.")
    if period == "hour":
        return amount * hours * WEEKS_PER_YEAR, notes
    if period == "day":
        notes.append(f"Assumed {DAYS_PER_WEEK_ASSUMED} working days/week for daily pay.")
        return amount * DAYS_PER_WEEK_ASSUMED * WEEKS_PER_YEAR, notes
    return None, notes


def rent_burden(monthly_rent: float | None, annual_pay: float | None) -> float | None:
    if monthly_rent is None or annual_pay is None or monthly_rent <= 0 or annual_pay <= 0:
        return None
    return 12 * monthly_rent / annual_pay


def compare(pay_min: float | None, pay_max: float | None, period: str | None,
            hours_per_week: float | None, monthly_rent: float | None) -> dict:
    lo_amt = pay_min if pay_min is not None else pay_max
    hi_amt = pay_max if pay_max is not None else pay_min
    if lo_amt is not None and hi_amt is not None and lo_amt > hi_amt:
        lo_amt, hi_amt = hi_amt, lo_amt
    annual_lo, notes = annualize(lo_amt, period, hours_per_week)
    annual_hi, _ = annualize(hi_amt, period, hours_per_week)
    b_max = rent_burden(monthly_rent, annual_lo)
    b_min = rent_burden(monthly_rent, annual_hi)
    if pay_min is not None and pay_max is None or pay_max is not None and pay_min is None:
        notes.append("Only one end of the pay range was listed; the burden is a single value.")
    unknown = b_min is None or b_max is None
    if unknown:
        notes.append("Pay or rent is missing or not comparable, so the burden is unknown.")
    return {
        "annual_gross_min": None if annual_lo is None else round(annual_lo, 2),
        "annual_gross_max": None if annual_hi is None else round(annual_hi, 2),
        "monthly_rent": monthly_rent,
        "rent_burden_min": None if b_min is None else round(b_min, 4),
        "rent_burden_max": None if b_max is None else round(b_max, 4),
        "status": "unknown" if unknown else "ok",
        "assumptions": notes,
        "caveat": CAVEAT,
    }

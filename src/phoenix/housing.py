"""Publishable rental aggregates and selected-job gross-income scenarios."""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from .models import HousingArea, Job, Rental
from .normalization import city_key
from .pay import annual_income, rent_burden


def summarize_housing(rentals: list[Rental], *, cities: set[str] | None = None,
                      minimum_count: int = 5) -> tuple[list[HousingArea], dict]:
    if minimum_count < 5:
        raise ValueError("Public housing summaries require at least five distinct properties")
    groups: dict[tuple, dict[str, Rental]] = defaultdict(dict)
    for rental in rentals:
        if cities and city_key(rental.city) not in cities:
            continue
        groups[(rental.city, None)][rental.property_id] = rental
        if rental.zipcode:
            groups[(rental.city, rental.zipcode)][rental.property_id] = rental
    areas = []
    suppressed = 0
    for (city, zipcode), records in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1] or "")):
        if len(records) < minimum_count:
            suppressed += 1
            continue
        values = list(records.values())
        amounts = [r.monthly_rent for r in values]
        bases = sorted({r.rent_basis for r in values})
        areas.append(HousingArea(area_id=f"{city_key(city)}:{zipcode or 'city'}", city=city, zipcode=zipcode,
            geography="zipcode" if zipcode else "city", listing_count=len(values),
            median_monthly_rent=median(amounts), minimum_monthly_rent=min(amounts), maximum_monthly_rent=max(amounts),
            rent_basis=", ".join(bases), notes=["Rental snapshot, not confirmed current availability.",
                "City and ZIP summaries overlap; do not add their listing counts."] +
                (["Monthly-rent units require source confirmation."] if "listed_price_unverified" in bases else [])))
    return areas, {"suppressed_small_groups": suppressed, "minimum_distinct_properties": minimum_count,
                   "public_areas": len(areas), "status": "available" if areas else "insufficient_rental_data"}


def compare_job_housing(job: Job, area: HousingArea, *, scenario_hours_per_week: float | None = None,
                        scenario_weeks_per_year: float | None = None) -> dict:
    income = annual_income(job, scenario_hours_per_week=scenario_hours_per_week,
                           scenario_weeks_per_year=scenario_weeks_per_year)
    lower = rent_burden(area.median_monthly_rent, income["maximum"])
    upper = rent_burden(area.median_monthly_rent, income["minimum"])
    return {"job_id": job.job_id, "area_id": area.area_id, "monthly_rent_basis": "area_median",
            "monthly_rent": area.median_monthly_rent, "annual_gross_pay_scenario": income,
            "rent_burden_minimum": lower, "rent_burden_maximum": upper,
            "status": "scenario_available" if upper is not None else "income_needs_confirmation",
            "notes": ["Gross-income scenario for the selected job, not the user's current income or rental eligibility.",
                      "Excludes taxes, deposits, utilities, transport, and household expenses."]}

"""Transparent planning checks using reported monthly take-home income/costs."""

FIELDS = ("monthlyTakeHomePay", "monthlyHousingCost", "monthlyFoodCost", "monthlyOtherCosts")
HOUSING_TARGET = 0.30
SPENDING_TARGET = 0.80
BUDGET_SOURCE = "https://files.consumerfinance.gov/f/documents/cfpb_well-being_monthly-budget.pdf"


def assess_finances(finances):
    values = {key: getattr(finances, key, None) for key in FIELDS}
    missing = [key for key in FIELDS if values[key] is None]
    cents = {key: int(round(value * 100)) if value is not None else None for key, value in values.items()}
    income, housing = cents["monthlyTakeHomePay"], cents["monthlyHousingCost"]
    housing_high = income is not None and housing is not None and housing > 0 and (income == 0 or housing * 100 > income * 30)
    total = None if missing else sum(cents[key] for key in FIELDS[1:])
    remaining = None if total is None else income - total
    spending_high = total is not None and total * 100 >= income * 80
    status = "incomplete" if missing else "deficit" if remaining < 0 else "tight" if spending_high else "high_housing" if housing_high else "within_budget"
    return {"status": status, "missing": missing, "housingHigh": housing_high, "spendingHigh": spending_high,
            "totalCosts": None if total is None else total / 100, "remaining": None if remaining is None else remaining / 100,
            "housingShare": housing / income if income and housing is not None else None}

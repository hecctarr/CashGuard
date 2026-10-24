"""
Spending categories and staff limits.

Each category has:
  max_per_request  - the most one staff member can ask for in a single request (RM)
  monthly_limit    - the most one staff member can request in that category per month (RM)
The Owner can change these in Settings. Requests above a limit are blocked.
"""

import pandas as pd

DEFAULT_CATEGORIES = {
    "Staff allowance":      {"max_per_request": 200,  "monthly_limit": 400},
    "Transport & travel":   {"max_per_request": 150,  "monthly_limit": 300},
    "Supplies & stock":     {"max_per_request": 1000, "monthly_limit": 3000},
    "Equipment":            {"max_per_request": 5000, "monthly_limit": 5000},
    "Repair & maintenance": {"max_per_request": 1500, "monthly_limit": 3000},
    "Marketing":            {"max_per_request": 800,  "monthly_limit": 1500},
    "Other":                {"max_per_request": 300,  "monthly_limit": 600},
}
COUNTED = ("Pending", "Approved")   # rejected requests do not use up the limit


def categories(settings: dict) -> dict:
    return settings.get("categories") or DEFAULT_CATEGORIES


def used_this_month(requests: pd.DataFrame, staff: str, category: str, today: pd.Timestamp) -> float:
    if requests.empty or "category" not in requests:
        return 0.0
    dates = pd.to_datetime(requests["request_date"], errors="coerce")
    m = ((requests["submitted_by"] == staff) & (requests["category"] == category)
         & requests["status"].isin(COUNTED)
         & (dates.dt.year == today.year) & (dates.dt.month == today.month))
    return float(requests.loc[m, "amount"].sum())


def check(amount: float, category: str, staff: str, requests: pd.DataFrame,
          settings: dict, today: pd.Timestamp) -> dict:
    """Return the limit status for a request. ok=False means it must be blocked."""
    lim = categories(settings)[category]
    used = used_this_month(requests, staff, category, today)
    left = max(0.0, lim["monthly_limit"] - used)
    problems = []
    if amount > lim["max_per_request"]:
        problems.append(f"Above the RM{lim['max_per_request']:,.0f} limit per request for {category}.")
    if amount > left:
        problems.append(f"Above your monthly {category} limit: RM{used:,.0f} of "
                        f"RM{lim['monthly_limit']:,.0f} already used, RM{left:,.0f} left.")
    return {"ok": not problems, "problems": problems, "max_per_request": lim["max_per_request"],
            "monthly_limit": lim["monthly_limit"], "used": used, "left": left}

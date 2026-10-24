"""
B. Rule check (deterministic timeline - always works, our fallback)
C. Monte Carlo simulation (1,000 possible futures -> probability of ruin)

Day 0 = today (the demo date in settings). Horizon = 30 days by default.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.payments import conditional_median, sample_delays

ACTIVE_BILL_STATUSES = ("To pay", "Scheduled", "On hold", "Awaiting review")


@dataclass
class Receivable:
    invoice_no: str
    customer: str
    amount: float
    due_day: int          # days from today (negative = already overdue)
    overdue: int          # days overdue so far (0 if not yet due)


@dataclass
class CashState:
    today: pd.Timestamp
    cash_today: float
    reserve: float
    horizon: int
    fixed_out: np.ndarray                  # bills per day (RM)
    bill_labels: dict                      # day -> list of bill names
    receivables: list
    daily_sales: np.ndarray                # all days (kept for reference)
    model: dict
    weekday_sales: np.ndarray = None       # Mon-Fri history
    weekend_sales: np.ndarray = None       # Sat-Sun history
    sales_mean: float = field(init=False)
    is_weekend: np.ndarray = field(init=False)

    def __post_init__(self):
        if self.weekday_sales is None or len(self.weekday_sales) == 0:
            self.weekday_sales = self.daily_sales
        if self.weekend_sales is None or len(self.weekend_sales) == 0:
            self.weekend_sales = self.daily_sales
        self.is_weekend = np.array([(self.today + pd.Timedelta(days=d)).dayofweek >= 5
                                    for d in range(self.horizon)])
        self.sales_mean = float(np.mean(self.daily_sales))

    def expected_sales(self) -> np.ndarray:
        return np.where(self.is_weekend, self.weekend_sales.mean(), self.weekday_sales.mean())

    def day_to_date(self, d: int) -> pd.Timestamp:
        return self.today + pd.Timedelta(days=int(d))

    def date_to_day(self, date) -> int:
        return int((pd.Timestamp(date) - self.today).days)


def build_state(settings, bills, invoices, daily_sales, model, exclude_bill=None) -> CashState:
    today = pd.Timestamp(settings["today"])
    horizon = int(settings.get("horizon_days", 30))
    fixed = np.zeros(horizon)
    labels = {}

    def add(day, amount, name):
        if 0 <= day < horizon:
            fixed[day] += amount
            labels.setdefault(day, []).append(name)

    for _, b in bills.iterrows():
        if b["status"] not in ACTIVE_BILL_STATUSES or b["bill_no"] == exclude_bill:
            continue
        when = b["pay_date"] if pd.notna(b.get("pay_date")) else b["due_date"]
        add(max(0, int((when - today).days)), float(b["amount"]), str(b["supplier"]))
    # Recurring bills: repeat monthly after the latest bill in each series
    if "repeat" in bills.columns:
        rec = bills[bills["repeat"].fillna("").str.lower() == "monthly"]
        for _, b in rec.sort_values("due_date").groupby(["supplier", "category"]).tail(1).iterrows():
            for k in (1, 2):
                nxt = b["due_date"] + pd.DateOffset(months=k)
                add(int((nxt - today).days), float(b["amount"]), f"{b['supplier']} (repeat)")
    recs = []
    for _, r in invoices[invoices["paid_date"].isna()].iterrows():
        due_day = int((r["due_date"] - today).days)
        recs.append(Receivable(r["invoice_no"], r["customer"], float(r["amount"]),
                               due_day, max(0, -due_day)))
    wkend = daily_sales["date"].dt.dayofweek >= 5
    return CashState(today, float(settings["cash_today"]), float(settings["min_reserve"]),
                     horizon, fixed, labels, recs,
                     daily_sales["net_cash"].to_numpy(dtype=float), model,
                     daily_sales.loc[~wkend, "net_cash"].to_numpy(dtype=float),
                     daily_sales.loc[wkend, "net_cash"].to_numpy(dtype=float))


def rule_check(state: CashState, outflows=(), sales_factor=1.0, extra_cost=0.0,
               extra_delay=None) -> dict:
    """Layer B: one 'typical' future using average sales and typical delays."""
    extra_delay = extra_delay or {}
    flows = -state.fixed_out + state.expected_sales() * sales_factor
    for d, amt in outflows:
        if d < state.horizon:
            flows[d] -= amt
    if extra_cost:
        flows[min(3, state.horizon - 1)] -= extra_cost
    for r in state.receivables:
        delay = conditional_median(state.model, r.customer, r.overdue) + extra_delay.get(r.customer, 0)
        arrive = max(1, int(round(r.due_day + delay)))
        if arrive < state.horizon:
            flows[arrive] += r.amount
    path = state.cash_today + np.cumsum(flows)
    low_day = int(np.argmin(path))
    return {"path": path, "lowest": float(path[low_day]), "lowest_day": low_day,
            "below_reserve": bool(path.min() < state.reserve)}


def simulate(state: CashState, outflows=(), runs=1000, seed=11, sales_factor=1.0,
             extra_cost=0.0, extra_delay=None, force_on_time=None, surprise=True) -> dict:
    """Layer C: Monte Carlo. Same seed for every option = fair comparison."""
    extra_delay = extra_delay or {}
    rng = np.random.default_rng(seed)
    H = state.horizon
    idx = np.arange(runs)

    flows = np.tile(-state.fixed_out, (runs, 1))
    wkday = rng.choice(state.weekday_sales, size=(runs, H))                 # random real sales days,
    wkend = rng.choice(state.weekend_sales, size=(runs, H))                 # weekends drawn from weekends
    flows += np.where(state.is_weekend, wkend, wkday) * sales_factor
    if surprise:                                                            # 10% chance of a surprise cost
        hit = rng.random(runs) < 0.10
        days = rng.integers(0, H, runs)
        amts = rng.uniform(300, 800, runs)
        flows[idx[hit], days[hit]] -= amts[hit]
    if extra_cost:
        flows[:, min(3, H - 1)] -= extra_cost
    for d, amt in outflows:                                                 # the decision being tested
        if d < H:
            flows[:, d] -= amt

    arrivals = {}
    for r in state.receivables:
        if r.invoice_no == force_on_time:
            arrive = np.full(runs, max(1, r.due_day))
        else:
            # credibility-blended delays; if already overdue, only delays at least that long
            d = sample_delays(state.model, r.customer, r.overdue, runs, rng)
            arrive = np.maximum(1, r.due_day + d + extra_delay.get(r.customer, 0))
        arrivals[r.invoice_no] = arrive
        ok = arrive < H
        flows[idx[ok], arrive[ok]] += r.amount

    cash = state.cash_today + np.cumsum(flows, axis=1)
    low = cash.min(axis=1)
    failed = low < state.reserve
    fail_day = np.where(failed, np.argmax(cash < state.reserve, axis=1), -1)

    causes = {}
    n_fail = int(failed.sum())
    for r in state.receivables:
        late = failed & (max(0, r.due_day) <= fail_day) & (arrivals[r.invoice_no] > fail_day)
        causes[r.invoice_no] = float(late.sum() / n_fail) if n_fail else 0.0

    return {
        "risk": float(failed.mean()),
        "worst5": float(np.percentile(low, 5)),
        "typical_low": float(np.median(low)),
        "p5": np.percentile(cash, 5, axis=0),
        "p50": np.percentile(cash, 50, axis=0),
        "p95": np.percentile(cash, 95, axis=0),
        "fail_day_mode": int(np.bincount(fail_day[failed]).argmax()) if n_fail else None,
        "causes": causes,
        "runs": runs,
    }

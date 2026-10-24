"""
Impact test: does CashGuard actually prevent cash shortfalls?

For N synthetic bill situations (different cash levels, bill sizes and due dates):
  - Policy 1 "pay straight away": pay the bill the day it arrives (what owners do today).
  - Policy 2 "CashGuard": pay on the date CashGuard suggests (never after the due date).
Each policy is then judged on "reality": 300 fresh futures drawn from the hidden customer
behaviour and sales pattern that generated the demo data - NOT from the model's own
assumptions - so the test is out-of-sample.
"""

import numpy as np
import pandas as pd

from engine.explain import evaluate_options
from engine.montecarlo import build_state
from make_data import CUSTOMERS


def _reality(state, pay_day, amount, rng, runs=300):
    """Lowest cash per future under the TRUE world (hidden customer means, true sales process)."""
    H = state.horizon
    idx = np.arange(runs)
    flows = np.tile(-state.fixed_out, (runs, 1))
    weekday = rng.normal(140, 120, (runs, H))
    weekend = rng.normal(260, 150, (runs, H))
    flows += np.where(state.is_weekend, weekend, weekday)
    hit = rng.random(runs) < 0.10
    flows[idx[hit], rng.integers(0, H, runs)[hit]] -= rng.uniform(300, 800, runs)[hit]
    flows[:, pay_day] -= amount
    for r in state.receivables:
        mean, spread, _ = CUSTOMERS.get(r.customer, (5, 5, 0))
        late = np.maximum(-3, np.round(rng.normal(mean, spread, runs)))
        if r.overdue > 0:                                   # it is already this late
            late = np.maximum(late, r.overdue + rng.integers(0, 7, runs))
        arrive = np.maximum(1, r.due_day + late).astype(int)
        ok = arrive < H
        flows[idx[ok], arrive[ok]] += r.amount
    cash = state.cash_today + np.cumsum(flows, axis=1)
    return cash.min(axis=1)


def run_impact(settings, bills, invoices, sales, model, n=50, seed=2026) -> dict:
    rng = np.random.default_rng(seed)
    quick = {**settings, "simulations": 500}
    rows = []
    for i in range(n):
        s = {**quick, "cash_today": float(rng.uniform(4500, 7500))}
        state = build_state(s, bills, invoices, sales, model)
        amount = float(round(rng.uniform(500, 2500), -1))
        due_day = int(rng.integers(3, 15))
        ev = evaluate_options(state, amount, "bill", s, due_day=due_day)
        sug = ev["suggested"]["day"]
        world = np.random.default_rng(seed + 1000 + i)
        low_now = _reality(state, 0, amount, world)
        world = np.random.default_rng(seed + 1000 + i)        # same reality for both policies
        low_cg = _reality(state, sug, amount, world)
        rows.append({
            "Situation": i + 1, "Cash today": s["cash_today"], "Bill": amount, "Due in (days)": due_day,
            "CashGuard pays on day": sug,
            "Breach rate - pay now": float(np.mean(low_now < s["min_reserve"])),
            "Breach rate - CashGuard": float(np.mean(low_cg < s["min_reserve"])),
            "Predicted risk - pay now": ev["today"]["risk"],
        })
    df = pd.DataFrame(rows)
    now, cg = df["Breach rate - pay now"].mean(), df["Breach rate - CashGuard"].mean()
    risky = df[df["Breach rate - pay now"] >= 0.05]
    return {
        "n": n,
        "breach_now": float(now), "breach_cg": float(cg),
        "reduction": float(1 - cg / now) if now > 0 else 0.0,
        "risky_situations": int(len(risky)),
        "risky_fixed": int((risky["Breach rate - CashGuard"] < 0.05).sum()),
        "paid_on_time": int((df["CashGuard pays on day"] <= df["Due in (days)"]).sum()),
        "delayed": int((df["CashGuard pays on day"] > 0).sum()),
        "table": df,
    }

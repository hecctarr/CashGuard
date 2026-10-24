"""
D. Best date to pay / spend
E. Plain-language explanation
F. Chase suggestion (what if the main late customer paid on time?)
"""

import pandas as pd

from engine.montecarlo import CashState, rule_check, simulate


def risk_level(risk: float, settings: dict):
    if risk < settings["low_risk_limit"]:
        return "Low", "green", "Within safe range"
    if risk <= settings["high_risk_limit"]:
        return "Medium", "orange", "Review recommended"
    return "High", "red", "High risk: consider a safer option"


def money(x: float) -> str:
    return f"-RM{abs(x):,.0f}" if x < 0 else f"RM{x:,.0f}"


def candidate_days(kind: str, due_day=None, horizon=30):
    if kind == "bill":
        last = max(0, due_day if due_day is not None else 0)
        days = sorted({d for d in (0, 3, 7, last) if 0 <= d <= last})
    else:  # expense
        days = [0, 7, 14, 21]
    return [d for d in days if d < horizon]


def evaluate_options(state: CashState, amount: float, kind: str, settings: dict,
                     due_day=None, **what_if) -> dict:
    """Run Monte Carlo for each candidate date; pick the suggested one."""
    runs = int(settings.get("simulations", 1000))
    options = []
    for d in candidate_days(kind, due_day, state.horizon):
        res = simulate(state, outflows=[(d, amount)], runs=runs, **what_if)
        level, colour, label = risk_level(res["risk"], settings)
        options.append({"day": d, "date": state.day_to_date(d), "result": res,
                        "risk": res["risk"], "level": level, "colour": colour, "label": label})
    safe = [o for o in options if o["risk"] < settings["low_risk_limit"]]
    suggested = safe[0] if safe else min(options, key=lambda o: o["risk"])
    return {"options": options, "suggested": suggested, "today": options[0]}


def explain(state: CashState, option: dict, amount: float, what: str) -> str:
    res = option["result"]
    if res["risk"] == 0 or res["fail_day_mode"] is None:
        return (f"In all {res['runs']:,} simulated futures, cash stays above your "
                f"{money(state.reserve)} reserve if you {what} on "
                f"{option['date']:%d %b}. Lowest typical cash: {money(res['typical_low'])}.")
    fail_day = res["fail_day_mode"]
    when = state.day_to_date(fail_day)
    near = [state.bill_labels[d] for d in range(fail_day, max(-1, fail_day - 4), -1)
            if d in state.bill_labels]
    bill_txt = f", when {', '.join(near[0])} is due" if near else ""
    text = (f"If you {what} on {option['date']:%d %b}, cash falls below your "
            f"{money(state.reserve)} reserve in {res['risk']:.0%} of {res['runs']:,} simulated "
            f"futures, most often around {when:%d %b}{bill_txt}.")
    top = main_cause(state, res)
    if top:
        r, share = top
        typical = state.model.get(r.customer, {}).get("median_late", 0)
        text += (f" Main reason: {r.customer}'s {r.invoice_no} ({money(r.amount)}) is usually "
                 f"paid about {typical:.0f} days after the due date; it was still unpaid in "
                 f"{share:.0%} of the bad futures.")
    return text


def main_cause(state: CashState, res: dict):
    if not res["causes"]:
        return None
    inv, share = max(res["causes"].items(), key=lambda kv: kv[1])
    if share < 0.2:
        return None
    r = next(x for x in state.receivables if x.invoice_no == inv)
    return r, share


def chase_suggestion(state: CashState, option: dict, amount: float, settings: dict):
    """Re-run as if the main late customer paid on time."""
    top = main_cause(state, option["result"])
    if not top:
        return None
    r, _ = top
    res = simulate(state, outflows=[(option["day"], amount)],
                   runs=int(settings.get("simulations", 1000)), force_on_time=r.invoice_no)
    draft = (f"Hi {r.customer}, hope you're well. A friendly reminder that invoice {r.invoice_no} "
             f"for {money(r.amount)} was due on {state.day_to_date(r.due_day):%d %b %Y}. "
             f"Could you let us know when payment will be made? Thank you! "
             f"- {settings['business_name']}")
    return {"receivable": r, "risk_before": option["risk"], "risk_after": res["risk"], "draft": draft}


def baseline(state: CashState, settings: dict) -> dict:
    """No new spending: how safe is the next 30 days already?"""
    return {"mc": simulate(state, runs=int(settings.get("simulations", 1000))),
            "rule": rule_check(state)}

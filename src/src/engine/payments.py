"""
A. Customer payment prediction ("training" = learning from past invoices).

For each customer we keep the list of past delays (days paid after the due date).
The Monte Carlo engine samples from it. Actuarial methods used:
  - Kaplan-Meier survival curve: chance an invoice is still unpaid after t days
    (unpaid invoices are handled as censored data).
  - Buhlmann credibility: a customer with few invoices is blended with the
    pattern of all customers. Credibility Z = n / (n + K), K = EPV / VHM.
"""

import numpy as np
import pandas as pd


def prepare(invoices: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    df = invoices.copy()
    df["paid"] = df["paid_date"].notna().astype(int)
    df["days_late"] = np.where(
        df["paid"] == 1,
        (df["paid_date"] - df["due_date"]).dt.days,
        (today - df["due_date"]).dt.days,
    )
    df["duration"] = df["days_late"].clip(lower=0)   # early payment counts as day 0
    return df


def credibility_k(paid: pd.DataFrame) -> float:
    """Buhlmann K = expected process variance / variance of hypothetical means."""
    groups = [g["days_late"].to_numpy(float) for _, g in paid.groupby("customer") if len(g) >= 2]
    if len(groups) < 2:
        return 5.0
    epv = float(np.mean([np.var(g, ddof=1) for g in groups]))
    means = np.array([g.mean() for g in groups])
    n_bar = float(np.mean([len(g) for g in groups]))
    vhm = float(np.var(means, ddof=1) - epv / n_bar)
    if vhm <= 0:
        return 50.0           # customers look alike -> lean on the group
    return float(np.clip(epv / vhm, 0.5, 50.0))


def train(invoices: pd.DataFrame, today: pd.Timestamp) -> dict:
    """Return {customer: {...}} learned from PAID invoices."""
    df = prepare(invoices, today)
    paid = df[df["paid"] == 1]
    pool = paid["days_late"].astype(int).tolist() or [0]
    k = credibility_k(paid)
    model = {}
    for customer, g in df.groupby("customer"):
        delays = g.loc[g["paid"] == 1, "days_late"].astype(int).tolist()
        n = len(delays)
        arr = np.array(delays or [0])
        model[customer] = {
            "delays": delays or [0],
            "n": n,
            "Z": n / (n + k),                       # credibility weight on own history
            "K": k,
            "pool": pool,
            "median_late": float(np.median(arr)),
            "p_on_time": float(np.mean(arr <= 0)),
            "still_unpaid_14": kaplan_meier(g["duration"], g["paid"], 14),
        }
    return model


def entry(model: dict, customer: str) -> dict:
    """Model entry; an unknown (new) customer gets Z = 0 = the all-customer pattern."""
    if customer in model:
        return model[customer]
    pool = next(iter(model.values()))["pool"] if model else [0]
    return {"delays": [0], "n": 0, "Z": 0.0, "pool": pool}


def sample_delays(model: dict, customer: str, overdue: int, size: int, rng) -> np.ndarray:
    """Draw payment delays: own history with probability Z, all customers otherwise.
    If the invoice is already `overdue` days late, only delays at least that long count."""
    e = entry(model, customer)
    own, pool = np.array(e["delays"]), np.array(e["pool"])
    if overdue > 0:
        own, pool = own[own >= overdue], pool[pool >= overdue]
    fallback = np.array([overdue + 30])
    own = own if len(own) else (pool if len(pool) else fallback)
    pool = pool if len(pool) else own
    use_own = rng.random(size) < e["Z"]
    return np.where(use_own, rng.choice(own, size), rng.choice(pool, size))


def conditional_median(model: dict, customer: str, days_overdue: int) -> float:
    """Typical delay for an invoice that is already `days_overdue` late (credibility-blended)."""
    rng = np.random.default_rng(0)
    return float(np.median(sample_delays(model, customer, days_overdue, 4000, rng)))


def kaplan_meier(durations, events, t: float) -> float:
    """Chance an invoice is STILL UNPAID t days after its due date.
    S = S x (1 - paid that day / still waiting), at each day someone paid.
    Unpaid invoices leave the waiting group without counting as paid (censoring)."""
    durations, events = np.asarray(durations), np.asarray(events)
    s = 1.0
    for day in np.unique(durations[(events == 1) & (durations <= t)]):
        at_risk = np.sum(durations >= day)
        paid_that_day = np.sum((durations == day) & (events == 1))
        s *= 1 - paid_that_day / at_risk
    return float(s)


def km_curve(invoices: pd.DataFrame, today: pd.Timestamp, customer: str, max_day: int = 40):
    df = prepare(invoices, today)
    g = df[df["customer"] == customer]
    days = list(range(0, max_day + 1))
    return days, [kaplan_meier(g["duration"], g["paid"], d) for d in days]


def _split(invoices, today):
    df = prepare(invoices, today)
    paid = df[df["paid"] == 1].sort_values("due_date")
    cut = int(len(paid) * 0.75)
    return paid.iloc[:cut], paid.iloc[cut:]


def backtest(invoices: pd.DataFrame, today: pd.Timestamp) -> dict:
    """Train on the older 75% of paid invoices, test on the newest 25%."""
    train_df, test_df = _split(invoices, today)
    medians = train_df.groupby("customer")["days_late"].median()
    pred = test_df["customer"].map(medians).fillna(0)
    return {
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "model_error_days": float(np.mean(np.abs(pred - test_df["days_late"]))),
        "naive_error_days": float(np.mean(np.abs(test_df["days_late"]))),
    }


def calibration(invoices: pd.DataFrame, today: pd.Timestamp, horizons=(0, 7, 14, 21)) -> pd.DataFrame:
    """Are the predicted chances honest? For each horizon t: average predicted chance an
    invoice is paid within t days (Kaplan-Meier from the OLDER invoices) vs what actually
    happened to the NEWER invoices."""
    train_df, test_df = _split(invoices, today)
    rows = []
    for t in horizons:
        preds = []
        for _, r in test_df.iterrows():
            g = train_df[train_df["customer"] == r["customer"]]
            preds.append(1 - kaplan_meier(g["duration"], g["paid"], t) if len(g) else 0.5)
        actual = float(np.mean(test_df["days_late"].to_numpy() <= t))
        rows.append({"Within (days after due date)": t, "Predicted paid": float(np.mean(preds)),
                     "Actually paid": actual})
    return pd.DataFrame(rows)

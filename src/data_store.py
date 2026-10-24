"""Load and save the demo data (CSV / JSON files in ./data)."""

import json
import os

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("CASHGUARD_DATA_DIR") or os.path.join(BASE, "data")   # tests use a temp folder

BILL_COLS = ["bill_no", "supplier", "amount", "issue_date", "due_date", "status",
             "pay_date", "category", "source", "captured_by", "repeat", "approved_by"]
REQUEST_COLS = ["request_id", "category", "item", "amount", "reason", "needed_by", "request_date",
                "submitted_by",
                "submitted_at", "status", "decision", "decision_date", "decision_reason",
                "decided_by", "risk_at_decision"]
AUDIT_COLS = ["time", "actor", "action", "details"]


def path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def load_settings() -> dict:
    with open(path("settings.json")) as f:
        return json.load(f)


def save_settings(settings: dict) -> None:
    with open(path("settings.json"), "w") as f:
        json.dump(settings, f, indent=2)


def today() -> pd.Timestamp:
    return pd.Timestamp(load_settings()["today"])


def _read(name: str, cols: list, dates: list) -> pd.DataFrame:
    p = path(name)
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(p)
    for c in dates:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def load_bills() -> pd.DataFrame:
    df = _read("bills.csv", BILL_COLS, ["issue_date", "due_date", "pay_date"])
    for c in BILL_COLS:             # older files may miss newer columns
        if c not in df.columns:
            df[c] = pd.NA
    return df


def save_bills(df: pd.DataFrame) -> None:
    df.to_csv(path("bills.csv"), index=False, date_format="%Y-%m-%d")


def load_invoices() -> pd.DataFrame:
    return _read("sales_invoices.csv", [], ["issue_date", "due_date", "paid_date"])


def load_daily_sales() -> pd.DataFrame:
    return _read("daily_sales.csv", ["date", "net_cash"], ["date"])


def load_requests() -> pd.DataFrame:
    df = _read("expense_requests.csv", REQUEST_COLS, ["needed_by", "decision_date"])
    for c in REQUEST_COLS:          # older files may miss newer columns
        if c not in df.columns:
            df[c] = pd.NA
    return df


def save_requests(df: pd.DataFrame) -> None:
    df.to_csv(path("expense_requests.csv"), index=False, date_format="%Y-%m-%d")

"""Append-only audit log: rows can be added, never edited or deleted."""

import csv
from datetime import datetime

import pandas as pd

from data_store import AUDIT_COLS, path


def log(actor: str, action: str, details: str = "") -> None:
    with open(path("audit_log.csv"), "a", newline="") as f:
        csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), actor, action, details])


def read() -> pd.DataFrame:
    try:
        df = pd.read_csv(path("audit_log.csv"))
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=AUDIT_COLS)
    return df.fillna("").iloc[::-1].reset_index(drop=True)   # newest first

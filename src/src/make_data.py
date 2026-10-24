"""
Create the synthetic (fictional) demo data for CashGuard Risk.

Run on its own:  python make_data.py
The app also calls generate() automatically when ./data is empty,
and the Owner can reset it from Settings.

Everything here is invented. No real business, customer or person.
"""

import json
import os

import numpy as np
import pandas as pd

from data_store import AUDIT_COLS, BILL_COLS, DATA_DIR, REQUEST_COLS, path
from policy import DEFAULT_CATEGORIES

TODAY = pd.Timestamp("2026-10-28")

SETTINGS = {
    "business_name": "Demo Café",
    "today": str(TODAY.date()),      # fixed demo date so results are repeatable
    "cash_today": 5500,
    "min_reserve": 2000,
    "low_risk_limit": 0.05,
    "high_risk_limit": 0.20,
    "horizon_days": 30,
    "simulations": 1000,
    "categories": DEFAULT_CATEGORIES,   # spending categories + staff limits (Owner can edit)
    "manager_approval_limit": 300,      # Manager may decide items up to this amount; above -> Owner
    "manager_monthly_limit": 1500,      # Manager may approve this much in total per month; above -> Owner
    "business_address": "12 Jalan Contoh, 47400 Petaling Jaya (demo)",
    "default_payment_terms": 30,        # days; used when a WhatsApp invoice form has no due date
    "supplier_profiles": {              # saved from earlier WhatsApp invoice forms (fictional)
        "+60120000101": {"supplier": "Kopi Bean Trading (demo)", "bank": "Maybank",
                         "account_name": "Kopi Bean Trading Sdn Bhd", "account_no": "5140-0000-1234",
                         "terms_days": 14},
    },
    "owner_whatsapp": "+60120000000",   # fictional number for the weekly summary
    "business_whatsapp": "+60120000999",  # fictional business number suppliers message (the bot)
    "notify_suppliers": True,           # bot tells suppliers: received, approved + pay date, paid
    "twilio_sandbox_code": "",          # e.g. "join happy-tiger" while testing with the Twilio sandbox
    "whatsapp_senders": [               # registered (trusted) senders - fictional numbers
        {"number": "+60120000101", "name": "Kopi Bean Trading (demo)", "type": "Supplier"},
        {"number": "+60120000102", "name": "Fresh Dairy Supply (demo)", "type": "Supplier"},
        {"number": "+60120000201", "name": "Staff Member", "type": "Staff"},
    ],
}

# Customer "personalities": mean days late, spread, typical invoice amount (RM)
CUSTOMERS = {
    "Client A": (17, 6, 2500),   # corporate catering - usually late
    "Client B": (0, 2, 1200),    # office - on time
    "Client C": (10, 12, 1800),  # events - unpredictable
    "Client D": (2, 3, 400),
    "Client E": (1, 2, 300),
}

# Invoices still unpaid today (these are the money we are waiting for)
OPEN_INVOICES = [
    ("INV-2041", "Client A", 2500, "2026-10-01", "2026-10-31"),
    ("INV-2043", "Client C", 1800, "2026-10-04", "2026-11-03"),
    ("INV-2045", "Client B", 1200, "2026-10-06", "2026-11-05"),
    ("INV-2047", "Client D", 400, "2026-10-09", "2026-11-08"),
]


def generate(force: bool = False) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(path("settings.json")) and not force:
        return
    rng = np.random.default_rng(7)

    with open(path("settings.json"), "w") as f:
        json.dump(SETTINGS, f, indent=2)

    # ---- Sales invoice history (paid) + open invoices ----------------------
    rows, n = [], 1000
    for customer, (mean_late, spread, amount) in CUSTOMERS.items():
        for _ in range(24):
            due = TODAY - pd.Timedelta(days=int(rng.integers(35, 200)))
            late = max(-3, int(round(rng.normal(mean_late, spread))))
            rows.append({
                "invoice_no": f"INV-{n}", "customer": customer,
                "amount": float(round(amount * rng.uniform(0.7, 1.3), -1)),
                "issue_date": (due - pd.Timedelta(days=30)).date(),
                "due_date": due.date(),
                "paid_date": (due + pd.Timedelta(days=late)).date(),
            })
            n += 1
    for inv, customer, amount, issue, due in OPEN_INVOICES:
        rows.append({"invoice_no": inv, "customer": customer, "amount": float(amount),
                     "issue_date": pd.Timestamp(issue).date(),
                     "due_date": pd.Timestamp(due).date(), "paid_date": None})
    pd.DataFrame(rows).sort_values("due_date").to_csv(path("sales_invoices.csv"), index=False)

    # ---- Daily net cash from walk-in sales (after daily ingredient costs) ---
    days = pd.date_range(TODAY - pd.Timedelta(days=90), TODAY - pd.Timedelta(days=1))
    net = [rng.normal(260, 150) if d.dayofweek >= 5 else rng.normal(140, 120) for d in days]
    pd.DataFrame({"date": days.date, "net_cash": np.round(net, 0)}).to_csv(
        path("daily_sales.csv"), index=False)

    # ---- Bills: upcoming + paid history (history used for "unusual amount") -
    bills = [
        ("SB-550", "Landlord (rent)", 2500, "2026-10-15", "2026-11-01", "To pay", "Rent"),
        ("SB-551", "Utilities", 700, "2026-10-20", "2026-11-10", "To pay", "Utilities"),
        ("PAY-NOV", "Payroll (6 staff)", 4000, "2026-10-25", "2026-11-25", "To pay", "Payroll"),
        ("SB-512", "Kopi Bean Trading (demo)", 1600, "2026-08-01", "2026-08-31", "Paid", "Supplier"),
        ("SB-527", "Kopi Bean Trading (demo)", 1700, "2026-09-01", "2026-09-30", "Paid", "Supplier"),
        ("SB-540", "Fresh Dairy Supply (demo)", 600, "2026-09-10", "2026-10-10", "Paid", "Supplier"),
    ]
    bdf = pd.DataFrame([{
        "bill_no": b[0], "supplier": b[1], "amount": float(b[2]), "issue_date": b[3],
        "due_date": b[4], "status": b[5], "pay_date": "", "category": b[6],
        "source": "Recurring" if b[6] in ("Rent", "Utilities", "Payroll") else "Uploaded",
        "captured_by": "System",
        "repeat": "monthly" if b[6] in ("Rent", "Utilities", "Payroll") else "",
        "approved_by": "",
    } for b in bills], columns=BILL_COLS)
    bdf.to_csv(path("bills.csv"), index=False)

    pd.DataFrame(columns=REQUEST_COLS).to_csv(path("expense_requests.csv"), index=False)
    pd.DataFrame(columns=AUDIT_COLS).to_csv(path("audit_log.csv"), index=False)


if __name__ == "__main__":
    generate(force=True)
    print("Synthetic demo data written to ./data")

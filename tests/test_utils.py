"""Unit tests for the CashGuard engine. Run from the repo root:  pytest -q"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import data_store as ds                                      # noqa: E402
import make_data                                             # noqa: E402
import policy                                                # noqa: E402
from capture.extract import checks, line_items_check         # noqa: E402
from engine.explain import evaluate_options, money           # noqa: E402
from engine.montecarlo import build_state, simulate          # noqa: E402
from engine.payments import credibility_k, kaplan_meier, train  # noqa: E402
from utils import pct                                        # noqa: E402


def demo():
    make_data.generate(force=True)
    ds.save_settings({**ds.load_settings(), "business_name": "Test Café", "setup_done": True})
    s = ds.load_settings()
    inv = ds.load_invoices()
    model = train(inv, pd.Timestamp(s["today"]))
    return s, ds.load_bills(), inv, ds.load_daily_sales(), model


def test_money_and_pct():
    assert money(1800) == "RM1,800"
    assert money(-250) == "-RM250"
    assert pct(0.237) == "23.7%"


def test_kaplan_meier_handles_censoring():
    d, e = np.array([1, 2, 3, 4, 5]), np.array([1, 1, 0, 1, 0])   # 0 = still unpaid (censored)
    surv = np.array([kaplan_meier(d, e, t) for t in range(0, 7)])
    assert surv[0] == 1.0 and 0.0 <= surv[-1] < 1.0
    assert np.all(np.diff(surv) <= 1e-12)          # survival never goes up
    # hand check: after day 1 -> 4/5; after day 2 -> 4/5 * 3/4 = 0.6; day 4 -> 0.6 * 1/2 = 0.3
    assert abs(surv[4] - 0.3) < 1e-9


def test_credibility_weight_in_range():
    s, bills, inv, sales, model = demo()
    for cust in model.values():
        if isinstance(cust, dict) and "Z" in cust:
            assert 0.0 <= cust["Z"] <= 1.0


def test_line_items_must_add_up():
    good = {"amount": 1800, "line_items": [{"total": 1280}, {"total": 520}]}
    bad = {"amount": 1900, "line_items": [{"total": 1280}, {"total": 520}]}
    assert not line_items_check(good)
    assert line_items_check(bad)


def test_duplicate_invoice_is_blocked():
    s, bills, *_ = demo()
    row = bills.iloc[0]
    fields = {"supplier": row["supplier"], "invoice_no": row["bill_no"], "amount": float(row["amount"]),
              "issue_date": "2026-10-20", "due_date": "2026-11-20", "line_items": []}
    assert any(level == "error" for level, _ in checks(fields, bills, pd.Timestamp(s["today"])))


def test_simulation_is_repeatable_and_paying_more_is_riskier():
    s, bills, inv, sales, model = demo()
    state = build_state(s, bills, inv, sales, model)
    a = simulate(state, outflows=[(0, 1800)], runs=500)["risk"]
    b = simulate(state, outflows=[(0, 1800)], runs=500)["risk"]
    c = simulate(state, outflows=[(0, 4000)], runs=500)["risk"]
    assert a == b                                   # fixed seed -> same answer
    assert c >= a                                   # bigger payment, never less risk


def test_suggested_date_never_after_due_date():
    s, bills, inv, sales, model = demo()
    state = build_state(s, bills, inv, sales, model)
    ev = evaluate_options(state, 1800, "bill", {**s, "simulations": 400}, due_day=8)
    assert ev["suggested"]["day"] <= 8


def test_staff_limit_blocks_large_request():
    s, *_ = demo()
    reqs = ds.load_requests()
    over = policy.check(250, "Staff allowance", "Staff Member (Employee)", reqs, s, pd.Timestamp(s["today"]))
    ok = policy.check(150, "Staff allowance", "Staff Member (Employee)", reqs, s, pd.Timestamp(s["today"]))
    assert not over["ok"] and ok["ok"]


# ---------------------------------------------------------------- WhatsApp invoice form
from whatsapp import invoice_form as form   # noqa: E402

FILLED = """Supplier name: Fresh Dairy Supply (demo)
Invoice no (optional):
Item 1: Fresh milk 1L, 150, 4.20
Item 2 (optional): Whipping cream 1L | 10 | RM2.00
Item 3 (optional):
Due date (optional, DD/MM/YYYY):
Bank name: CIMB Bank
Account name: Fresh Dairy Supply Sdn Bhd
Account no: 8000-0000-5678
Notes (optional): Delivered 27 Oct"""


def test_invoice_form_defaults_and_pdf():
    s, *_ = demo()
    res = form.process_form(FILLED, "+600000000102", s, pd.Timestamp(s["today"]), 1)
    assert res["ok"], res["reply"]
    inv = res["invoice"]
    assert inv["amount"] == 650.0                              # 150 x 4.20 + 10 x 2.00
    assert inv["invoice_no"].startswith("WA-")                  # auto number
    assert inv["due_date"] == "2026-11-27"                      # default 30 days after 28 Oct
    assert inv["bill_to"] == s["business_name"]
    assert res["pdf"][:4] == b"%PDF"


def test_invoice_form_uses_saved_profile_and_flags_new_bank():
    s, *_ = demo()
    text = "Supplier name:\nItem 1: Arabica beans 1kg, 40, 32\nBank name:\nAccount name:\nAccount no:"
    res = form.process_form(text, "+600000000101", s, pd.Timestamp(s["today"]), 2)
    assert res["ok"] and res["invoice"]["account_no"] == "5140-0000-1234"   # filled from saved profile
    assert res["invoice"]["due_date"] == "2026-11-11"                       # supplier's 14-day terms
    changed = text.replace("Account no:", "Account no: 9999-1111-2222")
    res2 = form.process_form(changed, "+600000000101", s, pd.Timestamp(s["today"]), 3)
    assert res2["invoice"]["bank_changed"]                                  # possible fraud -> flagged


def test_invoice_form_reports_missing_fields():
    s, *_ = demo()
    res = form.process_form("Supplier name: X\nItem 1: description, qty, unit price", "+60111111111", s,
                            pd.Timestamp(s["today"]), 1)
    assert not res["ok"] and "item" in res["reply"].lower()


# ---------------------------------------------------------------- supplier updates + share link
from whatsapp import notify   # noqa: E402


def test_supplier_updates_and_share_link():
    s, *_ = demo()
    bill = {"bill_no": "SB-552", "supplier": "Kopi Bean Trading (demo)", "amount": 1800,
            "due_date": pd.Timestamp("2026-11-05"), "pay_date": pd.Timestamp("2026-11-04")}
    assert "04 Nov 2026" in notify.message("scheduled", bill, s["business_name"])
    assert "transferred RM1,800.00" in notify.message("paid", bill, s["business_name"])
    assert notify.supplier_phone("SB-552", "Kopi Bean Trading (demo)", s) == "+600000000101"
    assert notify.share_link("+60 0-000 0999") == "https://wa.me/6000000999?text=INVOICE"
    assert notify.qr_png("https://wa.me/600000999?text=INVOICE")[:4] == b"\x89PNG"
    number, text, status = notify.notify_supplier("paid", bill, s)
    assert number == "+600000000101" and "demo" in status          # no keys -> logged, not sent
    assert notify.notify_supplier("paid", bill, {**s, "notify_suppliers": False}) is None

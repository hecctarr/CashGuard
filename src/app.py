"""
CashGuard Risk - actuarial cash-risk check for SMEs (hackathon demo)

Run:   pip install -r requirements.txt
       streamlit run app.py

All data is synthetic and fictional. Login and roles are simulated.
"""

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import audit
import data_store as ds
import policy
from capture.extract import extract, checks, FALLBACK
from capture.make_demo_invoices import main as make_demo_invoices
from engine.explain import (baseline, chase_suggestion, evaluate_options, explain,
                            money, risk_level)
from engine.montecarlo import build_state, simulate
from engine.payments import backtest, calibration, conditional_median, km_curve, train
from engine.impact import run_impact
from engine.montecarlo import rule_check
from whatsapp import inbox
from whatsapp.send import read_outbox, send_whatsapp
from whatsapp import invoice_form as wa_form
from whatsapp import notify
from make_data import generate

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
LOGO = os.path.join(ASSETS, "logo_navy.png")
LOGO_WHITE = os.path.join(ASSETS, "logo_white.png")
st.set_page_config(page_title="CashGuard Risk", page_icon=os.path.join(ASSETS, "logo_navy_64.png"), layout="wide")
st.markdown("""<style>
:root { --cg-navy:#152846; --cg-navy-2:#1F3A66; --cg-sky:#E8EDF5; --cg-line:#D5DDEA; }
[data-testid="stSidebar"] { background: var(--cg-navy); }
[data-testid="stSidebar"] * { color: #E9EEF7 !important; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.18); }
[data-testid="stSidebar"] [role="radiogroup"] label { padding: 6px 10px; border-radius: 8px; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background: var(--cg-navy-2); }
[data-testid="stSidebar"] button { background: transparent; border: 1px solid rgba(255,255,255,.35); }
h1, h2, h3, h4 { color: var(--cg-navy); letter-spacing: -0.01em; }
[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid var(--cg-line); border-radius: 12px; padding: 14px 16px; }
[data-testid="stMetricValue"] { color: var(--cg-navy); font-variant-numeric: tabular-nums; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; }
.stTabs [aria-selected="true"] { color: var(--cg-navy) !important; }
.cg-brand { display:flex; align-items:center; gap:14px; margin: 4px 0 6px; }
.cg-brand b { font-size: 1.9rem; color: var(--cg-navy); letter-spacing: -0.02em; }
.cg-brand span { display:block; color:#5A6785; font-size: .95rem; }
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# First run: create synthetic data + demo invoices
# ---------------------------------------------------------------------------
generate()
if not os.path.exists(FALLBACK):
    make_demo_invoices()
DEMO_DIR = os.path.join(ds.BASE, "demo_invoices")

USERS = {
    "owner": {"name": "Business Owner", "role": "Owner",
              "can": ["See cash, risk and charts", "Pay / schedule / hold bills",
                      "Approve or reject spending", "Set reserve and risk limits",
                      "View full audit log"]},
    "manager": {"name": "Shift Manager", "role": "Manager",
                "can": ["Approve bills and requests up to the manager limit",
                        "Upload invoices and submit requests",
                        "Cannot approve own submissions"]},
    "staff": {"name": "Staff Member", "role": "Employee",
              "can": ["Upload supplier invoices", "Submit expense requests",
                      "See status of own submissions"]},
}
PAGES = {
    "Owner": ["Dashboard", "Review & decide", "Invoices", "What-if simulator",
              "Impact test", "Audit log", "Settings"],
    "Manager": ["Review & decide", "Upload bill", "New expense request", "My submissions"],
    "Employee": ["Upload bill", "New expense request", "My submissions"],
}
COLOUR = {"green": "green", "orange": "orange", "red": "red"}

if "user" not in st.session_state:
    st.session_state.user = None
if "extraction" not in st.session_state:
    st.session_state.extraction = None
if "risk_sent" not in st.session_state:
    st.session_state.risk_sent = set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def actor() -> str:
    u = st.session_state.user
    return f"{u['name']} ({u['role']})"


def record(action: str, details: str = "") -> None:
    """Every step goes to the append-only audit log."""
    audit.log(actor(), action, details)


def load_all():
    settings = ds.load_settings()
    today = pd.Timestamp(settings["today"])
    invoices = ds.load_invoices()
    return {
        "settings": settings, "today": today, "bills": ds.load_bills(),
        "invoices": invoices, "sales": ds.load_daily_sales(),
        "requests": ds.load_requests(), "model": train(invoices, today),
    }


def state_for(d, exclude_bill=None):
    return build_state(d["settings"], d["bills"], d["invoices"], d["sales"], d["model"],
                       exclude_bill=exclude_bill)


def badge(level: str, colour: str) -> str:
    return f":{COLOUR[colour]}[**{level} risk**]"


def fan_chart(state, res, title, compare=None, compare_label=""):
    x = [state.day_to_date(i) for i in range(state.horizon)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=res["p95"], line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=res["p5"], fill="tonexty", line=dict(width=0),
                             fillcolor="rgba(21,40,70,0.12)",
                             name="Range of 90% of futures"))
    fig.add_trace(go.Scatter(x=x, y=res["p50"], name="Typical future",
                             line=dict(color="#152846", width=2.5)))
    if compare is not None:
        fig.add_trace(go.Scatter(x=x, y=compare["p50"], name=compare_label,
                                 line=dict(color="#2F9E6E", width=2.5, dash="dash")))
    fig.add_hline(y=state.reserve, line=dict(color="#C0392B", dash="dot"),
                  annotation_text=f"Minimum reserve {money(state.reserve)}",
                  annotation_position="bottom right")
    fig.update_layout(title=title, height=360, margin=dict(l=10, r=10, t=50, b=10),
                      yaxis_title="Cash (RM)", legend=dict(orientation="h", y=-0.15))
    return fig


def pending_items(d):
    items = []
    for _, b in d["bills"][d["bills"]["status"] == "Awaiting review"].iterrows():
        items.append({"id": b["bill_no"], "kind": "bill", "label":
                      f"Bill {b['bill_no']} · {b['supplier']} · {money(b['amount'])} · due {b['due_date']:%d %b}",
                      "amount": float(b["amount"]), "row": b})
    for _, r in d["requests"][d["requests"]["status"] == "Pending"].iterrows():
        items.append({"id": r["request_id"], "kind": "expense", "label":
                      f"Request {r['request_id']} · {r['category'] if pd.notna(r['category']) else 'Other'} · "
                      f"{r['item']} · {money(r['amount'])}",
                      "amount": float(r["amount"]), "row": r})
    return items


def manager_limit() -> float:
    """Largest single bill or request a Manager may decide (set by the Owner)."""
    return float(ds.load_settings().get("manager_approval_limit", 300))


def manager_monthly_limit() -> float:
    """Total a Manager may approve in one calendar month (set by the Owner)."""
    return float(ds.load_settings().get("manager_monthly_limit", 1500))


MANAGER_ACTOR = "Shift Manager (Manager)"


def manager_used_this_month(d) -> float:
    """What the Manager has already approved this month (bills scheduled/paid + requests approved)."""
    month = d["today"].to_period("M")
    used = 0.0
    b = d["bills"]
    if "approved_by" in b.columns:
        mb = b[(b["approved_by"].astype(str) == MANAGER_ACTOR) & b["status"].isin(["Paid", "Scheduled"])]
        used += float(mb[pd.to_datetime(mb["pay_date"]).dt.to_period("M") == month]["amount"].sum()) if len(mb) else 0.0
    r = d["requests"]
    if len(r):
        mr = r[(r["decided_by"].astype(str) == MANAGER_ACTOR) & (r["status"] == "Approved")]
        if len(mr):
            used += float(mr[pd.to_datetime(mr["decision_date"]).dt.to_period("M") == month]["amount"].sum())
    return used


def submitted_by(item) -> str:
    r = item["row"]
    return str(r.get("captured_by") if item["kind"] == "bill" else r.get("submitted_by"))


def calendar_rows(d, state):
    """Next 30 days: bills going out and customer money expected in, with typical cash."""
    rule = rule_check(state)
    rows = []
    for _, b in d["bills"][d["bills"]["status"].isin(["To pay", "Scheduled", "On hold", "Awaiting review"])].iterrows():
        when = b["pay_date"] if pd.notna(b["pay_date"]) else b["due_date"]
        day = max(0, (when - d["today"]).days)
        if day < state.horizon:
            rows.append({"day": day, "Type": "Bill out", "Name": b["supplier"], "Amount": -float(b["amount"]),
                         "Status": b["status"]})
    for r in state.receivables:
        delay = conditional_median(d["model"], r.customer, r.overdue)
        day = max(1, int(round(r.due_day + delay)))
        if day < state.horizon:
            rows.append({"day": day, "Type": "Expected in", "Name": f"{r.customer} {r.invoice_no}",
                         "Amount": r.amount, "Status": f"due {state.day_to_date(r.due_day):%d %b}, usually late"
                         if delay >= 3 else f"due {state.day_to_date(r.due_day):%d %b}"})
    rows.sort(key=lambda x: (x["day"], x["Type"]))
    for x in rows:
        x["Date"] = f"{state.day_to_date(x['day']):%a %d %b}"
        x["Typical cash after"] = money(rule["path"][x["day"]])
        x["Amount"] = ("+" if x["Amount"] > 0 else "") + money(x["Amount"])
    return pd.DataFrame(rows, columns=["Date", "Type", "Name", "Amount", "Status", "Typical cash after"])


def alerts(d, state, base):
    out = []
    lvl = risk_level(base["mc"]["risk"], d["settings"])[0]
    if lvl != "Low":
        out.append(("warning", f"Cash risk for the next 30 days is {lvl} ({base['mc']['risk']:.0%}) "
                               f"even before any new spending."))
    rule = base["rule"]
    for day in range(0, 8):
        for name in state.bill_labels.get(day, []):
            out.append(("info", f"{name} is due {state.day_to_date(day):%a %d %b} - typical cash after: "
                                f"{money(rule['path'][day])}."))
    for r in state.receivables:
        delay = conditional_median(d["model"], r.customer, r.overdue)
        if delay >= 7 and r.amount >= 1000:
            out.append(("warning", f"{r.customer}'s {r.invoice_no} ({money(r.amount)}) is likely to arrive about "
                                   f"{delay:.0f} days after its due date - consider a reminder."))
    new_wa = inbox.list_messages("New")
    if new_wa:
        out.append(("info", f"{len(new_wa)} invoice(s) arrived on WhatsApp and are waiting for staff to confirm."))
    return out


def weekly_summary(d, state, base, items) -> str:
    lvl = risk_level(base["mc"]["risk"], d["settings"])[0]
    due7 = sum(state.fixed_out[:7])
    owed = sum(r.amount for r in state.receivables)
    return (f"CashGuard weekly summary - {d['settings']['business_name']}\n"
            f"Cash today: {money(d['settings']['cash_today'])}\n"
            f"Bills due in 7 days: {money(due7)}\n"
            f"Customers owe you: {money(owed)}\n"
            f"Cash risk next 30 days: {lvl} ({base['mc']['risk']:.0%})\n"
            f"Waiting for your review: {len(items)}\n"
            f"Open CashGuard to review and decide.")


def confirm_invoice(key, file_name, file_bytes, ex, source, sender_note=""):
    """Shared confirm form for uploaded and WhatsApp invoices. Returns the new bill no. when saved."""
    st.caption(f"Read by: {ex['method']}" + (f" · {sender_note}" if sender_note else ""))
    f0, conf = ex["fields"], ex.get("confidence", {})

    def lbl(k, name):
        return f"{name} ⚠️ please check" if conf.get(k) == "low" else name

    items = f0.get("line_items") or []
    if items:
        st.dataframe(pd.DataFrame(items), hide_index=True, use_container_width=True)
    with st.form(f"confirm_{key}"):
        supplier = st.text_input(lbl("supplier", "Supplier"), f0.get("supplier") or "")
        inv_no = st.text_input(lbl("invoice_no", "Invoice no."), f0.get("invoice_no") or "")
        amount = st.number_input(lbl("amount", "Amount (RM)"), 0.0, 1e7, float(f0.get("amount") or 0), 10.0)
        issue = st.date_input(lbl("issue_date", "Invoice date"),
                              pd.Timestamp(f0["issue_date"]).date() if f0.get("issue_date") else D["today"].date())
        due = st.date_input(lbl("due_date", "Due date"),
                            pd.Timestamp(f0["due_date"]).date() if f0.get("due_date") else D["today"].date())
        ok = st.form_submit_button("Confirm and submit for review", type="primary")
    if not ok:
        return None
    fields = {"supplier": supplier.strip(), "invoice_no": inv_no.strip(), "amount": amount,
              "issue_date": str(issue), "due_date": str(due), "line_items": items}
    problems = checks(fields, D["bills"], D["today"])
    for level, msg in problems:
        (st.error if level == "error" else st.warning)(msg)
    if any(level == "error" for level, _ in problems):
        return None
    changed = [k for k in ("supplier", "invoice_no", "amount", "issue_date", "due_date")
               if f0.get(k) is not None and str(f0.get(k)) != str(fields[k])]
    new = {"bill_no": fields["invoice_no"], "supplier": fields["supplier"], "amount": float(amount),
           "issue_date": pd.Timestamp(issue), "due_date": pd.Timestamp(due), "status": "Awaiting review",
           "pay_date": pd.NaT, "category": "Supplier", "source": source, "captured_by": actor(),
           "repeat": "", "approved_by": ""}
    ds.save_bills(pd.concat([D["bills"], pd.DataFrame([new])], ignore_index=True))
    record("Captured invoice", f"{inv_no}, {supplier}, {money(amount)} via {source} ({ex['method']})")
    record("Confirmed fields", "Corrected: " + (", ".join(
        f"{k} {f0.get(k)} → {fields[k]}" for k in changed) or "none"))
    return fields["invoice_no"]


def tell_supplier(event: str, bill_no: str):
    """WhatsApp the supplier about their invoice's status (submitted / scheduled / paid / hold)."""
    bills = ds.load_bills()
    row = bills[bills["bill_no"] == bill_no]
    if row.empty:
        return
    out = notify.notify_supplier(event, row.iloc[0].to_dict(), ds.load_settings())
    if out:
        number, text, status = out
        audit.log("WhatsApp bot", f"Supplier update: {event}", f"{bill_no} to {number}: {status}")
        st.session_state.flash_supplier = f"WhatsApp update to supplier ({status}): \"{text}\""


def evaluate_item(d, item, **what_if):
    if item["kind"] == "bill":
        state = state_for(d, exclude_bill=item["id"])
        due_day = state.date_to_day(item["row"]["due_date"])
        ev = evaluate_options(state, item["amount"], "bill", d["settings"], due_day=due_day, **what_if)
    else:
        state = state_for(d)
        due_day = None
        ev = evaluate_options(state, item["amount"], "expense", d["settings"], **what_if)
    return state, ev, due_day


# ---------------------------------------------------------------------------
# LOGIN (simulated - no passwords)
# ---------------------------------------------------------------------------
if st.session_state.user is None:
    _, mid, _ = st.columns([1, 6, 1])
    with mid:
        lc, tc = st.columns([1, 6], vertical_alignment="center")
        lc.image(LOGO, width=72)
        tc.markdown('<div class="cg-brand"><div><b>CashGuard Risk</b>'
                    '<span>Cash safety check for small businesses</span></div></div>', unsafe_allow_html=True)
        st.info("**Demo mode:** simulated sign-in. No passwords, no real accounts, "
                "fictional business data only.")
        st.markdown("#### Choose who to sign in as")
        cols = st.columns(3)
        for col, uid in zip(cols, ("owner", "manager", "staff")):
            u = USERS[uid]
            with col, st.container(border=True):
                st.markdown(f"**{u['name']}**")
                st.caption(f"{u['role']} · {ds.load_settings()['business_name']}")
                for c in u["can"]:
                    st.markdown(f"- {c}")
                if st.button(f"Sign in as {u['role']}", key=f"login_{uid}",
                             use_container_width=True,
                             type="primary" if u["role"] == "Owner" else "secondary"):  # noqa
                    st.session_state.user = {"id": uid, **u}
                    record("Signed in", "Simulated login")
                    st.rerun()
        st.caption("In real use, each person signs in with their own account and role.")
    st.stop()

# ---------------------------------------------------------------------------
# FRAME: sidebar menu
# ---------------------------------------------------------------------------
user = st.session_state.user
D = load_all()
S = D["settings"]

with st.sidebar:
    lc, tc = st.columns([1, 3], vertical_alignment="center")
    lc.image(LOGO_WHITE, width=44)
    tc.markdown(f"**CashGuard**  \n{S['business_name']}")
    st.divider()
    page = st.radio("CashGuard", PAGES[user["role"]])
    st.divider()
    st.caption(f"Signed in as **{user['name']}** ({user['role']})")
    st.caption(f"Demo date: {D['today']:%d %b %Y}")
    if st.button("Sign out", use_container_width=True):
        record("Signed out")
        st.session_state.user = None
        st.session_state.extraction = None
        st.rerun()

st.markdown(f"## {page}")
if st.session_state.get("flash_supplier"):
    st.info("📱 " + st.session_state.pop("flash_supplier"))

# ===========================================================================
# OWNER PAGES
# ===========================================================================
if page == "Dashboard":
    state = state_for(D)
    base = baseline(state, S)
    items = pending_items(D)
    active = D["bills"][D["bills"]["status"].isin(["To pay", "Scheduled", "On hold", "Awaiting review"])]
    due30 = active[active["due_date"] <= D["today"] + pd.Timedelta(days=S["horizon_days"])]
    owed = D["invoices"][D["invoices"]["paid_date"].isna()]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cash today", money(S["cash_today"]))
    c2.metric(f"Bills due in {S['horizon_days']} days", money(due30["amount"].sum()))
    c3.metric("Customers owe you", money(owed["amount"].sum()))
    c3.caption(f"{len(owed)} unpaid invoices")
    c4.metric("Waiting for your review", len(items))

    lvl, colour, label = risk_level(base["mc"]["risk"], S)
    st.markdown(f"**Next {S['horizon_days']} days with no new spending:** "
                f"{badge(lvl, colour)} · {base['mc']['risk']:.0%} chance cash falls below "
                f"your {money(S['min_reserve'])} reserve")

    if items:
        st.markdown("#### Needs your attention")
        for it in items:
            _, ev, _ = evaluate_item(D, it)
            t = ev["today"]
            sug = ev["suggested"]
            st.markdown(f"- {it['label']} — pay/spend today: {badge(t['level'], t['colour'])} "
                        f"({t['risk']:.1%}); safest: **{sug['date']:%d %b}** ({sug['risk']:.1%}). "
                        f"Open **Review & decide**.")
    st.markdown("#### Alerts")
    for level, msg in alerts(D, state, base):
        (st.warning if level == "warning" else st.info)(msg)
    st.plotly_chart(fan_chart(state, base["mc"], "Cash for the next 30 days (1,000 simulated futures)"),
                    use_container_width=True)
    st.markdown("#### Payment calendar - next 30 days")
    st.dataframe(calendar_rows(D, state), hide_index=True, use_container_width=True)
    with st.expander("📱 Weekly WhatsApp summary to the owner"):
        text = weekly_summary(D, state, base, items)
        st.code(text, language=None)
        if st.button("Send summary now"):
            status = send_whatsapp(S.get("owner_whatsapp", ""), text)
            record("Sent weekly summary", status)
            st.success(f"Summary: {status}.")

elif page == "Review & decide":
    items = pending_items(D)
    limit = manager_limit()
    if user["role"] == "Manager":
        m_month = manager_monthly_limit()
        m_used = manager_used_this_month(D)
        m_left = max(0.0, m_month - m_used)
        above = [i for i in items if i["amount"] > min(limit, m_left)]
        items = [i for i in items if i["amount"] <= min(limit, m_left)]
        c1, c2, c3 = st.columns(3)
        c1.metric("Your limit per item", money(limit))
        c2.metric("Approved this month", money(m_used), help=f"Monthly limit {money(m_month)}")
        c3.metric("Left this month", money(m_left))
        st.caption(f"Limits are set by the Owner. {len(above)} item(s) above your limits are waiting for the Owner.")
    if not items:
        st.success("Nothing waiting for your review.")
        st.stop()
    choice = st.selectbox("Item to review", [i["label"] for i in items])
    item = next(i for i in items if i["label"] == choice)
    state, ev, due_day = evaluate_item(D, item)
    today_opt, sug = ev["today"], ev["suggested"]
    verb = "pay this bill" if item["kind"] == "bill" else "buy this"

    if item["id"] not in st.session_state.risk_sent:   # log each risk assessment once
        audit.log("CashGuard", "Risk assessed",
                  f"{item['id']}: today {today_opt['risk']:.1%} ({today_opt['level']}); "
                  f"safest {sug['date']:%d %b} {sug['risk']:.1%} ({sug['level']})")
        st.session_state.risk_sent.add(item["id"])

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"**If paid/spent today**  \n{badge(today_opt['level'], today_opt['colour'])}")
        c1.metric("Chance of going below reserve", f"{today_opt['risk']:.1%}", label_visibility="collapsed")
        c2.metric("Bad-case lowest cash (today)", money(today_opt["result"]["worst5"]),
                  help="Lowest cash in the worst 5% of simulated futures")
        c3.markdown(f"**Safest date**  \n{badge(sug['level'], sug['colour'])}")
        c3.metric("Suggested date", f"{sug['date']:%d %b}", label_visibility="collapsed")
        c3.caption(f"{sug['risk']:.1%} chance of going below reserve")
        c4.metric("Amount", money(item["amount"]))
        if item["kind"] == "bill":
            c4.caption(f"Due {item['row']['due_date']:%d %b}")
        else:
            r0 = item["row"]
            cat = r0["category"] if pd.notna(r0["category"]) else "Other"
            lim = policy.categories(S).get(cat, policy.DEFAULT_CATEGORIES["Other"])
            c4.caption(f"{cat} · by {r0['submitted_by']}  \nWithin limit: max {money(lim['max_per_request'])} "
                       f"per request, {money(lim['monthly_limit'])} per month")

    st.info(explain(state, today_opt, item["amount"], verb))
    if sug["day"] != today_opt["day"]:
        st.success(f"Safer option: {verb} on **{sug['date']:%d %b}** "
                   + ("(still on time). " if item["kind"] == "bill" else ". ")
                   + f"Risk drops from {today_opt['risk']:.1%} to {sug['risk']:.1%}.")

    st.plotly_chart(fan_chart(state, today_opt["result"], f"Cash if you {verb} today",
                              compare=sug["result"] if sug["day"] != today_opt["day"] else None,
                              compare_label=f"Typical future if {sug['date']:%d %b}"),
                    use_container_width=True)

    st.markdown("#### All options tested")
    st.dataframe(pd.DataFrame([{
        "Date": f"{o['date']:%a %d %b}", "Risk below reserve": f"{o['risk']:.1%}",
        "Level": o["level"], "Typical lowest cash": money(o["result"]["typical_low"]),
        "Bad-case lowest cash": money(o["result"]["worst5"]),
        "Suggested": "✓" if o is sug else ""} for o in ev["options"]]),
        hide_index=True, use_container_width=True)

    chase = chase_suggestion(state, today_opt, item["amount"], S)
    if chase and chase["risk_after"] < chase["risk_before"]:
        r = chase["receivable"]
        with st.expander(f"💬 Chase suggestion: {r.customer} ({r.invoice_no}) — risk "
                         f"{chase['risk_before']:.1%} → {chase['risk_after']:.1%} if they pay on time"):
            draft = st.text_area("Reminder draft (owner approves; not sent in demo)", chase["draft"])
            if st.button("Approve reminder draft"):
                record("Approved chase draft", f"{r.customer} {r.invoice_no} (draft only, not sent)")
                st.success("Draft approved and logged. In real use it would be sent via WhatsApp/email.")

    st.markdown("#### Your decision")
    if submitted_by(item) == actor():
        st.warning("You submitted this item, so someone else must decide it (separation of duties).")
        st.stop()
    if user["role"] == "Owner" and item["amount"] > limit:
        st.caption(f"Above the {money(limit)} manager limit - Owner decision.")
    with st.form("decision"):
        if item["kind"] == "bill":
            opts = ["Pay now (today)", f"Schedule on suggested date ({sug['date']:%d %b})",
                    "Schedule on another date", "Hold"]
        else:
            opts = ["Approve - buy today", f"Approve - buy on suggested date ({sug['date']:%d %b})",
                    "Approve - buy on another date", "Reject"]
        decision = st.radio("Choose", opts)
        other = st.date_input("Other date (only if you chose 'another date')",
                              value=sug["date"].date(), min_value=D["today"].date())
        reason = st.text_input("Reason (required if the option is high risk)")
        submit = st.form_submit_button("Save decision", type="primary")

    if submit:
        idx = opts.index(decision)
        if idx == 0:
            day = 0
        elif idx == 1:
            day = sug["day"]
        elif idx == 2:
            day = state.date_to_day(other)
        else:
            day = None
        chosen_risk = None
        if day is not None:
            chosen_risk = simulate(state, outflows=[(day, item["amount"])],
                                   runs=int(S["simulations"]))["risk"]
        lvl = risk_level(chosen_risk, S)[0] if chosen_risk is not None else "-"
        late = item["kind"] == "bill" and day is not None and day > due_day
        if lvl == "High" and not reason.strip():
            st.error(f"This option is high risk ({chosen_risk:.0%}). Please write a reason.")
            st.stop()
        if late and not reason.strip():
            st.error("That date is after the bill's due date. Please write a reason.")
            st.stop()

        pay_date = state.day_to_date(day) if day is not None else None
        bills = D["bills"].copy()
        if item["kind"] == "bill":
            m = bills["bill_no"] == item["id"]
            if day == 0:
                bills.loc[m, ["status", "pay_date"]] = ["Paid", D["today"]]
                bills["approved_by"] = bills["approved_by"].astype(object)
                bills.loc[m, "approved_by"] = actor()
                S["cash_today"] = float(S["cash_today"]) - item["amount"]
                ds.save_settings(S)
                text = "Marked as paid today (no real payment in demo)"
            elif day is None:
                bills.loc[m, "status"] = "On hold"
                text = "On hold (still counted at its due date)"
            else:
                bills.loc[m, ["status", "pay_date"]] = ["Scheduled", pay_date]
                bills["approved_by"] = bills["approved_by"].astype(object)
                bills.loc[m, "approved_by"] = actor()
                text = f"Scheduled for {pay_date:%d %b}"
            ds.save_bills(bills)
            tell_supplier("paid" if day == 0 else ("hold" if day is None else "scheduled"), item["id"])
        else:
            reqs = D["requests"].copy()
            for col in ("status", "decision", "decision_reason", "decided_by", "risk_at_decision"):
                reqs[col] = reqs[col].astype(object)
            m = reqs["request_id"] == item["id"]
            if day is None:
                reqs.loc[m, "status"] = "Rejected"
                text = "Rejected"
            else:
                reqs.loc[m, "status"] = "Approved"
                reqs.loc[m, "decision_date"] = pay_date
                text = f"Approved to buy on {pay_date:%d %b}"
                new = {"bill_no": item["id"], "supplier": f"Expense: {item['row']['item']}",
                       "amount": item["amount"], "issue_date": D["today"], "due_date": pay_date,
                       "status": "Scheduled" if day > 0 else "Paid", "pay_date": pay_date,
                       "category": item["row"]["category"] if pd.notna(item["row"]["category"]) else "Other",
                       "source": "Expense request",
                       "captured_by": item["row"]["submitted_by"], "repeat": "", "approved_by": actor()}
                bills = pd.concat([bills, pd.DataFrame([new])], ignore_index=True)
                ds.save_bills(bills)
                if day == 0:
                    S["cash_today"] = float(S["cash_today"]) - item["amount"]
                    ds.save_settings(S)
            reqs.loc[m, ["decision", "decision_reason", "decided_by"]] = [text, reason, actor()]
            reqs.loc[m, "risk_at_decision"] = f"{chosen_risk:.1%}" if chosen_risk is not None else ""
            ds.save_requests(reqs)
        risk_txt = f"risk {chosen_risk:.0%} ({lvl})" if chosen_risk is not None else "no payment"
        record("Decision", f"{item['id']}: {text}; {risk_txt}; reason: {reason or '-'}")
        st.success(f"Saved: {text}. Logged in the audit trail.")
        st.button("Continue")

elif page == "Invoices":
    tab1, tab2, tab3 = st.tabs(["Bills to pay", "Customers owe you", "Payment behaviour (actuarial)"])
    with tab1:
        b = D["bills"].copy().sort_values("due_date")
        b["amount"] = b["amount"].map(money)
        for c in ("due_date", "pay_date"):
            b[c] = b[c].dt.strftime("%d %b %Y").fillna("")
        b["repeat"] = b["repeat"].fillna("").replace({"monthly": "Monthly"})
        st.dataframe(b[["bill_no", "supplier", "amount", "due_date", "status", "pay_date", "repeat",
                        "source", "captured_by", "approved_by"]].fillna(""), hide_index=True,
                     use_container_width=True)
        sched = D["bills"][D["bills"]["status"] == "Scheduled"]
        if user["role"] == "Owner" and len(sched):
            with st.container(border=True):
                st.markdown("**Record a payment made**")
                st.caption("When the bank transfer for a scheduled bill has gone out, record it here. "
                           "The supplier gets a WhatsApp message that payment was made.")
                lab = [f"{r.bill_no} · {r.supplier} · {money(r.amount)} · scheduled {r.pay_date:%d %b}"
                       for r in sched.itertuples()]
                pick = st.selectbox("Scheduled bill", lab, key="paid_pick")
                if st.button("Mark as paid by transfer", type="primary"):
                    r = sched.iloc[lab.index(pick)]
                    bills = D["bills"].copy()
                    m = bills["bill_no"] == r["bill_no"]
                    bills.loc[m, "status"] = "Paid"
                    ds.save_bills(bills)
                    if r["pay_date"] <= D["today"]:
                        S["cash_today"] = float(S["cash_today"]) - float(r["amount"])
                        ds.save_settings(S)
                    record("Recorded payment", f"{r['bill_no']} {money(r['amount'])} paid by transfer on {r['pay_date']:%d %b %Y}")
                    tell_supplier("paid", r["bill_no"])
                    st.rerun()
        with st.expander("➕ Add a recurring monthly bill (rent, utilities, payroll, subscriptions)"):
            with st.form("recurring"):
                rname = st.text_input("Paid to", placeholder="e.g. Internet provider")
                ramt = st.number_input("Amount each month (RM)", 0.0, 1e7, 0.0, 10.0)
                rdue = st.date_input("Next due date", D["today"].date() + pd.Timedelta(days=7))
                rcat = st.selectbox("Type", ["Rent", "Utilities", "Payroll", "Subscription", "Loan", "Other"])
                if st.form_submit_button("Add recurring bill", type="primary"):
                    if rname.strip() and ramt > 0:
                        new = {"bill_no": f"REC-{len(D['bills']) + 1:03d}", "supplier": rname.strip(),
                               "amount": ramt, "issue_date": D["today"], "due_date": pd.Timestamp(rdue),
                               "status": "To pay", "pay_date": pd.NaT, "category": rcat,
                               "source": "Recurring", "captured_by": actor(), "repeat": "monthly",
                               "approved_by": ""}
                        ds.save_bills(pd.concat([D["bills"], pd.DataFrame([new])], ignore_index=True))
                        record("Added recurring bill", f"{rname} {money(ramt)} monthly from {rdue}")
                        st.success("Added. It now repeats every month in the forecast.")
                    else:
                        st.error("Please enter a name and an amount.")
    with tab2:
        rows = []
        for _, r in D["invoices"][D["invoices"]["paid_date"].isna()].iterrows():
            overdue = max(0, (D["today"] - r["due_date"]).days)
            delay = conditional_median(D["model"], r["customer"], overdue)
            m = D["model"].get(r["customer"], {})
            p_on_time, unpaid14 = m.get("p_on_time", 0), m.get("still_unpaid_14", 0)
            reliability = ("Reliable" if unpaid14 < 0.1 and p_on_time >= 0.3
                           else "Usually late" if unpaid14 >= 0.4 else "Unpredictable")
            rows.append({"Invoice": r["invoice_no"], "Customer": r["customer"],
                         "Amount": money(r["amount"]), "Due": f"{r['due_date']:%d %b}",
                         "Days overdue": overdue,
                         "Predicted pay date": f"{r['due_date'] + pd.Timedelta(days=round(delay)):%d %b}",
                         "Reliability": reliability})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("Predicted pay date = due date + the customer's typical delay, "
                   "learned from their past invoices (given how late it already is).")
    with tab3:
        fig = go.Figure()
        for c in sorted(D["model"]):
            days, surv = km_curve(D["invoices"], D["today"], c)
            fig.add_trace(go.Scatter(x=days, y=surv, name=c, line_shape="hv"))
        fig.update_layout(title="Kaplan-Meier: chance an invoice is still unpaid, by days after due date",
                          xaxis_title="Days after due date", yaxis_title="Still unpaid",
                          yaxis_tickformat=".0%", height=380, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)
        bt = backtest(D["invoices"], D["today"])
        st.markdown(f"**Model check (backtest):** trained on {bt['train_rows']} older invoices, tested on "
                    f"{bt['test_rows']} newer ones. Average error **{bt['model_error_days']:.1f} days** vs "
                    f"**{bt['naive_error_days']:.1f} days** if we assume everyone pays on the due date.")
        st.markdown("**Calibration check:** are the predicted chances honest? (older invoices predict the newer ones)")
        cal = calibration(D["invoices"], D["today"])
        cal["Predicted paid"] = cal["Predicted paid"].map("{:.0%}".format)
        cal["Actually paid"] = cal["Actually paid"].map("{:.0%}".format)
        st.dataframe(cal, hide_index=True, use_container_width=True)
        st.markdown("**Credibility weighting (Bühlmann):** customers with little history are blended with "
                    "the all-customer pattern.")
        any_m = next(iter(D["model"].values()))
        st.dataframe(pd.DataFrame([{"Customer": c, "Paid invoices": v["n"],
                                    "Weight on own history (Z)": f"{v['Z']:.0%}"} for c, v in D["model"].items()]),
                     hide_index=True, use_container_width=True)
        st.caption(f"Z = n / (n + K), with K = {any_m['K']:.2f} estimated from the data "
                   "(expected process variance ÷ variance of customer averages). A new customer starts at Z = 0.")

elif page == "What-if simulator":
    st.caption("Test 'what if' scenarios. Nothing here changes your data.")
    items = pending_items(D)
    names = ["No new spending"] + [i["label"] for i in items]
    choice = st.selectbox("Decision to test", names)
    c1, c2, c3 = st.columns(3)
    drop = c1.slider("Sales drop", 0, 50, 0, 5, format="%d%%")
    extra = c2.slider("Unexpected extra cost (RM)", 0, 2000, 0, 100)
    customers = sorted(D["model"])
    late_cust = c3.selectbox("Customer pays later than usual", ["Nobody"] + customers)
    late_days = c3.slider("Extra days late", 0, 30, 0, 1)
    what_if = {"sales_factor": 1 - drop / 100, "extra_cost": extra,
               "extra_delay": {late_cust: late_days} if late_cust != "Nobody" else {}}
    if choice == "No new spending":
        state = state_for(D)
        res = simulate(state, runs=int(S["simulations"]), **what_if)
        lvl, colour, _ = risk_level(res["risk"], S)
        st.markdown(f"Result: {badge(lvl, colour)} · {res['risk']:.0%} chance of going below reserve · "
                    f"bad-case lowest cash {money(res['worst5'])}")
        st.plotly_chart(fan_chart(state, res, "Cash in this scenario"), use_container_width=True)
    else:
        item = next(i for i in items if i["label"] == choice)
        state, ev, _ = evaluate_item(D, item, **what_if)
        st.dataframe(pd.DataFrame([{
            "Date": f"{o['date']:%a %d %b}", "Risk below reserve": f"{o['risk']:.1%}",
            "Level": o["level"], "Bad-case lowest cash": money(o["result"]["worst5"]),
            "Suggested": "✓" if o is ev["suggested"] else ""} for o in ev["options"]]),
            hide_index=True, use_container_width=True)
        st.plotly_chart(fan_chart(state, ev["today"]["result"], "If paid/spent today, in this scenario",
                                  compare=ev["suggested"]["result"],
                                  compare_label=f"Typical future if {ev['suggested']['date']:%d %b}"),
                        use_container_width=True)

elif page == "Impact test":
    st.caption("Does CashGuard really prevent cash shortfalls? 50 synthetic bill situations, each judged on "
               "300 fresh futures drawn from the hidden behaviour that generated the demo data (not the model's "
               "own assumptions). It uses the original demo bills, so the result is repeatable and does not "
               "change as you add bills in the demo.")
    if st.button("Run impact test", type="primary") or "impact" not in st.session_state:
        with st.spinner("Testing 50 situations..."):
            st.session_state.impact = run_impact(S, D["bills"][D["bills"]["captured_by"] == "System"], D["invoices"], D["sales"], D["model"], n=50)
    r = st.session_state.impact
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Shortfall rate - pay straight away", f"{r['breach_now']:.1%}")
    c2.metric("Shortfall rate - CashGuard date", f"{r['breach_cg']:.1%}")
    c3.metric("Fewer shortfalls", f"{r['reduction']:.0%}")
    c4.metric("Bills still paid on time", f"{r['paid_on_time']}/{r['n']}")
    st.markdown(f"Of **{r['risky_situations']}** risky situations (5%+ shortfall chance if paid straight away), "
                f"CashGuard brought **{r['risky_fixed']}** below 5% by choosing a better date. "
                f"It changed the pay date in {r['delayed']} of {r['n']} cases and never paid late.")
    t = r["table"].copy()
    for c in ("Breach rate - pay now", "Breach rate - CashGuard", "Predicted risk - pay now"):
        t[c] = t[c].map("{:.0%}".format)
    t["Cash today"] = t["Cash today"].map(money)
    t["Bill"] = t["Bill"].map(money)
    st.dataframe(t, hide_index=True, use_container_width=True)

elif page == "Audit log":
    st.caption("Append-only: entries can be added but never edited or deleted.")
    st.dataframe(audit.read(), hide_index=True, use_container_width=True)

elif page == "Settings":
    with st.form("settings"):
        reserve = st.number_input("Minimum cash reserve (RM)", 0, 100000, int(S["min_reserve"]), 100)
        low = st.slider("Low risk below", 1, 20, int(S["low_risk_limit"] * 100), format="%d%%")
        high = st.slider("High risk above", 5, 60, int(S["high_risk_limit"] * 100), format="%d%%")
        runs = st.select_slider("Simulated futures", [500, 1000, 2000, 5000], int(S["simulations"]))
        cash = st.number_input("Cash today (RM) - or upload a bank statement below",
                               0, 1000000, int(S["cash_today"]), 100)
        st.markdown("**Manager approval limits**")
        m1, m2 = st.columns(2)
        mlimit = m1.number_input("Max per bill or request (RM)", 0, 1000000,
                                 int(S.get("manager_approval_limit", 300)), 50,
                                 help="The Manager can decide items up to this amount. Larger items go to you.")
        mmonth = m2.number_input("Monthly approval limit (RM)", 0, 10000000,
                                 int(S.get("manager_monthly_limit", 1500)), 100,
                                 help="Total the Manager can approve in one month. After that, items go to you.")
        owner_wa = st.text_input("Owner's WhatsApp number (for the weekly summary)", S.get("owner_whatsapp", ""))
        biz_wa = st.text_input("Business WhatsApp number (the bot suppliers message)", S.get("business_whatsapp", ""))
        notify_on = st.checkbox("Send suppliers WhatsApp updates (received, approved with pay date, paid)",
                                S.get("notify_suppliers", True))
        if st.form_submit_button("Save settings", type="primary"):
            S.update({"min_reserve": reserve, "low_risk_limit": low / 100,
                      "high_risk_limit": high / 100, "simulations": runs, "cash_today": cash,
                      "manager_approval_limit": mlimit, "manager_monthly_limit": mmonth,
                      "owner_whatsapp": owner_wa, "business_whatsapp": biz_wa, "notify_suppliers": notify_on})
            ds.save_settings(S)
            record("Changed settings", f"reserve {money(reserve)}, low <{low}%, high >{high}%, "
                                       f"{runs} futures, cash {money(cash)}, manager limits {money(mlimit)} per item / "
                                       f"{money(mmonth)} per month")
            st.success("Saved.")
    st.divider()
    st.markdown("#### Bank statement (update cash today)")
    st.caption("Upload a CSV with columns: date, description, amount, balance. CashGuard uses the latest balance.")
    bank = st.file_uploader("Bank statement CSV", type=["csv"], key="bank_csv")
    if bank is not None:
        try:
            bdf = pd.read_csv(bank)
            bdf.columns = [c.strip().lower() for c in bdf.columns]
            bdf["date"] = pd.to_datetime(bdf["date"])
            last = bdf.sort_values("date").iloc[-1]
            st.dataframe(bdf.tail(8), hide_index=True, use_container_width=True)
            st.markdown(f"Latest balance on {last['date']:%d %b %Y}: **{money(float(last['balance']))}**")
            if st.button("Use this balance as cash today", type="primary"):
                S["cash_today"] = float(last["balance"])
                ds.save_settings(S)
                record("Updated cash from bank statement", f"{money(float(last['balance']))} as of {last['date']:%d %b %Y}")
                st.success("Cash today updated.")
        except Exception:
            st.error("Could not read the file. It needs columns: date, description, amount, balance.")
    st.divider()
    st.markdown("#### Share the invoice bot with suppliers")
    biz = S.get("business_whatsapp", "")
    if not biz:
        st.info("Add your business WhatsApp number above to get a link and QR code.")
    else:
        link = notify.share_link(biz)
        q1, q2 = st.columns([1, 2])
        png = notify.qr_png(link)
        q1.image(png, caption="Scan to send us an invoice", width=210)
        q1.download_button("Download QR code (PNG)", png, file_name="cashguard_invoice_qr.png", mime="image/png")
        sandbox = S.get("twilio_sandbox_code", "")
        msg = (f"Hi! From now on, please send your invoices to {S['business_name']} on WhatsApp: {biz}\n"
               f"Tap this link and press send: {link}\n"
               "You can send a photo/PDF of your invoice, or reply to our form and we'll create the invoice "
               "for you. We pay by online bank transfer and will update you on WhatsApp when it's approved "
               "and when it's paid.")
        if sandbox:
            msg += f"\n(Test mode: first send '{sandbox}' to this number.)"
        q2.markdown(f"**Link:** {link}")
        q2.caption("Print the QR code on purchase orders or at the receiving counter. "
                   "Send this message to each supplier:")
        q2.code(msg, language=None, wrap_lines=True)
        sb = q2.text_input("Twilio sandbox join code (hackathon only, optional)", sandbox, placeholder="join happy-tiger")
        if q2.button("Save join code"):
            S["twilio_sandbox_code"] = sb.strip()
            ds.save_settings(S)
            st.rerun()
    st.divider()
    st.markdown("#### Registered WhatsApp senders")
    st.caption("Invoices from these numbers are trusted. Unknown numbers are flagged for checking.")
    wa = pd.DataFrame(S.get("whatsapp_senders", []), columns=["number", "name", "type"])
    wa_edit = st.data_editor(wa, num_rows="dynamic", hide_index=True, use_container_width=True, key="wa_editor")
    if st.button("Save WhatsApp senders"):
        S["whatsapp_senders"] = [{"number": str(r["number"]), "name": str(r["name"]), "type": str(r["type"])}
                                 for _, r in wa_edit.dropna(subset=["number"]).iterrows()]
        ds.save_settings(S)
        record("Changed WhatsApp senders", f"{len(S['whatsapp_senders'])} registered numbers")
        st.success("Saved.")
    st.divider()
    st.markdown("#### Spending categories and staff limits")
    st.caption("Staff cannot submit a request above these limits. Monthly limit is per staff member, per category. "
               "Edit a cell, add a row for a new category, or select a row and delete it, then press Save limits.")
    cats = policy.categories(S)
    table = pd.DataFrame([{"Category": k, "Max per request (RM)": v["max_per_request"],
                           "Monthly limit per staff (RM)": v["monthly_limit"]} for k, v in cats.items()])
    edited = st.data_editor(table, num_rows="dynamic", hide_index=True, use_container_width=True,
                            key="limits_editor")
    if st.button("Save limits", type="primary"):
        new_cats, errs = {}, []
        for _, r in edited.dropna(subset=["Category"]).iterrows():
            name = str(r["Category"]).strip()
            if not name:
                continue
            mx, mo = float(r["Max per request (RM)"] or 0), float(r["Monthly limit per staff (RM)"] or 0)
            if name in new_cats:
                errs.append(f"'{name}' appears twice.")
            elif mx <= 0 or mo <= 0:
                errs.append(f"{name}: both limits must be above RM0.")
            elif mx > mo:
                errs.append(f"{name}: max per request ({money(mx)}) cannot be more than the monthly limit ({money(mo)}).")
            new_cats[name] = {"max_per_request": mx, "monthly_limit": mo}
        if errs:
            st.error("Not saved. " + " ".join(errs))
            st.stop()
        if "Other" not in new_cats:
            new_cats["Other"] = policy.DEFAULT_CATEGORIES["Other"]
        S["categories"] = new_cats
        ds.save_settings(S)
        record("Changed spending limits", "; ".join(
            f"{k}: {money(v['max_per_request'])}/request, {money(v['monthly_limit'])}/month" for k, v in new_cats.items()))
        st.success("Limits saved. Staff see the new limits on their next request.")
    st.divider()
    st.markdown("**Reset demo data** (restores the original synthetic data and clears logs)")
    if st.checkbox("I understand this resets everything") and st.button("Reset demo data"):
        generate(force=True)
        make_demo_invoices()
        st.session_state.risk_sent = set()
        st.success("Demo data reset.")

# ===========================================================================
# EMPLOYEE PAGES
# ===========================================================================
elif page == "Upload bill":
    st.caption("Invoices arrive on WhatsApp automatically, or you can upload one. AI reads it; you check it "
               "before it is saved. Cash and risk are only visible to the Owner and Manager.")
    tab_wa, tab_up = st.tabs([f"📥 From WhatsApp ({len(inbox.list_messages('New'))} new)", "⬆️ Upload a file"])
    with tab_wa:
        with st.expander("Demo: simulate a WhatsApp message (use this if live WhatsApp is not connected)"):
            demos = sorted(f for f in os.listdir(DEMO_DIR) if f.endswith(".png"))
            senders = S.get("whatsapp_senders", [])
            opts = [f"{x['name']} ({x['number']})" for x in senders] + ["Unknown number (+60111111111)"]
            c1, c2 = st.columns(2)
            demo_file = c1.selectbox("Invoice photo", demos, key="wa_demo_file")
            guess = next((i for i, x in enumerate(senders)
                          if x["name"].split()[0].lower() in demo_file.lower()), 0)
            who = c2.selectbox("Sent from", opts, index=guess)
            if st.button("Send as WhatsApp message"):
                number = (senders[opts.index(who)]["number"] if opts.index(who) < len(senders) else "+60111111111")
                with open(os.path.join(DEMO_DIR, demo_file), "rb") as f:
                    data = f.read()
                meta = inbox.save_incoming(data, "image/png", number, S, body="Invoice attached",
                                           channel="WhatsApp (demo simulator)", original_name=demo_file)
                ex = extract(demo_file, data)
                inbox.update(meta["id"], extraction=ex)
                reply = inbox.receipt_text(ex["fields"], S["business_name"])
                status = send_whatsapp(number, reply)
                audit.log("WhatsApp", "Invoice received", f"from {meta['sender_name']} {meta['sender']} "
                          f"({meta['channel']}); auto-reply {status}")
                st.session_state.flash = f"WhatsApp invoice received. Auto-reply to sender ({status}): \"{reply}\""
                st.rerun()
        with st.expander("Demo: supplier has no invoice - fills in the WhatsApp invoice form"):
            st.caption("The supplier types INVOICE. The bot replies with this form; they fill it in and send it "
                       "back, and CashGuard creates the invoice PDF for them. Blank lines get default values.")
            senders = S.get("whatsapp_senders", [])
            fopts = [f"{x['name']} ({x['number']})" for x in senders if x["type"] == "Supplier"]
            fwho = st.selectbox("Supplier", fopts, index=min(1, len(fopts) - 1), key="wa_form_sender")
            fnum = fwho.split("(")[-1].rstrip(")")
            st.markdown("**1. Bot sends the form**")
            st.code(wa_form.template_for(S, fnum), language=None)
            prof = wa_form.profile(S, fnum)
            sample = (f"Supplier name: {prof.get('supplier') or fwho.split(' (')[0]}\n"
                      "Invoice no (optional): \n"
                      "Item 1: Fresh milk 1L, 150, 4.20\n"
                      "Item 2 (optional): Whipping cream 1L, 10, 2.00\n"
                      "Item 3 (optional): \n"
                      "Due date (optional, DD/MM/YYYY): \n"
                      f"Bank name: {prof.get('bank', 'CIMB Bank')}\n"
                      f"Account name: {prof.get('account_name', 'Fresh Dairy Supply Sdn Bhd')}\n"
                      f"Account no: {prof.get('account_no', '8000-0000-5678')}\n"
                      "Notes (optional): Delivered 27 Oct")
            st.markdown("**2. Supplier fills it in and sends it back**")
            filled = st.text_area("Supplier's reply", sample, height=230, key=f"wa_form_text_{fnum}")
            if st.button("Send filled form", type="primary"):
                seq = 1 + sum(1 for m in inbox.list_messages() if m.get("channel", "").endswith("form"))
                res = wa_form.process_form(filled, fnum, S, D["today"], seq, os.path.join(ASSETS, "logo_navy_64.png"))
                if not res["ok"]:
                    st.error(res["reply"])
                else:
                    inv = res["invoice"]
                    meta = inbox.save_incoming(res["pdf"], "application/pdf", fnum, S, body=filled,
                                               channel="WhatsApp (demo simulator) - invoice form",
                                               original_name=f"{inv['invoice_no']}.pdf")
                    inbox.update(meta["id"], extraction=wa_form.extraction_from(inv), generated=True)
                    ds.save_settings(wa_form.remember_supplier(S, fnum, inv))
                    status = send_whatsapp(fnum, res["reply"])
                    audit.log("WhatsApp", "Invoice generated from form",
                              f"{inv['invoice_no']} for {inv['supplier']}, {money(inv['amount'])}; "
                              f"defaults: {', '.join(res['defaults'])}; reply {status}")
                    st.session_state.flash = f"Invoice {inv['invoice_no']} generated. Bot reply ({status}):\n\n{res['reply']}"
                    st.rerun()
        if st.session_state.get("flash"):
            st.success(st.session_state.pop("flash"))
        new_msgs = inbox.list_messages("New")
        if not new_msgs:
            st.info("No new WhatsApp invoices. Suppliers send them to the business WhatsApp number "
                    "(see whatsapp_webhook.py), or use the demo simulator above.")
        else:
            labels = [f"{m['received_at']} · {m['sender_name']} ({m['sender']})" for m in new_msgs]
            pick = st.selectbox("Message", labels, key="wa_pick")
            meta = new_msgs[labels.index(pick)]
            if not meta["known"]:
                st.warning("This number is not a registered supplier or staff member. Check the invoice carefully.")
            if meta.get("duplicate_of"):
                st.error("This exact file was already received before (possible duplicate).")
            data = inbox.read_file(meta)
            ci, cf = st.columns([1, 1])
            with ci:
                if meta["file"].endswith((".png", ".jpg")):
                    st.image(data, caption=f"WhatsApp message: {meta.get('body') or ''}", use_container_width=True)
                elif meta.get("generated"):
                    exm = meta.get("extraction", {})
                    pay = exm.get("payment", {})
                    st.markdown(f"**Invoice generated from WhatsApp form** · {meta['original_name']}")
                    st.markdown(f"Pay by online transfer to **{pay.get('bank', '')}** "
                                f"{pay.get('account_no', '')} ({pay.get('account_name', '')}). No cash needed.")
                    if exm.get("bank_changed"):
                        st.error("Bank details are different from this supplier's saved details. "
                                 "Call the supplier on a known number to verify before paying.")
                    st.download_button("Download invoice PDF", data, file_name=meta["original_name"],
                                       mime="application/pdf")
                    with st.expander("Supplier's WhatsApp message"):
                        st.code(meta.get("body", ""), language=None)
                if st.button("Not an invoice - dismiss", key="wa_dismiss"):
                    inbox.update(meta["id"], status="Dismissed")
                    record("Dismissed WhatsApp message", f"{meta['id']} from {meta['sender']}")
                    st.rerun()
            with cf:
                ex = meta.get("extraction") or extract(meta["original_name"], data)
                bill_no = confirm_invoice(meta["id"], meta["original_name"], data, ex, "WhatsApp",
                                          f"from {meta['sender_name']}")
                if bill_no:
                    inbox.update(meta["id"], status="Processed", bill_no=bill_no)
                    tell_supplier("submitted", bill_no)
                    st.session_state.flash = f"{bill_no} submitted for review."
                    st.rerun()
    with tab_up:
        src = st.radio("Invoice source", ["Use a demo invoice", "Upload a file"], horizontal=True)
        file_name, file_bytes = None, None
        if src == "Use a demo invoice":
            demos = sorted(f for f in os.listdir(DEMO_DIR) if f.endswith(".png"))
            file_name = st.selectbox("Demo invoice", demos)
            with open(os.path.join(DEMO_DIR, file_name), "rb") as f:
                file_bytes = f.read()
        else:
            up = st.file_uploader("Invoice image or PDF", type=["png", "jpg", "jpeg", "pdf"])
            if up:
                file_name, file_bytes = up.name, up.getvalue()
        if file_name:
            col_img, col_form = st.columns([1, 1])
            with col_img:
                if not file_name.lower().endswith(".pdf"):
                    st.image(file_bytes, caption=file_name, use_container_width=True)
            with col_form:
                if st.button("Read invoice", type="primary"):
                    st.session_state.extraction = {"file": file_name, **extract(file_name, file_bytes)}
                ex = st.session_state.extraction
                if ex and ex["file"] == file_name:
                    new_no = confirm_invoice("upload", file_name, file_bytes, ex, "Uploaded")
                    if new_no:
                        tell_supplier("submitted", new_no)
                        st.session_state.extraction = None
                        st.success("Submitted for review.")

elif page == "New expense request":
    cats = policy.categories(S)
    category = st.selectbox("Category - what is the money for?", list(cats))
    lim = policy.check(0, category, actor(), D["requests"], S, D["today"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Max per request", money(lim["max_per_request"]))
    c2.metric("Your monthly limit", money(lim["monthly_limit"]))
    c3.metric("Left this month", money(lim["left"]))
    c3.caption(f"Used {money(lim['used'])} so far in {D['today']:%B}")
    with st.form("request"):
        item = st.text_input("What is it?", placeholder="e.g. New coffee machine / Overtime meal allowance")
        amount = st.number_input("Amount (RM)", 0.0, 1e7, 0.0, 10.0)
        reason = st.text_area("Why is it needed?")
        needed = st.date_input("Needed by", D["today"].date() + pd.Timedelta(days=14),
                               min_value=D["today"].date())
        sent = st.form_submit_button("Submit request", type="primary")
    if sent:
        res = policy.check(amount, category, actor(), D["requests"], S, D["today"])
        if not item.strip() or amount <= 0:
            st.error("Please fill in what it is and an amount above RM0.")
        elif not res["ok"]:
            for msg in res["problems"]:
                st.error(msg)
            st.caption("Lower the amount, split it into another category if it truly belongs there, "
                       "or ask the Owner to raise the limit in Settings.")
            record("Request blocked by limit", f"{category}: {item} {money(amount)} - " + " ".join(res["problems"]))
        else:
            reqs = D["requests"]
            rid = f"REQ-{len(reqs) + 1:03d}"
            new = {"request_id": rid, "category": category, "item": item.strip(), "amount": amount,
                   "reason": reason, "needed_by": pd.Timestamp(needed),
                   "request_date": str(D["today"].date()), "submitted_by": actor(),
                   "submitted_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "status": "Pending"}
            ds.save_requests(pd.concat([reqs, pd.DataFrame([new])], ignore_index=True))
            record("Submitted expense request", f"{rid}: {category} - {item} {money(amount)}")
            st.success(f"Request {rid} submitted for Owner review. "
                       f"{money(res['left'] - amount)} left this month for {category}.")

elif page == "My submissions":
    me = actor()
    b = D["bills"][D["bills"]["captured_by"] == me]
    st.markdown("#### Bills I uploaded")
    if len(b):
        st.dataframe(pd.DataFrame({"Bill": b["bill_no"], "Supplier": b["supplier"],
                                   "Amount": b["amount"].map(money),
                                   "Due": b["due_date"].dt.strftime("%d %b"),
                                   "Status": b["status"]}), hide_index=True, use_container_width=True)
    else:
        st.caption("None yet.")
    r = D["requests"][D["requests"]["submitted_by"] == me]
    st.markdown("#### My expense requests")
    if len(r):
        st.dataframe(pd.DataFrame({"Request": r["request_id"], "Category": r["category"].fillna("Other"),
                                   "Item": r["item"],
                                   "Amount": r["amount"].map(money), "Status": r["status"],
                                   "Owner's note": r["decision"].fillna("")}),
                     hide_index=True, use_container_width=True)
    else:
        st.caption("None yet.")
    st.markdown("#### My activity")
    log = audit.read()
    st.dataframe(log[log["actor"] == me], hide_index=True, use_container_width=True)

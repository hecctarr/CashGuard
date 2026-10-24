"""
CashGuard Risk - actuarial cash-risk check for SMEs (hackathon demo)

Run:   pip install -r requirements.txt
       streamlit run app.py

All data is synthetic and fictional. Sign-in uses hashed passwords; each role sees only its own pages.
"""

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import audit
import auth
import data_store as ds
import help_text as H
import policy
from capture.extract import extract, checks, FALLBACK
from capture.make_demo_invoices import main as make_demo_invoices
from engine.explain import (baseline, chase_suggestion, evaluate_options, explain,
                            money, risk_level)
from engine.montecarlo import build_state, simulate
from engine.payments import backtest, calibration, conditional_median, train
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
LOGO_NAV = os.path.join(ASSETS, "logo_navy_64.png")
st.set_page_config(page_title="CashGuard Risk", page_icon=os.path.join(ASSETS, "logo_navy_64.png"), layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@500;600;700&display=swap');
:root { --cg-navy:#152846; --cg-navy-2:#1F3A66; --cg-sky:#EDF1F8; --cg-line:#E5E6EB; --cg-text:#1F2329;
        --cg-muted:#646A73; --cg-hover:#F2F3F5; --cg-bg:#F7F8FA; --cg-ease: cubic-bezier(.2,.8,.2,1); }
html, body, [class*="css"], .stMarkdown, button, input, textarea { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], #MainMenu, [data-testid="stDecoration"], footer { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stMainBlockContainer"] { padding-top: 1.6rem; max-width: 1180px; }

/* ---------- Sidebar (Lark-like: white, grouped, quiet) ---------- */
[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid var(--cg-line); }
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: .6rem; }
[data-testid="stSidebarHeader"] { height: 2.2rem; padding-bottom: 0; }
.cg-ws { display:flex; gap:10px; align-items:center; padding: 8px 8px 12px; margin-bottom: 4px;
         border-bottom: 1px solid var(--cg-line); }
.cg-ws-av, .cg-me-av { flex: 0 0 auto; width: 36px; height: 36px; border-radius: 10px; display:grid; place-items:center;
         background: linear-gradient(135deg, #152846, #3B5C94); color:#fff; font-weight:700; font-size:.9rem;
         box-shadow: 0 4px 10px rgba(21,40,70,.18); }
.cg-ws b { display:block; color: var(--cg-text); font-size: .95rem; line-height:1.2; }
.cg-ws span { color: var(--cg-muted); font-size: .76rem; }
.cg-sec { color:#8F959E; font-size:.7rem; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
          margin: 14px 10px 4px; }
[data-testid="stSidebar"] [data-testid="stPageLink"] { margin: 0 !important; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
    position: relative; border-radius: 8px; padding: 6px 10px; margin: 1px 0;
    transition: background .18s var(--cg-ease), transform .18s var(--cg-ease), color .18s; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { background: var(--cg-hover); transform: translateX(3px); }
[data-testid="stSidebar"] [data-testid="stPageLink"] a span[data-testid="stIconMaterial"] { transition: transform .25s var(--cg-ease); color:#646A73; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover span[data-testid="stIconMaterial"] { transform: scale(1.15); }
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"],
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] { background: var(--cg-sky); }
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] p { color: var(--cg-navy); font-weight: 650; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] span[data-testid="stIconMaterial"] { color: var(--cg-navy); }
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"]::before {
    content:""; position:absolute; left:-6px; top:8px; bottom:8px; width:3px; border-radius:3px; background: var(--cg-navy);
    animation: cgBar .35s var(--cg-ease); }
@keyframes cgBar { from { transform: scaleY(0); } to { transform: scaleY(1); } }
.cg-grow { height: 28px; }
.st-key-cg_me { border-top: 1px solid var(--cg-line); padding-top: 12px; }
.cg-me { display:flex; gap:10px; align-items:center; padding: 0 6px 6px; }
.cg-me-av { border-radius: 50%; width: 34px; height: 34px; background: linear-gradient(135deg,#2F9E6E,#3B6FC4); }
.cg-me b { display:block; font-size:.88rem; color: var(--cg-text); }
.cg-role { display:inline-block; font-size:.7rem; font-weight:600; padding: 1px 8px; border-radius: 999px; margin-top:2px; }
.cg-role-Owner { background:#E8EDF5; color:#152846; } .cg-role-Manager { background:#FFF3DC; color:#9A6100; }
.cg-role-Employee { background:#E7F6EE; color:#1E7A4C; }
.st-key-cg_me button { border: none; background: transparent; color: var(--cg-muted); justify-content:flex-start; padding-left: 10px; }
.st-key-cg_me button > div { justify-content: flex-start; }
.st-key-cg_me button:hover { background: #FDECEA; color: #B42318; }

/* ---------- Page header + seamless help ---------- */
.cg-crumb { color:#8F959E; font-size:.8rem; margin-bottom: 2px; }
.cg-crumb span { margin: 0 4px; color:#C9CDD4; } .cg-crumb b { color: var(--cg-muted); font-weight:500; }
.st-key-cg_head [data-testid="stHorizontalBlock"] { gap: .5rem; justify-content: flex-start; flex-wrap: nowrap; }
.st-key-cg_head [data-testid="stColumn"] { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
.cg-title { margin: 0 !important; padding: 0 !important; color: var(--cg-text); font-weight: 750; letter-spacing:-.02em; font-size: 1.75rem; }
.st-key-cg_head [data-testid="stPopover"] button {
    border: 1px solid transparent; background: transparent; color: #8F959E; border-radius: 999px;
    padding: 2px 10px; min-height: 30px; font-size: .82rem; transition: all .2s var(--cg-ease); }
.st-key-cg_head [data-testid="stPopover"] button:hover { background: var(--cg-sky); color: var(--cg-navy); border-color: #D5DDEA; }
.st-key-cg_head [data-testid="stPopover"] button [data-testid="stIconMaterial"] { transition: transform .35s var(--cg-ease); }
.st-key-cg_head [data-testid="stPopover"] button:hover [data-testid="stIconMaterial"] { transform: rotate(-12deg) scale(1.1); }
.st-key-cg_head [data-testid="stPopoverButton"] [data-testid="stIconMaterial"],
.st-key-cg_chat [data-testid="stPopoverButton"] [data-testid="stIconMaterial"] { display:none; }   /* no dropdown chevron */
[data-testid="stPopoverBody"] { border-radius: 14px !important; box-shadow: 0 12px 32px rgba(31,35,41,.14) !important;
    border: 1px solid var(--cg-line) !important; max-width: 460px; animation: cgPop .22s var(--cg-ease); }
@keyframes cgPop { from { opacity:0; transform: translateY(-6px) scale(.98); } to { opacity:1; transform:none; } }
.st-key-cg_maths { background: var(--cg-bg); border-radius: 10px; padding: 10px 12px; }
.cg-sub { color: var(--cg-muted); margin: 2px 0 14px; font-size: .95rem; }

/* ---------- Motion: content eases in ---------- */
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] > div { animation: cgIn .38s var(--cg-ease) both; }
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] > div:nth-child(2) { animation-delay: .03s; }
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] > div:nth-child(3) { animation-delay: .06s; }
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] > div:nth-child(4) { animation-delay: .09s; }
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] > div:nth-child(5) { animation-delay: .12s; }
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] > div:has(> .st-key-cg_chat) { animation: none !important; transform: none !important; }
@keyframes cgIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { *, *::before { animation: none !important; transition: none !important; } }

/* ---------- Cards, metrics, buttons ---------- */
h1, h2, h3, h4 { color: var(--cg-text); letter-spacing: -0.01em; }
[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid var(--cg-line); border-radius: 12px; padding: 14px 16px;
    transition: transform .2s var(--cg-ease), box-shadow .2s var(--cg-ease); }
[data-testid="stMetric"]:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(31,35,41,.08); }
[data-testid="stMetricLabel"] p { color: var(--cg-muted); font-weight: 500; }
[data-testid="stMetricValue"] { color: var(--cg-text); font-variant-numeric: tabular-nums; font-weight: 700; }
[data-testid="stMetricValue"] div, [data-testid="stMetricLabel"] div, [data-testid="stMetricLabel"] p {
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }
[data-testid="stMetricValue"] { font-size: clamp(1.3rem, 2.1vw, 2rem); }
div[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"] details { border-radius: 12px; border-color: var(--cg-line); background:#fff; }
[data-testid="stExpander"] summary:hover { color: var(--cg-navy); }
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
    border-radius: 8px; transition: transform .12s var(--cg-ease), box-shadow .2s, background .2s; }
.stButton button:hover { box-shadow: 0 4px 12px rgba(21,40,70,.10); }
.stButton button:active, [data-testid="stFormSubmitButton"] button:active { transform: scale(.97); }
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [aria-selected="true"] { color: var(--cg-navy) !important; }
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
.st-key-cg_chat { position: fixed !important; right: 26px; bottom: 22px; z-index: 999; width: auto !important; }
.st-key-cg_chat [data-testid="stPopover"] > div > button, .st-key-cg_chat button {
    background: var(--cg-navy); color: #fff; border: none; border-radius: 999px; padding: 10px 18px;
    box-shadow: 0 10px 26px rgba(21,40,70,.30); animation: cgBob 1.6s ease-in-out 3; }
.st-key-cg_chat button:hover { background: var(--cg-navy-2); color:#fff; }
.st-key-cg_chat button p, .st-key-cg_chat button span { color: #fff !important; }
@keyframes cgBob { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
.cg-chip { display:inline-block; border:1px solid var(--cg-line); border-radius:999px; padding: 4px 12px; margin: 3px 4px 3px 0;
           font-size:.85rem; color: var(--cg-muted); background: var(--cg-bg); }

/* ---------- Dashboard pieces ---------- */
.cg-brand { display:flex; align-items:center; gap:14px; margin: 4px 0 6px; }
.cg-brand b { font-size: 1.9rem; color: var(--cg-navy); letter-spacing: -0.02em; }
.cg-brand span { display:block; color:#5A6785; font-size: .95rem; }
.cg-status { border-radius: 14px; padding: 18px 22px; display:flex; gap: 22px; align-items:center; margin: 6px 0 4px;
             animation: cgIn .45s var(--cg-ease) both; }
.cg-status .pct { font-size: 3.2rem; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.cg-status .lvl { font-weight: 700; font-size: 1.05rem; margin-bottom: 4px; }
.cg-status .msg { font-size: 1.02rem; color:#1d2a40; }
.cg-High { background:#FDECEA; border:1px solid #F3B8B1; } .cg-High .pct, .cg-High .lvl { color:#B42318; }
.cg-High .pct { animation: cgPulse 2.4s ease-in-out infinite; }
@keyframes cgPulse { 0%,100% { text-shadow: 0 0 0 rgba(217,45,32,0); } 50% { text-shadow: 0 0 18px rgba(217,45,32,.35); } }
.cg-Medium { background:#FFF6E0; border:1px solid #F4D58D; } .cg-Medium .pct, .cg-Medium .lvl { color:#9A6100; }
.cg-Low { background:#E7F6EE; border:1px solid #A8DCC0; } .cg-Low .pct, .cg-Low .lvl { color:#1E7A4C; }
.cg-row { border-left: 4px solid; border-radius: 10px; padding: 9px 14px; background:#fff; margin: 3px 0;
          border-top:1px solid var(--cg-line); border-right:1px solid var(--cg-line); border-bottom:1px solid var(--cg-line);
          transition: transform .18s var(--cg-ease), box-shadow .18s; }
.cg-row:hover { transform: translateX(3px); box-shadow: 0 6px 16px rgba(31,35,41,.06); }
.cg-row small { display:block; font-weight:700; letter-spacing:.04em; text-transform: uppercase; font-size:.7rem; }
.cg-act { border-left-color:#D92D20; } .cg-act small { color:#B42318; }
.cg-chase { border-left-color:#F0B429; } .cg-chase small { color:#9A6100; }
.cg-fyi { border-left-color:#3B6FC4; } .cg-fyi small { color:#2B5BA8; }
.cg-steps { display:flex; gap:10px; flex-wrap:wrap; background: var(--cg-sky); border-radius: 12px; padding: 10px 14px; margin-bottom: 8px; }
.cg-steps span { background:#fff; border:1px solid #D5DDEA; border-radius: 999px; padding: 4px 12px; font-weight:600; color: var(--cg-navy); }
.cg-steps i { align-self:center; color:#5A6785; font-style: normal; }
.cg-card { border:1px solid var(--cg-line); border-radius: 14px; padding: 16px 18px; background:#fff; height:100%;
           transition: transform .2s var(--cg-ease), box-shadow .2s; }
.cg-card:hover { transform: translateY(-2px); box-shadow: 0 10px 24px rgba(31,35,41,.08); }
.cg-card h4 { margin: 0 0 6px; } .cg-card .big { font-size: 2rem; font-weight: 800; }
.cg-best { border: 2px solid #2F9E6E; background: #F3FBF7; }
.cg-card h4 { font-size: .9rem; color: var(--cg-muted); font-weight: 600; } .cg-card { color: var(--cg-muted); font-size: .9rem; }
.cg-card .big { color: var(--cg-text); margin: 2px 0 4px; }
.cg-tone-High { border-top: 4px solid #D92D20; } .cg-tone-Medium { border-top: 4px solid #F0B429; } .cg-tone-Low { border-top: 4px solid #2F9E6E; }

.cg-sbrand { display:flex; align-items:center; gap:9px; padding: 0 8px 10px; }
.cg-sbrand .ic { height:24px; width:auto; flex:none; } .cg-sbrand .wm { width:132px; max-width:calc(100% - 40px); height:auto; }
/* ---------- Sign-in / set-up (same look as the CashGuard banner) ---------- */
.cg-intro { display:flex; flex-direction:column; gap:14px; padding-top: 6vh; }
.cg-brandline { display:flex; align-items:center; gap:18px; }
.cg-brandline .tile { width:64px; height:64px; border-radius:16px; box-shadow:0 10px 24px rgba(21,40,70,.18); }
.cg-brandline .wm { height:21px; width:auto; }
.cg-hl > div { white-space:nowrap; }
.cg-hl { font-family:'Outfit','Inter',sans-serif; font-size:clamp(2rem,3.6vw,3.4rem); line-height:1.05; letter-spacing:-.025em;
         font-weight:700; color:#1F2329; display:flex; flex-direction:column; align-items:flex-start; gap:4px; margin:0; isolation:isolate; }
.cg-hl .w { position:relative; color:#fff; font-weight:600; padding:2px 6px; margin-left:-6px; z-index:0; }
.cg-hl .w::before { content:""; position:absolute; inset:-35% -18%; z-index:-1; border-radius:50%; filter:blur(18px);
         background: radial-gradient(closest-side, #3550F5, #8A4FE6 60%, transparent); }
.cg-tag { font-family:'Outfit','Inter',sans-serif; font-weight:600; font-size:1.15rem; color:#1F2329; margin:0; }
.cg-stack { color:#646A73; font-weight:600; font-size:.9rem; margin:0; }
.cg-feat { list-style:none; padding:0 !important; margin:4px 0 0 !important; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px 16px; color:#1F2329; font-size:.92rem; }
.cg-feat li { margin:0 !important; padding:0 !important; }
.cg-feat li::before { content:"✓"; color:#3550F5; font-weight:800; margin-right:8px; }
.st-key-cg_login { background: rgba(255,255,255,.74); -webkit-backdrop-filter: blur(18px); backdrop-filter: blur(18px);
    border:1px solid rgba(255,255,255,.8); border-radius: 22px; padding: 26px 26px 18px; box-shadow: 0 24px 60px rgba(60,40,140,.18); margin-top: 8vh; }
.st-key-cg_login [data-testid="stFormSubmitButton"] button { background: linear-gradient(90deg,#152846,#2C3FB8); border:0; color:#fff; }

</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# First run: create synthetic data + demo invoices
# ---------------------------------------------------------------------------
generate()
if not os.path.exists(FALLBACK):
    make_demo_invoices()
DEMO_DIR = os.path.join(ds.BASE, "demo_invoices")

PAGES = auth.PAGES
ICON = {"Dashboard": ":material/space_dashboard:", "Review & decide": ":material/fact_check:",
        "Invoices": ":material/receipt_long:", "What-if simulator": ":material/tune:",
        "Does it work? (Test)": ":material/science:", "Upload bill": ":material/upload_file:",
        "Audit log": ":material/history:", "Settings": ":material/settings:",
        "New expense request": ":material/add_card:", "My submissions": ":material/inbox:"}
SLUG = {"Dashboard": "dashboard", "Review & decide": "review", "Invoices": "invoices",
        "What-if simulator": "what-if", "Does it work? (Test)": "test", "Upload bill": "upload",
        "Audit log": "audit", "Settings": "settings", "New expense request": "request",
        "My submissions": "my-submissions"}
SECTIONS = [("Home", ["Dashboard"]),
            ("Money", ["Review & decide", "Invoices", "What-if simulator"]),
            ("Bills in", ["Upload bill", "New expense request", "My submissions"]),
            ("Trust", ["Does it work? (Test)", "Audit log"]),
            ("Admin", ["Settings"])]
SECTION_OF = {p: sec for sec, ps in SECTIONS for p in ps}
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


EMOJI = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}


def badge(level: str, colour: str) -> str:
    return f"{EMOJI.get(level, '')} :{COLOUR[colour]}[**{level} risk**]"


def fdate(d) -> str:
    """'Sun 1 Nov' everywhere."""
    d = pd.Timestamp(d)
    return f"{d:%a} {d.day} {d:%b}"


def risk_tag(risk: float, digits: int = 0) -> str:
    """'🔴 22% High risk' - the label always sits next to the %."""
    lvl = risk_level(risk, S)[0]
    return f"{EMOJI[lvl]} {risk * 100:.{digits}f}% {lvl} risk"


def go_to(page: str, **state):
    """Button callback: jump to another page (only if this role may open it)."""
    if auth.can_open(st.session_state.user["role"], page):
        st.session_state.goto = page
        st.session_state.update(state)


def page_header(page: str):
    """Lark-style header: breadcrumb, title, one-line purpose and a quiet help button."""
    title, what, maths = H.PAGE_HELP.get(page, (page, "", ""))
    st.markdown(f'<div class="cg-crumb">{S["business_name"]} <span>/</span> {SECTION_OF.get(page, "")} '
                f'<span>/</span> <b>{page}</b></div>', unsafe_allow_html=True)
    with st.container(key="cg_head"):
        c1, c2 = st.columns([1, 1], vertical_alignment="center")
        c1.markdown(f'<h2 class="cg-title">{page}</h2>', unsafe_allow_html=True)
        with c2.popover(":material/help: Help", help="What is this page? How does it work?"):
            st.markdown(f"#### {title}")
            st.markdown(what)
            if maths:
                with st.container(key="cg_maths"):
                    st.markdown("**:material/function: The maths behind it, in plain words**")
                    st.caption(maths)
            with st.expander(":material/menu_book: Words used in CashGuard"):
                for v in H.GLOSSARY.values():
                    st.markdown(v)
    st.markdown(f'<div class="cg-sub">{title}</div>', unsafe_allow_html=True)


def cg_chart(fig, **kw):
    """Charts without the floating toolbar, with a gentle fade-in."""
    kw.setdefault("use_container_width", True)
    return st.plotly_chart(fig, config={"displayModeBar": False}, **{k: v for k, v in kw.items()
                                                                   if k != "use_container_width"},
                           use_container_width=kw["use_container_width"])


def danger_window(state, res):
    """Days where the bad-case (bottom 5%) cash is below the safety cushion."""
    days = [i for i in range(state.horizon) if res["p5"][i] < state.reserve]
    return (days[0], days[-1]) if days else None


def chart_title(state, res, verb="") -> str:
    win = danger_window(state, res)
    if not win:
        return f"Your cash stays above the safety line for the next {state.horizon} days{verb}"
    a, b = state.day_to_date(win[0]), state.day_to_date(win[1])
    span = f"{a.day} {a:%b}" if win[0] == win[1] else (
        f"{a.day} to {b.day} {b:%b}" if a.month == b.month else f"{a.day} {a:%b} to {b.day} {b:%b}")
    low = min(res["p50"])
    word = "drops below" if low < state.reserve else "dips close to"
    return f"Your cash {word} the safety line around {span}{verb}"


def fan_chart(state, res, title, compare=None, compare_label=""):
    x = [state.day_to_date(i) for i in range(state.horizon)]
    fig = go.Figure()
    top = max(max(res["p95"]), state.reserve * 2)
    win = danger_window(state, res)
    fig.add_hrect(y0=min(0, min(res["p5"])), y1=state.reserve, fillcolor="rgba(217,45,32,0.07)", line_width=0)
    if win:
        fig.add_vrect(x0=x[win[0]] - pd.Timedelta(hours=12), x1=x[win[1]] + pd.Timedelta(hours=12),
                      fillcolor="rgba(217,45,32,0.10)", line_width=0,
                      annotation_text="Risk zone", annotation_position="top left",
                      annotation_font_color="#B42318")
    fig.add_trace(go.Scatter(x=x, y=res["p95"], line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=res["p5"], fill="tonexty", line=dict(width=0),
                             fillcolor="rgba(21,40,70,0.12)",
                             name="Where cash will likely stay (9 times out of 10)"))
    fig.add_trace(go.Scatter(x=x, y=res["p50"], name="Most likely cash path",
                             line=dict(color="#152846", width=2.5)))
    if compare is not None:
        fig.add_trace(go.Scatter(x=x, y=compare["p50"], name=compare_label,
                                 line=dict(color="#2F9E6E", width=2.5, dash="dash")))
    fig.add_hline(y=state.reserve, line=dict(color="#C0392B", dash="dot"),
                  annotation_text=f"Safety cushion: {money(state.reserve)}",
                  annotation_position="bottom right", annotation_font_color="#B42318")
    # Mark the big bills so the dips make sense
    k = 0
    for d, names in sorted(state.bill_labels.items()):
        amt = state.fixed_out[d]
        if amt >= 1000 and d < state.horizon:
            k += 1
            name = names[0].split(" (")[0].replace(" Sdn Bhd", "")
            fig.add_vline(x=x[d], line=dict(color="#8A94A8", width=1, dash="dot"))
            fig.add_annotation(x=x[d], y=top, text=f"{name} −{money(amt)}", showarrow=False,
                               yshift=4 if k % 2 else -16, font=dict(size=11, color="#3D4A63"), textangle=0,
                               bgcolor="rgba(255,255,255,.85)")
    fig.update_layout(title=title, height=400, margin=dict(l=10, r=10, t=60, b=10),
                      yaxis_title="Cash (RM)", legend=dict(orientation="h", y=-0.15),
                      plot_bgcolor="#FFFFFF", yaxis=dict(gridcolor="#EEF1F6"),
                      xaxis=dict(tickformat="%a %-d %b"))
    return fig


def pending_items(d):
    items = []
    for _, b in d["bills"][d["bills"]["status"] == "Awaiting review"].iterrows():
        items.append({"id": b["bill_no"], "kind": "bill", "label":
                      f"Bill {b['bill_no']} · {b['supplier']} · {money(b['amount'])} · due {fdate(b['due_date'])}",
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


def manager_used_this_month(d, who=None) -> float:
    """What the Manager has already approved this month (bills scheduled/paid + requests approved)."""
    who = who or actor()
    month = d["today"].to_period("M")
    used = 0.0
    b = d["bills"]
    if "approved_by" in b.columns:
        mb = b[(b["approved_by"].astype(str) == who) & b["status"].isin(["Paid", "Scheduled"])]
        used += float(mb[pd.to_datetime(mb["pay_date"]).dt.to_period("M") == month]["amount"].sum()) if len(mb) else 0.0
    r = d["requests"]
    if len(r):
        mr = r[(r["decided_by"].astype(str) == who) & (r["status"] == "Approved")]
        if len(mr):
            used += float(mr[pd.to_datetime(mr["decision_date"]).dt.to_period("M") == month]["amount"].sum())
    return used


def submitted_by(item) -> str:
    r = item["row"]
    return str(r.get("captured_by") if item["kind"] == "bill" else r.get("submitted_by"))


def calendar_rows(d, state):
    """Next 30 days: money out (bills) and money in (customers), with the cash left after each."""
    rule = rule_check(state)
    rows = []
    for _, b in d["bills"][d["bills"]["status"].isin(["To pay", "Scheduled", "On hold", "Awaiting review"])].iterrows():
        when = b["pay_date"] if pd.notna(b["pay_date"]) else b["due_date"]
        day = max(0, (when - d["today"]).days)
        if day < state.horizon:
            status = {"Awaiting review": "Waiting for your decision"}.get(b["status"], b["status"])
            rows.append({"day": day, "Type": "Money out", "Name": b["supplier"], "Amount": -float(b["amount"]),
                         "Status": status})
    for r in state.receivables:
        delay = conditional_median(d["model"], r.customer, r.overdue)
        day = max(1, int(round(r.due_day + delay)))
        if day < state.horizon:
            rows.append({"day": day, "Type": "Money in", "Name": f"{r.customer} {r.invoice_no}",
                         "Amount": r.amount, "Status": f"due {fdate(state.day_to_date(r.due_day))}, "
                         f"expected ~{delay:.0f} days late" if delay >= 3 else
                         f"due {fdate(state.day_to_date(r.due_day))}"})
    rows.sort(key=lambda x: (x["day"], x["Type"]))
    for x in rows:
        x["Date"] = fdate(state.day_to_date(x["day"]))
        x["cash"] = float(rule["path"][x["day"]])
        x["Cash left after this"] = money(x["cash"])
        x["Amount"] = ("+" if x["Amount"] > 0 else "−") + money(abs(x["Amount"]))
    df = pd.DataFrame(rows, columns=["Date", "Type", "Name", "Amount", "Status", "Cash left after this", "cash"])
    return df


def styled_calendar(df, reserve):
    def colour(row):
        if row["cash"] < reserve:
            c = "background-color:#FDECEA;color:#8A1C12;font-weight:600"
        elif row["Type"] == "Money in":
            c = "background-color:#E7F6EE;color:#165C39"
        else:
            c = ""
        return [c] * len(row)
    return df.style.apply(colour, axis=1)


def attention(d, state, base):
    """Everything worth knowing, grouped: ('act'|'chase'|'fyi', title, detail, action)."""
    out = []
    for it in pending_items(d):
        _, ev, _ = evaluate_item(d, it)
        t, sug = ev["today"], ev["suggested"]
        name = it["row"]["supplier"] if it["kind"] == "bill" else it["row"]["item"]
        group = "act" if t["level"] != "Low" else "fyi"
        detail = (f"Paying today: {risk_tag(t['risk'])}, could leave you at about "
                  f"{money(t['result']['typical_low'])}.")
        if sug["day"] != t["day"]:
            detail += f" Safest: {fdate(sug['date'])} ({risk_tag(sug['risk'])})."
        out.append((group, f"{name} · {money(it['amount'])}", detail, ("Review", it["label"])))
    for r in sorted(state.receivables, key=lambda r: -r.amount):
        delay = conditional_median(d["model"], r.customer, r.overdue)
        if delay >= 7 and r.amount >= 1000:
            out.append(("chase", f"{r.customer} owes {money(r.amount)}",
                        f"Usually pays ~{delay:.0f} days late. A friendly reminder now could bring it in "
                        f"before your big bills.", ("Draft reminder", r)))
        elif delay >= 3:
            out.append(("fyi", f"{r.customer} · {money(r.amount)}",
                        f"Likely to pay ~{delay:.0f} days late. Already counted in your forecast.", None))
    for day in range(0, 8):
        for name in state.bill_labels.get(day, []):
            out.append(("fyi", f"{name} due {fdate(state.day_to_date(day))}",
                        f"Cash left after it (most likely): {money(base['rule']['path'][day])}.", None))
    new_wa = inbox.list_messages("New")
    if new_wa:
        out.append(("fyi", f"{len(new_wa)} invoice(s) arrived on WhatsApp",
                    "Someone needs to check the details before they count.", ("Review invoices", len(new_wa))))
    order = {"act": 0, "chase": 1, "fyi": 2}
    return sorted(out, key=lambda x: order[x[0]])


def weekly_summary(d, state, base, items) -> str:
    lvl = risk_level(base["mc"]["risk"], d["settings"])[0]
    due7 = sum(state.fixed_out[:7])
    owed = sum(r.amount for r in state.receivables)
    return (f"CashGuard weekly summary - {d['settings']['business_name']}\n"
            f"Cash today: {money(d['settings']['cash_today'])}\n"
            f"Bills due in 7 days: {money(due7)}\n"
            f"Customers owe you: {money(owed)}\n"
            f"Chance of running short (30 days): {EMOJI[lvl]} {base['mc']['risk']:.0%} {lvl} risk\n"
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
# FIRST-RUN SET-UP, then SIGN-IN (username + password)
# ---------------------------------------------------------------------------
def b64(path: str) -> str:
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def gate_theme():
    """Sign-in and set-up pages: soft blue / violet / pink glow and the big shield, like the CashGuard banner."""
    st.markdown(f"""<style>
    .stApp {{ background:
        radial-gradient(38% 42% at 80% 14%, rgba(245,154,216,.75), transparent 70%),
        radial-gradient(34% 40% at 98% 55%, rgba(185,166,247,.8), transparent 70%),
        radial-gradient(30% 36% at 62% 82%, rgba(138,79,230,.55), transparent 72%),
        radial-gradient(34% 40% at 10% 95%, rgba(53,80,245,.6), transparent 70%), #F6F7FB !important; }}
    .stApp::after {{ content:""; position:fixed; right:-60px; bottom:-40px; width:min(440px,40vw); height:min(600px,55vw);
        background:url("data:image/png;base64,{b64(os.path.join(ASSETS, "shield_white.png"))}") no-repeat right bottom / contain;
        opacity:.6; pointer-events:none; z-index:0; }}
    [data-testid="stMainBlockContainer"] {{ position:relative; z-index:1; max-width: 1100px; }}
    </style>""", unsafe_allow_html=True)


def brand_intro(note: str = "") -> str:
    return (f'<div class="cg-intro"><div class="cg-brandline"><img class="tile" src="data:image/png;base64,{b64(os.path.join(ASSETS, "icon_tile.png"))}">'
            f'<img class="wm" src="data:image/png;base64,{b64(os.path.join(ASSETS, "wordmark_black.png"))}" alt="CashGuard"></div>'
            '<div class="cg-hl"><div>Know it\'s safe</div><div class="w">Before you pay</div></div>'
            '<p class="cg-tag">Actuarial cash-safety check for small businesses.</p>'
            '<p class="cg-stack">WhatsApp bot · Streamlit dashboard · Python risk engine</p>'
            '<ul class="cg-feat"><li>Your chance of running short, in one number</li><li>The safest pay date that is still on time</li>'
            '<li>Invoices straight from WhatsApp</li><li>Staff only see what their role allows</li></ul>'
            f'<p class="cg-stack" style="font-weight:500;font-size:.8rem">{note}</p></div>')


S0 = ds.load_settings()
if not S0.get("setup_done") or not S0.get("business_name"):
    # FIRST RUN: the owner sets up the business before anyone signs in
    gate_theme()
    left, mid = st.columns([0.95, 1.15], gap="large")
    left.markdown(brand_intro("First run · fictional demo data"), unsafe_allow_html=True)
    with mid, st.container(key="cg_login"):
        st.markdown("### Set up your business")
        st.caption("One minute. You can change all of this later in Settings.")
        with st.form("setup"):
            name = st.text_input("Business name *", placeholder="e.g. Kedai Kopi Aminah")
            addr = st.text_input("Business address (shown on invoices)", placeholder="Street, postcode, city")
            c1, c2 = st.columns(2, vertical_alignment="bottom")
            biz_wa = c1.text_input("Business WhatsApp", placeholder="+60 1x-xxx xxxx",
                                   help="Optional. The number suppliers send invoices to (the invoice bot). "
                                        "Leave blank to use the demo simulator.")
            own_wa = c2.text_input("Owner's WhatsApp", placeholder="+60 1x-xxx xxxx",
                                   help="Optional. Gets the weekly cash summary.")
            c3, c4, c5 = st.columns(3, vertical_alignment="bottom")
            cash = c3.number_input("Cash today (RM)", 0, 10_000_000, int(S0.get("cash_today", 5500)), 100,
                                   help="How much is in the business bank account today.")
            reserve = c4.number_input("Safety cushion", 0, 10_000_000, int(S0.get("min_reserve", 2000)), 100,
                                      help="In RM. The minimum cash you always want to keep. Going below it counts as running short.")
            terms = c5.number_input("Terms (days)", 1, 120, int(S0.get("default_payment_terms", 30)), 1,
                                    help="Supplier payment terms: how many days suppliers usually give you to pay.")
            st.caption("To let you explore straight away, CashGuard starts with sample bills, customers and sales "
                       "(fictional). Real use would connect your own data.")
            go = st.form_submit_button("Save and continue", type="primary", use_container_width=True)
        if go:
            if not name.strip():
                st.error("Please enter your business name.")
            else:
                S0.update({"business_name": name.strip(), "business_address": addr.strip(),
                           "business_whatsapp": biz_wa.strip(), "owner_whatsapp": own_wa.strip(),
                           "cash_today": cash, "min_reserve": reserve, "default_payment_terms": int(terms),
                           "setup_done": True})
                ds.save_settings(S0)
                make_demo_invoices(name.strip())          # demo invoices addressed to this business
                audit.log("Owner", "Business set up", f"{name.strip()}; cash {money(cash)}, reserve {money(reserve)}")
                st.rerun()
    st.stop()

# Make sure sign-in accounts exist (older saved settings may not have them yet)
if auth.ensure_users(S0):
    ds.save_settings(S0)

if st.session_state.user is None:
    gate_theme()
    left, right = st.columns([1.2, 0.9], gap="large")
    left.markdown(brand_intro(f"{S0.get('business_name', '')} · fictional demo data"), unsafe_allow_html=True)
    with right:
        with st.container(key="cg_login"):
            st.markdown("### Welcome back")
            st.caption("Sign in to your CashGuard workspace")
            fails = st.session_state.get("login_fails", 0)
            with st.form("login", border=False):
                uname = st.text_input("Username", placeholder="e.g. owner")
                pw = st.text_input("Password", type="password")
                go_in = st.form_submit_button("Sign in", type="primary", use_container_width=True,
                                              disabled=fails >= 5)
            if fails >= 5:
                st.error("Too many wrong tries. Refresh the page to try again.")
            if go_in:
                u = auth.verify(ds.load_settings(), uname, pw)
                if u:
                    st.session_state.user = u
                    st.session_state.login_fails = 0
                    record("Signed in", f"username {u['id']}")
                    st.rerun()
                st.session_state.login_fails = fails + 1
                audit.log("Sign-in", "Failed sign-in", f"username '{uname.strip()[:30]}'")
                st.error("Wrong username or password.")
            with st.expander(":material/key: Demo accounts for judges"):
                st.markdown("| Role | Username | Password |\n|---|---|---|\n" + "\n".join(
                    f"| {r} | `{u}` | `{p}` |" for u, p, _, r in auth.DEMO_ACCOUNTS))
                st.caption("Staff and Managers can never open Owner pages. Passwords are stored only as "
                           "salted hashes. The Owner can change them in Settings → Team & sign-in.")
    st.stop()

# ---------------------------------------------------------------------------
# FRAME: sidebar menu
# ---------------------------------------------------------------------------
user = st.session_state.user
D = load_all()
S = D["settings"]
allowed = PAGES[user["role"]]

# Lark-style navigation: grouped sections, icons, live counts. Only allowed pages are registered,
# so other pages don't exist for this user (not even by URL).
PAGE_OBJ = {p: st.Page(lambda: None, title=p, icon=ICON[p], url_path=SLUG[p], default=(p == allowed[0]))
            for p in allowed}
current = st.navigation(list(PAGE_OBJ.values()), position="hidden")
if st.session_state.get("goto") in PAGE_OBJ:
    st.switch_page(PAGE_OBJ[st.session_state.pop("goto")])
st.session_state.pop("goto", None)
page = current.title
current.run()

n_review = len(pending_items(D))
if user["role"] == "Manager":     # a Manager only counts what they are allowed to decide
    _cap = min(manager_limit(), max(0.0, manager_monthly_limit() - manager_used_this_month(D)))
    n_review = len([i for i in pending_items(D) if i["amount"] <= _cap])
n_wa = len(inbox.list_messages("New"))
COUNTS = {"Review & decide": n_review, "Upload bill": n_wa}

with st.sidebar:
    st.markdown(f'<div class="cg-sbrand"><img src="data:image/png;base64,{b64(LOGO_NAV)}" class="ic">'
                f'<img src="data:image/png;base64,{b64(os.path.join(ASSETS, "wordmark_black.png"))}" class="wm" alt="CashGuard"></div>',
                unsafe_allow_html=True)
    initials = "".join(w[0] for w in S["business_name"].split()[:2]).upper() or "CG"
    st.markdown(f'<div class="cg-ws"><div class="cg-ws-av">{initials}</div><div><b>{S["business_name"]}</b>'
                f'<span>CashGuard Risk · {fdate(D["today"])} {D["today"]:%Y}</span></div></div>',
                unsafe_allow_html=True)
    for section, names in SECTIONS:
        mine = [n for n in names if n in PAGE_OBJ]
        if not mine:
            continue
        st.markdown(f'<div class="cg-sec">{section}</div>', unsafe_allow_html=True)
        for n in mine:
            label = n + (f"  :red-badge[{COUNTS[n]}]" if COUNTS.get(n) else "")
            st.page_link(PAGE_OBJ[n], label=label, icon=ICON[n], use_container_width=True)
    st.markdown('<div class="cg-grow"></div>', unsafe_allow_html=True)
    with st.container(key="cg_me"):
        me_init = "".join(w[0] for w in user["name"].split()[:2]).upper()
        st.markdown(f'<div class="cg-me"><div class="cg-me-av">{me_init}</div><div><b>{user["name"]}</b>'
                    f'<span class="cg-role cg-role-{user["role"]}">{user["role"]}</span></div></div>',
                    unsafe_allow_html=True)
        if st.button("Sign out", icon=":material/logout:", use_container_width=True):
            record("Signed out")
            for k in ("user", "extraction", "goto", "review_pick"):
                st.session_state.pop(k, None)
            st.session_state.user = None
            st.rerun()

# Access control: checked on every run, not only in the menu
if not auth.can_open(user["role"], page):
    audit.log(actor(), "Blocked page access", page)
    st.error(f"🔒 {page} is only for the Owner.")
    st.stop()

page_header(page)
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
    new_wa = inbox.list_messages("New")

    if not st.session_state.get("guide_done"):
        g1, g2 = st.columns([10, 1], vertical_alignment="center")
        g1.markdown('<div class="cg-steps"><span>1. Check your risk</span><i>→</i><span>2. Review a bill</span>'
                    '<i>→</i><span>3. Decide and save</span></div>', unsafe_allow_html=True)
        if g2.button("Got it", key="guide_ok"):
            st.session_state.guide_done = True
            st.rerun()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cash today", money(S["cash_today"]))
    c2.metric(f"Bills due · next {S['horizon_days']} days", money(due30["amount"].sum()),
              help=f"{len(due30)} bills, including ones waiting for your decision")
    c3.metric("Customers owe you", money(owed["amount"].sum()), help=f"{len(owed)} unpaid invoices")
    c4.metric("From WhatsApp", f"{len(new_wa)} to confirm")
    if new_wa:
        c4.button(f"Review {len(new_wa)} invoices", on_click=go_to, args=("Upload bill",),
                  use_container_width=True)

    # Big status card
    risk = base["mc"]["risk"]
    lvl = risk_level(risk, S)[0]
    fail = base["mc"]["fail_day_mode"]
    if fail is None or lvl == "Low":
        msg = (f"Your cash should stay above your {money(S['min_reserve'])} safety cushion for the next "
               f"{S['horizon_days']} days.")
    else:
        near = [n for dd in range(fail, max(-1, fail - 4), -1) for n in state.bill_labels.get(dd, [])]
        why = f", when {near[0].split(' (')[0].lower() if near[0].startswith(('Rent', 'Payroll')) else near[0]} is due" if near else ""
        msg = (f"Your cash may run short. Danger starts around <b>{fdate(state.day_to_date(fail))}</b>{why}. "
               f"Review the bills below before paying anything big.")
    st.markdown(f'<div class="cg-status cg-{lvl}"><div class="pct">{risk:.0%}</div><div>'
                f'<div class="lvl">{EMOJI[lvl]} {lvl} risk · chance of running short in the next '
                f'{S["horizon_days"]} days</div><div class="msg">{msg}</div></div></div>', unsafe_allow_html=True)
    st.caption(f"Based on 1,000 simulated futures, before any new spending. Exact: {risk:.1%}.",
               help=H.GLOSSARY["futures"] + "\n\n" + H.GLOSSARY["cushion"])

    groups = attention(D, state, base)
    with st.expander("👉 See what to do", expanded=lvl == "High"):
        steps = []
        for g, title, detail, act in groups:
            if g == "act":
                steps.append(f"**Review {title}** before paying. {detail}")
            elif g == "chase":
                steps.append(f"**Chase {title.split(' owes')[0]}** for {title.split('owes ')[-1]}. {detail}")
        steps.append("**Keep big optional spending** until after the risk zone on the chart.")
        for i, t in enumerate(steps[:4], 1):
            st.markdown(f"{i}. {t}")

    # Needs your attention: top 3, grouped
    st.markdown("#### Needs your attention")
    label = {"act": "Act now", "chase": "Chase customers", "fyi": "Just so you know"}
    css = {"act": "cg-act", "chase": "cg-chase", "fyi": "cg-fyi"}

    def show_row(i, g, title, detail, act):
        r1, r2 = st.columns([6, 1.3], vertical_alignment="center")
        r1.markdown(f'<div class="cg-row {css[g]}"><small>{label[g]}</small><b>{title}</b> · {detail}</div>',
                    unsafe_allow_html=True)
        if not act:
            return
        if act[0] == "Review":
            r2.button("Review", key=f"att_{i}", on_click=go_to, args=("Review & decide",),
                      kwargs={"review_pick": act[1]}, use_container_width=True)
        elif act[0] == "Review invoices":
            r2.button(f"Review {act[1]}", key=f"att_{i}", on_click=go_to, args=("Upload bill",),
                      use_container_width=True)
        else:
            rcv = act[1]
            with r2.popover("Draft reminder", use_container_width=True):
                draft = (f"Hi {rcv.customer}, hope you're well. A friendly reminder that invoice {rcv.invoice_no} "
                         f"for {money(rcv.amount)} was due on {fdate(state.day_to_date(rcv.due_day))}. Could you "
                         f"let us know when payment will be made? Thank you! - {S['business_name']}")
                st.text_area("Reminder (you send it; nothing is sent automatically)", draft, key=f"draft_{i}",
                             height=150)
                if st.button("Approve draft", key=f"appr_{i}"):
                    record("Approved chase draft", f"{rcv.customer} {rcv.invoice_no} (draft only)")
                    st.success("Approved and logged.")

    for i, row in enumerate(groups[:3]):
        show_row(i, *row)
    if len(groups) > 3:
        with st.expander(f"See all {len(groups)} alerts"):
            for i, row in enumerate(groups[3:], 3):
                show_row(i, *row)

    cg_chart(fan_chart(state, base["mc"], chart_title(state, base["mc"])), use_container_width=True)
    st.caption("Dark line: most likely cash path. Shaded band: where cash will likely stay (9 times out of 10). "
               "Red area: below your safety cushion.", help=H.GLOSSARY["band"])

    st.markdown("#### Payment calendar · next 30 days")
    st.caption(f"Every bill going out and every customer payment expected in. **Red** rows: cash would be below "
               f"your {money(S['min_reserve'])} safety cushion. **Green** rows: money coming in.")
    cal = calendar_rows(D, state)
    st.dataframe(styled_calendar(cal, S["min_reserve"]), hide_index=True, use_container_width=True,
                 column_config={"cash": None})

    with st.expander("ℹ️ How CashGuard works"):
        st.markdown(H.HOW_IT_WORKS)
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
    labels = [i["label"] for i in items]
    pick = st.session_state.pop("review_pick", None)
    choice = st.selectbox("Item to review", labels, index=labels.index(pick) if pick in labels else 0)
    item = next(i for i in items if i["label"] == choice)
    state, ev, due_day = evaluate_item(D, item)
    today_opt, sug = ev["today"], ev["suggested"]
    verb = "pay this bill" if item["kind"] == "bill" else "buy this"

    if item["id"] not in st.session_state.risk_sent:   # log each risk assessment once
        audit.log("CashGuard", "Risk assessed",
                  f"{item['id']}: today {today_opt['risk']:.1%} ({today_opt['level']}); "
                  f"safest {sug['date']:%d %b} {sug['risk']:.1%} ({sug['level']})")
        st.session_state.risk_sent.add(item["id"])

    if item["kind"] == "bill":
        sub = f"Due {fdate(item['row']['due_date'])} · {item['row']['supplier']}"
    else:
        r0 = item["row"]
        cat = r0["category"] if pd.notna(r0["category"]) else "Other"
        lim = policy.categories(S).get(cat, policy.DEFAULT_CATEGORIES["Other"])
        sub = (f"{cat} · by {r0['submitted_by']}<br>Limit: {money(lim['max_per_request'])} per request, "
               f"{money(lim['monthly_limit'])} per month")
    k1, k2, k3 = st.columns(3)
    k1.markdown(f'<div class="cg-card cg-tone-{today_opt["level"]}"><h4>Risk if you pay today</h4><div class="big">'
                f'{EMOJI[today_opt["level"]]} {today_opt["risk"]:.0%}</div>{today_opt["level"]} risk · exact '
                f'{today_opt["risk"]:.1%}<br>Lowest cash in a bad month: <b>{money(today_opt["result"]["worst5"])}</b>'
                f'</div>', unsafe_allow_html=True)
    k2.markdown(f'<div class="cg-card cg-best"><h4>Safest date</h4><div class="big">{fdate(sug["date"])}</div>'
                f'{EMOJI[sug["level"]]} {sug["risk"]:.1%} {sug["level"]} risk<br>Lowest cash in a bad month: '
                f'<b>{money(sug["result"]["worst5"])}</b></div>', unsafe_allow_html=True)
    k3.markdown(f'<div class="cg-card"><h4>Amount</h4><div class="big">{money(item["amount"])}</div>{sub}</div>',
                unsafe_allow_html=True)
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    st.info(explain(state, today_opt, item["amount"], verb))
    if sug["day"] != today_opt["day"]:
        st.success(f"Safer option: {verb} on **{fdate(sug['date'])}** "
                   + ("(still on time). " if item["kind"] == "bill" else ". ")
                   + f"Risk drops from {risk_tag(today_opt['risk'])} to {risk_tag(sug['risk'], 1)}.")

    cg_chart(fan_chart(state, today_opt["result"], chart_title(state, today_opt["result"], f" if you {verb} today"),
                              compare=sug["result"] if sug["day"] != today_opt["day"] else None,
                              compare_label=f"Most likely path if you pay on {fdate(sug['date'])}"),
                    use_container_width=True)

    st.markdown("#### Every date we tested")
    st.dataframe(pd.DataFrame([{
        "Pay on": fdate(o["date"]), "Chance of running short": f"{EMOJI[o['level']]} {o['risk']:.1%} {o['level']}",
        "Most likely lowest cash": money(o["result"]["typical_low"]),
        "Lowest cash in a bad month": money(o["result"]["worst5"]),
        "Suggested": "✓" if o is sug else ""} for o in ev["options"]]),
        hide_index=True, use_container_width=True)

    chase = chase_suggestion(state, today_opt, item["amount"], S)
    if chase and chase["risk_after"] < chase["risk_before"]:
        r = chase["receivable"]
        with st.expander(f"💬 Chase suggestion: {r.customer} ({r.invoice_no}) · risk "
                         f"{risk_tag(chase['risk_before'])} → {risk_tag(chase['risk_after'])} if they pay on time"):
            draft = st.text_area("Reminder draft (owner approves; not sent in demo)", chase["draft"])
            if st.button("Approve reminder draft"):
                record("Approved chase draft", f"{r.customer} {r.invoice_no} (draft only, not sent)")
                st.success("Draft approved and logged. In real use it would be sent via WhatsApp/email.")

    st.markdown("#### Your decision")
    if submitted_by(item) == actor() and user["role"] != "Owner":
        st.warning("You submitted this item, so someone else must decide it (separation of duties).")
        st.stop()
    if user["role"] == "Owner" and item["amount"] > limit:
        st.caption(f"Above the {money(limit)} manager limit - Owner decision.")
    with st.form("decision"):
        if item["kind"] == "bill":
            opts = ["Pay now (today)", f"Schedule on suggested date ({fdate(sug['date'])})",
                    "Schedule on another date", "Hold"]
        else:
            opts = ["Approve - buy today", f"Approve - buy on suggested date ({fdate(sug['date'])})",
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
    tab1, tab2 = st.tabs(["Bills to pay", "Customers owe you"])
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

elif page == "What-if simulator":
    st.caption("Nothing here changes your real data.")
    items = pending_items(D)
    customers = sorted(D["model"])
    for k, v in {"wi_drop": 0, "wi_extra": 0, "wi_cust": "Nobody", "wi_late": 0}.items():
        st.session_state.setdefault(k, v)

    def preset(drop=0, extra=0, cust="Nobody", late=0):
        st.session_state.update(wi_drop=drop, wi_extra=extra, wi_cust=cust, wi_late=late)

    st.markdown("**Quick scenarios**")
    p1, p2, p4 = st.columns(3)
    p1.button("📉 Bad month", on_click=preset, kwargs={"drop": 20}, use_container_width=True,
              help="Sales 20% lower than usual")
    p2.button("🔧 Surprise repair", on_click=preset, kwargs={"extra": 1500}, use_container_width=True,
              help="An unexpected RM1,500 cost this week")
    p4.button("↺ Normal month", on_click=preset, use_container_width=True)

    names = ["No new spending"] + [i["label"] for i in items]
    choice = st.selectbox("Decision to test", names, index=1 if len(names) > 1 else 0)
    c1, c2, c3 = st.columns(3)
    drop = c1.slider("Sales drop by", 0, 50, step=5, format="%d%%", key="wi_drop")
    extra = c2.slider("Surprise cost this week (RM)", 0, 3000, step=100, key="wi_extra")
    late_cust = c3.selectbox("Which customer pays late?", ["Nobody"] + customers, key="wi_cust")
    late_days = c3.slider("Customer pays this many days later", 0, 30, step=1, key="wi_late")
    what_if = {"sales_factor": 1 - drop / 100, "extra_cost": extra,
               "extra_delay": {late_cust: late_days} if late_cust != "Nobody" else {}}
    if choice == "No new spending":
        state = state_for(D)
        res = simulate(state, runs=int(S["simulations"]), **what_if)
        lvl = risk_level(res["risk"], S)[0]
        st.markdown(f'<div class="cg-status cg-{lvl}"><div class="pct">{res["risk"]:.0%}</div><div>'
                    f'<div class="lvl">{EMOJI[lvl]} {lvl} risk in this scenario</div><div class="msg">'
                    f'In a bad month (worst 1 in 20), cash could drop to {money(res["worst5"])}.</div></div></div>',
                    unsafe_allow_html=True)
        cg_chart(fan_chart(state, res, chart_title(state, res, " in this scenario")),
                        use_container_width=True)
    else:
        item = next(i for i in items if i["label"] == choice)
        state, ev, _ = evaluate_item(D, item, **what_if)
        t, sug = ev["today"], ev["suggested"]
        k1, k2 = st.columns(2)
        k1.markdown(f'<div class="cg-card"><h4>Pay today · {fdate(t["date"])}</h4><div class="big">'
                    f'{EMOJI[t["level"]]} {t["risk"]:.0%}</div>{t["level"]} risk · chance of running short<br>'
                    f'Lowest cash in a bad month: <b>{money(t["result"]["worst5"])}</b></div>', unsafe_allow_html=True)
        k2.markdown(f'<div class="cg-card cg-best"><h4>Pay on the safest date · {fdate(sug["date"])}</h4>'
                    f'<div class="big">{EMOJI[sug["level"]]} {sug["risk"]:.0%}</div>{sug["level"]} risk · '
                    f'chance of running short<br>Lowest cash in a bad month: <b>{money(sug["result"]["worst5"])}</b>'
                    f'</div>', unsafe_allow_html=True)
        if sug["day"] != t["day"]:
            st.info(f"In this scenario, waiting until **{fdate(sug['date'])}** cuts your chance of running short "
                    f"from {t['risk']:.0%} to {sug['risk']:.0%}"
                    + (", and the bill is still paid on time." if item["kind"] == "bill" else "."))
        else:
            st.info("Paying today is already the safest choice in this scenario.")
        cg_chart(fan_chart(state, t["result"], chart_title(state, t["result"], " if you pay today"),
                                  compare=sug["result"],
                                  compare_label=f"Most likely path if you pay on {fdate(sug['date'])}"),
                        use_container_width=True)
        with st.expander("Every date we tested"):
            st.dataframe(pd.DataFrame([{
                "Pay on": fdate(o["date"]),
                "Chance of running short": f"{EMOJI[o['level']]} {o['risk']:.1%} {o['level']}",
                "Lowest cash in a bad month": money(o["result"]["worst5"]),
                "Suggested": "✓" if o is sug else ""} for o in ev["options"]]),
                hide_index=True, use_container_width=True)

elif page == "Does it work? (Test)":
    if st.button("Run the test again", help="Takes a few seconds") or "impact" not in st.session_state:
        with st.spinner("Testing 50 situations..."):
            st.session_state.impact = run_impact(S, D["bills"][D["bills"]["captured_by"] == "System"], D["invoices"], D["sales"], D["model"], n=50)
    r = st.session_state.impact
    st.markdown(f"### CashGuard cut cash shortfalls from {r['breach_now']:.1%} to {r['breach_cg']:.1%}, "
                f"and still paid every bill on time." if r["paid_on_time"] == r["n"] else
                f"### CashGuard cut cash shortfalls from {r['breach_now']:.1%} to {r['breach_cg']:.1%}.")
    st.caption("⚠️ Synthetic test: 50 made-up bill situations for a fictional café. Each is judged on 300 fresh "
               "futures from the hidden rules that created the demo data, not from CashGuard's own model.")
    left, right = st.columns([3, 2])
    with left:
        fig = go.Figure(go.Bar(x=["Pay straight away", "Pay on CashGuard's date"],
                               y=[r["breach_now"], r["breach_cg"]], marker_color=["#D92D20", "#2F9E6E"],
                               text=[f"{r['breach_now']:.1%}", f"{r['breach_cg']:.1%}"], textposition="outside",
                               width=0.5))
        fig.update_layout(title="How often cash ran short (lower is better)", height=320,
                          yaxis_tickformat=".0%", yaxis_range=[0, max(r["breach_now"] * 1.3, 0.05)],
                          margin=dict(l=10, r=10, t=50, b=10), plot_bgcolor="#FFFFFF")
        cg_chart(fig, use_container_width=True)
    with right:
        st.metric("Fewer shortfalls", f"{r['reduction']:.0%}")
        st.metric("Bills still paid on time", f"{r['paid_on_time']} of {r['n']}")
        st.metric("Risky situations made safe", f"{r['risky_fixed']} of {r['risky_situations']}",
                  help="Situations with a 5%+ chance of running short if paid straight away, brought below 5%.")
    t = r["table"].copy()
    ex = t.sort_values("Breach rate - pay now", ascending=False).iloc[0]
    st.success(f"**Example, situation {int(ex['Situation'])}:** cash {money(ex['Cash today'])}, bill "
               f"{money(ex['Bill'])} due in {int(ex['Due in (days)'])} days. Paying straight away ran short "
               f"in **{ex['Breach rate - pay now']:.0%}** of futures. CashGuard paid on day "
               f"{int(ex['CashGuard pays on day'])} instead: **{ex['Breach rate - CashGuard']:.0%}**, still on time.")
    with st.expander(f"See all {r['n']} situations"):
        t = t.rename(columns={"Breach rate - pay now": "How often cash ran short - pay now",
                              "Breach rate - CashGuard": "How often cash ran short - CashGuard",
                              "Predicted risk - pay now": "Risk CashGuard predicted (pay now)",
                              "CashGuard pays on day": "CashGuard pays on day"})
        for c in ("How often cash ran short - pay now", "How often cash ran short - CashGuard",
                  "Risk CashGuard predicted (pay now)"):
            t[c] = t[c].map("{:.0%}".format)
        t["Cash today"] = t["Cash today"].map(money)
        t["Bill"] = t["Bill"].map(money)
        hl = int(ex["Situation"])
        st.dataframe(t.style.apply(lambda row: ["background-color:#E7F6EE;font-weight:600"
                                                if row["Situation"] == hl else ""] * len(row), axis=1),
                     hide_index=True, use_container_width=True)

    with st.container(border=True):
        st.markdown("#### Are the payment predictions accurate?")
        bt = backtest(D["invoices"], D["today"])
        st.markdown(f"CashGuard predicts when each customer will really pay. We checked it on {bt['test_rows']} invoices "
                    f"it had not seen: on average it was off by **{bt['model_error_days']:.1f} days**, compared with "
                    f"**{bt['naive_error_days']:.1f} days** if you simply assume everyone pays on the due date.")
        cal = calibration(D["invoices"], D["today"]).rename(columns={
            "Within (days after due date)": "Paid within … days after the due date",
            "Predicted paid": "CashGuard predicted", "Actually paid": "What really happened"})
        for c in ("CashGuard predicted", "What really happened"):
            cal[c] = cal[c].map("{:.0%}".format)
        st.dataframe(cal, hide_index=True, use_container_width=True)
        st.caption("When the two columns are close, the chances CashGuard shows you can be trusted.")

elif page == "Audit log":
    st.caption("Append-only: entries can be added but never edited or deleted.")
    st.dataframe(audit.read(), hide_index=True, use_container_width=True)

elif page == "Settings":
    tab_biz, tab_team, tab_wa, tab_spend, tab_data = st.tabs([
        ":material/storefront: Business & risk", ":material/group: Team & sign-in",
        ":material/chat: WhatsApp", ":material/payments: Spending limits", ":material/database: Data"])
    with tab_biz:
        with st.form("settings"):
            b1, b2 = st.columns(2)
            bname = b1.text_input("Business name", S.get("business_name", ""))
            baddr = b2.text_input("Business address (shown on invoices)", S.get("business_address", ""))
            reserve = st.number_input("Safety cushion: minimum cash you always want to keep (RM)", 0, 100000,
                                      int(S["min_reserve"]), 100, help=H.GLOSSARY["cushion"])
            low = st.slider("🟢 Low risk below", 1, 20, int(S["low_risk_limit"] * 100), format="%d%%")
            high = st.slider("🔴 High risk above", 5, 60, int(S["high_risk_limit"] * 100), format="%d%%")
            runs = st.select_slider("Simulated futures", [500, 1000, 2000, 5000], int(S["simulations"]),
                                    help=H.GLOSSARY["futures"])
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
                          "owner_whatsapp": owner_wa, "business_whatsapp": biz_wa, "notify_suppliers": notify_on,
                          "business_name": bname.strip() or S.get("business_name", ""), "business_address": baddr.strip()})
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
    with tab_team:
        st.markdown("#### People who can sign in")
        st.caption("Each person signs in with their own username and password. Staff and Managers can never open "
                   "Owner pages. Passwords are stored only as salted hashes, never as text.")
        users = S.get("users", [])
        st.dataframe(pd.DataFrame([{"Username": u["username"], "Name": u["name"], "Role": u["role"],
                                    "Can open": ", ".join(PAGES[u["role"]])} for u in users]),
                     hide_index=True, use_container_width=True)
        t1, t2, t3 = st.tabs(["Add a person", "Reset a password", "Remove a person"])
        with t1, st.form("add_user", clear_on_submit=True):
            a1, a2, a3 = st.columns(3)
            nu = a1.text_input("Username")
            nn = a2.text_input("Full name")
            nr = a3.selectbox("Role", ["Employee", "Manager", "Owner"])
            npw = st.text_input("Starting password (min 8 characters)", type="password")
            if st.form_submit_button("Add person", type="primary"):
                prob = auth.check_new_password(npw)
                if not nu.strip() or not nn.strip():
                    st.error("Please fill in a username and name.")
                elif auth.find(S, nu):
                    st.error("That username is already taken.")
                elif prob:
                    st.error(prob)
                else:
                    S["users"] = users + [auth.make_user(nu, npw, nn, nr)]
                    ds.save_settings(S)
                    record("Added user", f"{nu.strip().lower()} as {nr}")
                    st.success(f"Added {nn} ({nr}).")
        with t2, st.form("reset_pw", clear_on_submit=True):
            who = st.selectbox("Person", [u["username"] for u in users])
            pw1 = st.text_input("New password (min 8 characters)", type="password")
            if st.form_submit_button("Reset password", type="primary"):
                prob = auth.check_new_password(pw1)
                if prob:
                    st.error(prob)
                else:
                    old = auth.find(S, who)
                    new = auth.make_user(who, pw1, old["name"], old["role"])
                    S["users"] = [new if u["username"] == who else u for u in users]
                    ds.save_settings(S)
                    record("Reset password", who)
                    st.success(f"Password for {who} changed.")
        with t3:
            who = st.selectbox("Person to remove", [u["username"] for u in users if u["username"] != user["id"]],
                               key="rm_user")
            if st.button("Remove access") and who:
                target = auth.find(S, who)
                if target["role"] == "Owner" and auth.owners(S) <= 1:
                    st.error("Keep at least one Owner.")
                else:
                    S["users"] = [u for u in users if u["username"] != who]
                    ds.save_settings(S)
                    record("Removed user", who)
                    st.rerun()
    with tab_wa:
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
    with tab_spend:
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
    with tab_data:
        st.markdown("**Reset demo data** (restores the original synthetic data and clears logs)")
        if st.checkbox("I understand this resets everything") and st.button("Reset demo data"):
            keep = {k: S.get(k) for k in ("business_name", "business_address", "business_whatsapp",
                                           "owner_whatsapp", "setup_done", "twilio_sandbox_code", "users")}
            generate(force=True)
            ds.save_settings({**ds.load_settings(), **keep})      # keep the business set-up
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

# ---------------------------------------------------------------------------
# Chat helper: placeholder for the next round
# ---------------------------------------------------------------------------
@st.dialog("Ask CashGuard", width="medium")
def chat_dialog():
    st.caption(":material/smart_toy: Coming in the next round: ask questions in your own words and get answers "
               "from your own numbers.")
    st.markdown("".join(f'<span class="cg-chip">{q}</span>' for q in (
        "Why is my risk high this week?", "Which bill should I pay first?",
        "What does 'safety cushion' mean?", "Which customer should I chase?")), unsafe_allow_html=True)
    st.text_input("Message", placeholder="Type a question... (available next round)", disabled=True,
                  label_visibility="collapsed")


with st.container(key="cg_chat"):
    if st.button("Ask CashGuard", icon=":material/forum:", help="Chat assistant (coming in the next round)"):
        chat_dialog()

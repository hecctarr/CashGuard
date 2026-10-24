"""
WhatsApp invoice form: suppliers without a ready invoice fill in a text template on WhatsApp
and CashGuard generates a proper invoice (PDF) for them.

Flow
  1. Supplier sends "INVOICE" (or "hi" / "form") to the business WhatsApp number.
  2. Bot replies with TEMPLATE. Supplier copies it, fills in the blanks and sends it back.
  3. parse_form() reads the reply. apply_defaults() fills everything the supplier left blank:
        invoice no. (auto), invoice date (today), due date (supplier's usual terms, default 30 days),
        bill-to (this business), payment method (online bank transfer - no cash), saved bank details.
  4. render_pdf() draws the invoice. It goes into the CashGuard inbox as a bill with exact fields
     (no AI reading needed) and the supplier gets the PDF back on WhatsApp.
  5. Supplier details are saved, so next time they only fill in the items.

Safety: if the bank account differs from the one saved for that supplier, the bill is flagged
("bank details changed - verify by phone before paying"), a common invoice-fraud pattern.
Nothing is paid automatically. The owner still decides when to pay, by online transfer.
"""

import io
import os
import re
from datetime import datetime, timedelta

FORM_TRIGGERS = {"invoice", "inv", "form", "hi", "hello", "menu", "borang"}
DEFAULT_TERMS_DAYS = 30
PAYMENT_METHOD = "Online bank transfer / DuitNow transfer (no cash)"

TEMPLATE = (
    "*{business} - Invoice form*\n"
    "Copy this message, fill in after each colon and send it back.\n"
    "Leave (optional) lines blank and CashGuard fills them in for you.\n"
    "\n"
    "Supplier name: {name}\n"
    "Invoice no (optional): \n"
    "Item 1: description, qty, unit price\n"
    "Item 2 (optional): \n"
    "Item 3 (optional): \n"
    "Due date (optional, DD/MM/YYYY): \n"
    "Bank name: {bank}\n"
    "Account name: {account_name}\n"
    "Account no: {account_no}\n"
    "Notes (optional): "
)

KEYS = {
    "supplier name": "supplier", "supplier": "supplier", "company": "supplier",
    "invoice no": "invoice_no", "invoice number": "invoice_no",
    "due date": "due_date", "due": "due_date",
    "bank name": "bank", "bank": "bank",
    "account name": "account_name", "account no": "account_no", "account number": "account_no",
    "notes": "notes", "note": "notes",
}


def is_form_request(text: str) -> bool:
    return text.strip().lower().strip("!.?") in FORM_TRIGGERS


def looks_like_form(text: str) -> bool:
    t = text.lower()
    return "item 1" in t and ("supplier" in t or "account" in t)


def template_for(settings: dict, sender: str) -> str:
    p = profile(settings, sender)
    return TEMPLATE.format(business=settings.get("business_name", "Our business"), name=p.get("supplier", ""),
                           bank=p.get("bank", ""), account_name=p.get("account_name", ""),
                           account_no=p.get("account_no", ""))


def profile(settings: dict, sender: str) -> dict:
    return settings.get("supplier_profiles", {}).get(sender, {})


def _money(s: str) -> float:
    return float(re.sub(r"[^0-9.]", "", s or "") or 0)


def _item(value: str):
    """'Arabica beans 1kg, 40, 32.00'  or  'Arabica beans 1kg | 40 | RM32'  or  'Arabica beans 40 x 32'."""
    v = value.strip()
    if not v or v.lower().startswith("description"):
        return None
    parts = [p.strip() for p in re.split(r"[|,;]", v) if p.strip()]
    if len(parts) < 3:
        m = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)\s*[xX@*]\s*(?:RM)?\s*([\d.,]+)$", v)
        if not m:
            raise ValueError(f"Could not read item '{v}'. Use: description, qty, unit price")
        parts = [m.group(1), m.group(2), m.group(3)]
    desc, qty, price = ", ".join(parts[:-2]), _money(parts[-2]), _money(parts[-1])
    if qty <= 0 or price <= 0:
        raise ValueError(f"Item '{desc}' needs a quantity and unit price above zero.")
    return {"description": desc, "qty": qty, "unit_price": round(price, 2), "total": round(qty * price, 2)}


def parse_form(text: str) -> dict:
    """Read a filled template. Returns {'fields': {...}, 'items': [...], 'errors': [...]}."""
    fields, items, errors = {}, [], []
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        k = re.sub(r"\(.*?\)", "", key).strip().strip("*").lower()
        if re.match(r"item\s*\d+", k):
            try:
                it = _item(value)
                if it:
                    items.append(it)
            except ValueError as exc:
                errors.append(str(exc))
        elif k in KEYS and value.strip():
            fields[KEYS[k]] = value.strip()
    if not items and not errors:
        errors.append("Please add at least one item: description, qty, unit price.")
    return {"fields": fields, "items": items, "errors": errors}


def _date(s: str):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def apply_defaults(parsed: dict, settings: dict, sender: str, today, seq: int) -> dict:
    """Fill in everything the supplier left blank. Returns the invoice, its defaults and any problems."""
    f, p = parsed["fields"], profile(settings, sender)
    used_defaults, problems = [], list(parsed["errors"])

    def pick(key, label):
        if f.get(key):
            return f[key]
        if p.get(key):
            used_defaults.append(f"{label} (saved from last time)")
            return p[key]
        return ""

    supplier = pick("supplier", "Supplier name")
    bank, acc_name, acc_no = pick("bank", "Bank"), pick("account_name", "Account name"), pick("account_no", "Account no")
    if not supplier:
        problems.append("Supplier name is missing.")
    if not (bank and acc_name and acc_no):
        problems.append("Bank name, account name and account no are needed so we can pay you by transfer.")
    issue = today.date() if hasattr(today, "date") else today
    terms = int(p.get("terms_days", settings.get("default_payment_terms", DEFAULT_TERMS_DAYS)))
    due = _date(f["due_date"]) if f.get("due_date") else None
    if f.get("due_date") and not due:
        problems.append(f"Due date '{f['due_date']}' is not a date. Use DD/MM/YYYY.")
    if not due:
        due = issue + timedelta(days=terms)
        used_defaults.append(f"Due date ({terms} days after invoice date)")
    if due < issue:
        problems.append("Due date is before today.")
    inv_no = f.get("invoice_no") or f"WA-{issue:%y%m%d}-{seq:02d}"
    if not f.get("invoice_no"):
        used_defaults.append("Invoice no (auto)")
    used_defaults += ["Invoice date (today)", "Bill to (our business)", "Payment by online transfer"]
    bank_changed = bool(p.get("account_no")) and f.get("account_no") and f["account_no"] != p["account_no"]
    invoice = {
        "invoice_no": inv_no, "supplier": supplier, "supplier_phone": sender,
        "issue_date": issue.isoformat(), "due_date": due.isoformat(),
        "bill_to": settings.get("business_name", ""), "bill_to_address": settings.get("business_address", ""),
        "line_items": parsed["items"], "amount": round(sum(i["total"] for i in parsed["items"]), 2),
        "payment_method": PAYMENT_METHOD, "bank": bank, "account_name": acc_name, "account_no": acc_no,
        "notes": f.get("notes", ""), "bank_changed": bool(bank_changed),
    }
    return {"invoice": invoice, "defaults": used_defaults, "problems": problems}


def remember_supplier(settings: dict, sender: str, invoice: dict) -> dict:
    """Save supplier details so the next form is pre-filled. Never overwrites a verified bank account."""
    profs = settings.setdefault("supplier_profiles", {})
    p = profs.setdefault(sender, {})
    p["supplier"] = invoice["supplier"]
    if not p.get("account_no"):                     # first time: save bank details
        p.update({"bank": invoice["bank"], "account_name": invoice["account_name"],
                  "account_no": invoice["account_no"]})
    p.setdefault("terms_days", DEFAULT_TERMS_DAYS)
    return settings


def reply_summary(inv: dict, defaults: list) -> str:
    lines = "\n".join(f"- {i['description']}: {i['qty']:g} x RM{i['unit_price']:,.2f} = RM{i['total']:,.2f}"
                      for i in inv["line_items"])
    warn = ("\n\nNote: these bank details are different from the ones we have on file. Our team will "
            "call you to verify before any payment.") if inv["bank_changed"] else ""
    return (f"Invoice {inv['invoice_no']} created for {inv['bill_to']}.\n{lines}\n"
            f"*Total: RM{inv['amount']:,.2f}* · due {datetime.fromisoformat(inv['due_date']):%d %b %Y}\n"
            f"Payment: {inv['payment_method']} to {inv['bank']} {inv['account_no']}.\n"
            f"Filled in for you: {', '.join(defaults)}.\n"
            f"Our team will check it. You don't need to come in person to collect payment.{warn}")


def render_pdf(inv: dict, logo_path: str = None) -> bytes:
    """Draw the invoice as a one-page A4 PDF."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    navy, grey, line = HexColor("#152846"), HexColor("#5A6785"), HexColor("#D5DDEA")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x0, x1 = 48, W - 48
    y = H - 60
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(x0, y, inv["supplier"] or "Supplier")
    c.drawRightString(x1, y, "INVOICE")
    c.setFont("Helvetica", 9.5)
    c.setFillColor(grey)
    c.drawString(x0, y - 16, f"WhatsApp {inv['supplier_phone']}")
    y -= 50
    rows = [("Invoice no.", inv["invoice_no"]), ("Invoice date", inv["issue_date"]), ("Due date", inv["due_date"])]
    c.setFont("Helvetica", 10)
    for i, (k, v) in enumerate(rows):
        c.setFillColor(grey); c.drawString(x0, y - i * 16, k)
        c.setFillColor(navy); c.drawString(x0 + 90, y - i * 16, v)
    c.setFillColor(grey); c.drawString(W / 2 + 20, y, "Bill to")
    c.setFillColor(navy); c.setFont("Helvetica-Bold", 11); c.drawString(W / 2 + 20, y - 16, inv["bill_to"])
    if inv.get("bill_to_address"):
        c.setFont("Helvetica", 9.5); c.setFillColor(grey); c.drawString(W / 2 + 20, y - 30, inv["bill_to_address"])
    y -= 70
    cols = [x0, x0 + 280, x0 + 350, x1]
    c.setFillColor(navy); c.rect(x0, y - 6, x1 - x0, 22, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 10)
    c.drawString(cols[0] + 8, y + 1, "Item"); c.drawRightString(cols[1] + 40, y + 1, "Qty")
    c.drawRightString(cols[2] + 80, y + 1, "Unit (RM)"); c.drawRightString(cols[3] - 8, y + 1, "Total (RM)")
    y -= 26
    c.setFont("Helvetica", 10)
    for it in inv["line_items"]:
        c.setFillColor(navy)
        c.drawString(cols[0] + 8, y, it["description"][:55])
        c.drawRightString(cols[1] + 40, y, f"{it['qty']:g}")
        c.drawRightString(cols[2] + 80, y, f"{it['unit_price']:,.2f}")
        c.drawRightString(cols[3] - 8, y, f"{it['total']:,.2f}")
        c.setStrokeColor(line); c.line(x0, y - 7, x1, y - 7)
        y -= 22
    y -= 6
    c.setFont("Helvetica-Bold", 13); c.setFillColor(navy)
    c.drawRightString(cols[2] + 20, y, "TOTAL DUE")
    c.drawRightString(cols[3] - 8, y, f"RM{inv['amount']:,.2f}")
    y -= 44
    c.setFont("Helvetica-Bold", 11); c.drawString(x0, y, "How to pay")
    c.setFont("Helvetica", 10); c.setFillColor(grey)
    for i, t in enumerate([inv["payment_method"], f"Bank: {inv['bank']}", f"Account name: {inv['account_name']}",
                           f"Account no: {inv['account_no']}", f"Reference: {inv['invoice_no']}"]):
        c.drawString(x0, y - 16 - i * 14, t)
    if inv.get("notes"):
        c.drawString(x0, y - 16 - 5 * 14 - 6, f"Notes: {inv['notes'][:90]}")
    if inv.get("bank_changed"):
        c.setFillColor(HexColor("#B8382A")); c.setFont("Helvetica-Bold", 10)
        c.drawString(x0, y - 120, "Bank details differ from the supplier's saved details - verify by phone before paying.")
    c.setFillColor(grey); c.setFont("Helvetica", 8.5)
    c.drawString(x0, 48, f"Generated by CashGuard from a WhatsApp invoice form on {datetime.now():%d %b %Y %H:%M}.")
    c.drawString(x0, 36, "Payment is made online by bank transfer. No cash collection needed.")
    if logo_path and os.path.exists(logo_path):
        c.drawImage(logo_path, x1 - 22, 30, width=22, height=30, mask="auto", preserveAspectRatio=True)
    c.showPage(); c.save()
    return buf.getvalue()


def process_form(text: str, sender: str, settings: dict, today, seq: int, logo_path: str = None) -> dict:
    """Full step: parse -> defaults -> PDF. Returns {'ok', 'reply', 'invoice', 'pdf', 'defaults'}."""
    parsed = parse_form(text)
    res = apply_defaults(parsed, settings, sender, today, seq)
    if res["problems"]:
        return {"ok": False, "reply": "Almost there! Please fix and send again:\n- " + "\n- ".join(res["problems"])}
    inv = res["invoice"]
    return {"ok": True, "invoice": inv, "defaults": res["defaults"], "pdf": render_pdf(inv, logo_path),
            "reply": reply_summary(inv, res["defaults"])}


def extraction_from(inv: dict) -> dict:
    """Same shape as capture.extract.extract(), so the app's confirm screen works unchanged."""
    keys = ["supplier", "invoice_no", "amount", "issue_date", "due_date"]
    return {"fields": {**{k: inv[k] for k in keys}, "line_items": inv["line_items"]},
            "confidence": {k: "high" for k in keys}, "method": "WhatsApp invoice form (typed by supplier)",
            "bank_changed": inv["bank_changed"], "payment": {k: inv[k] for k in ("bank", "account_name", "account_no")}}

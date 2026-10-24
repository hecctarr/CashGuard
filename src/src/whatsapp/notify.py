"""
Supplier updates on WhatsApp: the bot tells the supplier what happened to their invoice.

    submitted  -> "received and sent for approval"
    scheduled  -> "approved - will be paid by online transfer on <date>"
    paid       -> "payment made on <date>"
    hold       -> "on hold - we will update you"

Messages never reveal the business's cash position or risk figures, only the invoice's status.
The Owner can turn updates off in Settings ("notify_suppliers").
"""

import pandas as pd

from whatsapp import inbox
from whatsapp.send import send_whatsapp


def share_link(number: str, text: str = "INVOICE") -> str:
    """Click-to-chat link that opens WhatsApp with INVOICE already typed."""
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    return f"https://wa.me/{digits}?text={text}"


def qr_png(data: str, scale: int = 8) -> bytes:
    import io
    import segno
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=scale, border=2, dark="#152846")
    return buf.getvalue()


def supplier_phone(bill_no: str, supplier: str, settings: dict):
    """Find the supplier's WhatsApp number: from the WhatsApp message that created the bill,
    otherwise from the registered senders list."""
    for m in inbox.list_messages():
        if m.get("bill_no") == bill_no and m.get("sender"):
            return m["sender"]
    for s in settings.get("whatsapp_senders", []):
        if s.get("type") == "Supplier" and s.get("name", "").strip().lower() == str(supplier).strip().lower():
            return inbox.normalise(s["number"])
    for num, p in settings.get("supplier_profiles", {}).items():
        if p.get("supplier", "").strip().lower() == str(supplier).strip().lower():
            return num
    return None


def _d(x) -> str:
    return pd.Timestamp(x).strftime("%d %b %Y") if pd.notna(x) and x != "" else "-"


def message(event: str, bill: dict, business: str) -> str:
    no, amt = bill["bill_no"], f"RM{float(bill['amount']):,.2f}"
    if event == "submitted":
        return (f"Hi {bill['supplier']}, {business} has received invoice {no} ({amt}, due "
                f"{_d(bill['due_date'])}) and sent it for approval. We'll update you here.")
    if event == "scheduled":
        return (f"Good news: invoice {no} ({amt}) is approved. {business} will pay by online bank transfer "
                f"on {_d(bill['pay_date'])} (due {_d(bill['due_date'])}). No need to collect in person.")
    if event == "paid":
        return (f"Payment made: {business} transferred {amt} for invoice {no} on {_d(bill['pay_date'])}. "
                f"Reference: {no}. Thank you!")
    if event == "hold":
        return (f"Invoice {no} ({amt}) is on hold for now. {business} will message you here as soon as "
                f"the payment date is set.")
    raise ValueError(event)


def notify_supplier(event: str, bill: dict, settings: dict):
    """Send the update. Returns (number, text, status) or None if updates are off / no number."""
    if not settings.get("notify_suppliers", True):
        return None
    number = supplier_phone(bill["bill_no"], bill["supplier"], settings)
    if not number:
        return None
    text = message(event, bill, settings.get("business_name", "We"))
    return number, text, send_whatsapp(number, text)

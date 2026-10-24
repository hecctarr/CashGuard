"""
WhatsApp inbox: invoices that arrive by WhatsApp wait here until staff confirm them.

Each message = one file (photo/PDF) + one JSON record in data/whatsapp_inbox/.
Used by the webhook server (real WhatsApp) and by the app's demo simulator.
"""

import hashlib
import json
import os
from datetime import datetime

from data_store import path

INBOX = path("whatsapp_inbox")
EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}


def normalise(number: str) -> str:
    n = "".join(ch for ch in str(number) if ch.isdigit() or ch == "+")
    return n if n.startswith("+") else "+" + n


def lookup(number: str, settings: dict):
    """Registered sender (supplier or staff) for this number, or None if unknown."""
    num = normalise(number)
    for s in settings.get("whatsapp_senders", []):
        if normalise(s["number"]) == num:
            return s
    return None


def save_incoming(file_bytes: bytes, content_type: str, sender: str, settings: dict,
                  body: str = "", channel: str = "WhatsApp", original_name: str = "") -> dict:
    os.makedirs(INBOX, exist_ok=True)
    msg_id = datetime.now().strftime("WA%Y%m%d%H%M%S%f")
    ext = EXT.get(content_type.split(";")[0].strip().lower(), ".bin")
    fname = msg_id + ext
    with open(os.path.join(INBOX, fname), "wb") as f:
        f.write(file_bytes)
    digest = hashlib.sha256(file_bytes).hexdigest()
    dup_of = next((m["id"] for m in list_messages() if m.get("sha256") == digest), None)
    who = lookup(sender, settings)
    meta = {
        "id": msg_id, "file": fname, "original_name": original_name or fname,
        "content_type": content_type, "sender": normalise(sender),
        "sender_name": who["name"] if who else "Unknown number",
        "sender_type": who["type"] if who else "Unknown",
        "known": bool(who), "body": body, "channel": channel,
        "received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sha256": digest, "duplicate_of": dup_of, "status": "New", "bill_no": "",
    }
    _write(meta)
    return meta


def _write(meta: dict) -> None:
    with open(os.path.join(INBOX, meta["id"] + ".json"), "w") as f:
        json.dump(meta, f, indent=2)


def list_messages(status: str = None) -> list:
    if not os.path.isdir(INBOX):
        return []
    out = []
    for n in sorted(os.listdir(INBOX)):
        if n.endswith(".json"):
            with open(os.path.join(INBOX, n)) as f:
                m = json.load(f)
            if status is None or m["status"] == status:
                out.append(m)
    return out


def read_file(meta: dict) -> bytes:
    with open(os.path.join(INBOX, meta["file"]), "rb") as f:
        return f.read()


def update(msg_id: str, **fields) -> None:
    with open(os.path.join(INBOX, msg_id + ".json")) as f:
        meta = json.load(f)
    meta.update(fields)
    _write(meta)


def receipt_text(fields: dict, business: str) -> str:
    """Auto-reply to the sender. It confirms receipt only - it never promises payment."""
    if fields.get("invoice_no") and fields.get("amount"):
        due = f", due {fields['due_date']}" if fields.get("due_date") else ""
        return (f"Thank you - {business} received invoice {fields['invoice_no']} "
                f"(RM{float(fields['amount']):,.2f}{due}). Our team will check it.")
    return f"Thank you - {business} received your file. Our team will check it."

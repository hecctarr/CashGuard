"""
Send a WhatsApp message (used for receipt replies and the owner's weekly summary).

If TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM are set, it sends
through Twilio. Otherwise (demo mode) it only records the message in data/whatsapp_outbox.jsonl.
"""

import json
import os
from datetime import datetime

from data_store import path


def send_whatsapp(to: str, text: str) -> str:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    frm = os.environ.get("TWILIO_WHATSAPP_FROM")       # e.g. +14155238886 (Twilio sandbox number)
    status = "demo - not sent (no WhatsApp keys configured)"
    if sid and token and frm:
        try:
            import requests
            r = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data={"From": f"whatsapp:{frm}", "To": f"whatsapp:{to}", "Body": text},
                auth=(sid, token), timeout=20)
            status = "sent" if r.ok else f"failed ({r.status_code})"
        except Exception as exc:
            status = f"failed ({exc.__class__.__name__})"
    with open(path("whatsapp_outbox.jsonl"), "a") as f:
        f.write(json.dumps({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "to": to, "text": text, "status": status}) + "\n")
    return status


def read_outbox() -> list:
    try:
        with open(path("whatsapp_outbox.jsonl")) as f:
            return [json.loads(l) for l in f if l.strip()][::-1]
    except FileNotFoundError:
        return []

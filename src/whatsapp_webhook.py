"""
CashGuard WhatsApp webhook server - invoices sent on WhatsApp arrive in CashGuard automatically.

Run next to the app:
    python whatsapp_webhook.py            # listens on port 5055

Option A - Twilio WhatsApp (best for the hackathon demo)
    In the Twilio console, set the sandbox "When a message comes in" URL to
        https://<your-public-url>/twilio/whatsapp
    Environment: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
    Optional:    PUBLIC_URL (the exact public URL Twilio calls, used to check Twilio's signature)

Option B - Meta WhatsApp Cloud API (production route)
    Webhook URL: https://<your-public-url>/meta/whatsapp
    Environment: META_VERIFY_TOKEN, META_ACCESS_TOKEN, META_PHONE_NUMBER_ID, META_API_VERSION (e.g. v21.0)
    Note: Meta media download links expire after about 5 minutes, so files are fetched immediately.

Two ways a supplier can send an invoice:
    A. A photo or PDF of their own invoice (read by the AI model).
    B. No invoice ready? They send "INVOICE" and the bot replies with a fill-in form. They fill it in,
       send it back, and CashGuard generates the invoice PDF for them (see whatsapp/invoice_form.py),
       filling in defaults: invoice no., dates, bill-to, payment by online transfer, saved bank details.

What happens to each photo/PDF:
    1. Only photos/PDFs are accepted (one file per WhatsApp message).
    2. The file is saved to the CashGuard WhatsApp inbox; unknown numbers are flagged.
    3. The invoice is read (AI if EXTRACT_API_URL/EXTRACT_MODEL_URL is set, else left for staff to type).
    4. The sender gets a receipt reply. Nothing is approved or paid automatically -
       staff confirm the fields in CashGuard and the owner decides.
"""

import base64
import hashlib
import hmac
import os
from xml.sax.saxutils import escape

import requests
from flask import Flask, Response, abort, request

import data_store as ds
from capture.extract import extract
from make_data import generate
from whatsapp import inbox
from whatsapp import invoice_form as form

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

app = Flask(__name__)
generate()


def _store_and_read(file_bytes, content_type, sender, body, channel):
    settings = ds.load_settings()
    meta = inbox.save_incoming(file_bytes, content_type, sender, settings, body=body, channel=channel)
    if meta.get("duplicate_of"):
        inbox.update(meta["id"], status="Duplicate")
        return (f"Thank you - {settings.get('business_name') or 'we'} already has this invoice. "
                "No need to send it again.")
    ex = extract(meta["original_name"], file_bytes)
    if ex.get("is_invoice") is False:                       # bot: ignore non-invoice photos
        inbox.update(meta["id"], extraction=ex, status="Not an invoice")
        return ("This doesn't look like an invoice. Please send a clear photo or PDF of the "
                "supplier invoice.")
    inbox.update(meta["id"], extraction=ex)
    note = "" if meta["known"] else " (Note: this number is not registered with us yet.)"
    return inbox.receipt_text(ex["fields"], settings.get("business_name") or "Our business") + note


def handle_text(sender: str, body: str, channel: str):
    """Text messages: send the invoice form, or turn a filled form into an invoice.
    Returns (reply_text, media_url_or_None)."""
    settings = ds.load_settings()
    sender = inbox.normalise(sender)
    if form.looks_like_form(body):
        today = __import__("pandas").Timestamp(settings["today"])
        seq = 1 + sum(1 for m in inbox.list_messages() if m.get("channel", "").endswith("form"))
        res = form.process_form(body, sender, settings, today, seq, os.path.join(ASSETS, "logo_navy_64.png"))
        if not res["ok"]:
            return res["reply"], None
        inv = res["invoice"]
        meta = inbox.save_incoming(res["pdf"], "application/pdf", sender, settings, body=body,
                                   channel=f"{channel} - invoice form", original_name=f"{inv['invoice_no']}.pdf")
        inbox.update(meta["id"], extraction=form.extraction_from(inv), generated=True)
        ds.save_settings(form.remember_supplier(settings, sender, inv))
        base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        return res["reply"], (f"{base}/files/{meta['id']}" if base else None)
    if form.is_form_request(body) or not body.strip():
        return ("Hi! To send us an invoice you can:\n1) send a photo or PDF of your invoice, or\n"
                "2) fill in the form below and we will create the invoice for you.\n\n"
                + form.template_for(settings, sender)), None
    return ("Sorry, we didn't understand that. Send a photo/PDF of your invoice, or type INVOICE "
            "to get the fill-in form."), None


@app.get("/files/<msg_id>")
def generated_file(msg_id):
    """Serve a generated invoice PDF so WhatsApp can attach it (set PUBLIC_BASE_URL)."""
    meta = next((m for m in inbox.list_messages() if m["id"] == msg_id and m.get("generated")), None)
    if not meta:
        abort(404)
    return Response(inbox.read_file(meta), mimetype="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={meta['original_name']}"})


# ---------------------------------------------------------------- Twilio
def _twilio_signature_ok() -> bool:
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not token or os.environ.get("SKIP_TWILIO_SIGNATURE") == "1":
        return True
    url = os.environ.get("PUBLIC_URL", request.url)
    data = url + "".join(k + v for k, v in sorted(request.form.items()))
    expected = base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, request.headers.get("X-Twilio-Signature", ""))


def _twiml(text, media_url=None):
    media = f"<Media>{escape(media_url)}</Media>" if media_url else ""
    return Response(f"<?xml version='1.0' encoding='UTF-8'?><Response><Message><Body>{escape(text)}</Body>"
                    f"{media}</Message></Response>", mimetype="application/xml")


@app.post("/twilio/whatsapp")
def twilio_whatsapp():
    if not _twilio_signature_ok():
        abort(403)
    sender = request.form.get("From", "").replace("whatsapp:", "")
    body = request.form.get("Body", "")
    n = int(request.form.get("NumMedia", "0") or 0)
    if n == 0:
        reply, media_url = handle_text(sender, body, "WhatsApp (Twilio)")
        return _twiml(reply, media_url)
    sid, token = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
    replies = []
    for i in range(n):
        url = request.form.get(f"MediaUrl{i}")
        ctype = request.form.get(f"MediaContentType{i}", "")
        if not url or ctype.split(";")[0] not in inbox.EXT:
            replies.append("Sorry, please send a photo (JPG/PNG) or a PDF.")
            continue
        r = requests.get(url, auth=(sid, token) if sid and token else None, timeout=30)
        r.raise_for_status()
        replies.append(_store_and_read(r.content, ctype, sender, body, "WhatsApp (Twilio)"))
    return _twiml(" ".join(replies))


# ---------------------------------------------------------------- Meta Cloud API
@app.get("/meta/whatsapp")
def meta_verify():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == os.environ.get("META_VERIFY_TOKEN")):
        return request.args.get("hub.challenge", "")
    abort(403)


@app.post("/meta/whatsapp")
def meta_whatsapp():
    token = os.environ.get("META_ACCESS_TOKEN")
    version = os.environ.get("META_API_VERSION", "v21.0")
    payload = request.get_json(silent=True) or {}
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                kind = msg.get("type")
                phone_id = os.environ.get("META_PHONE_NUMBER_ID")
                if kind == "text":
                    reply, media_url = handle_text(msg.get("from", ""), msg["text"].get("body", ""), "WhatsApp (Meta)")
                    if phone_id:
                        requests.post(f"https://graph.facebook.com/{version}/{phone_id}/messages",
                                      headers={"Authorization": f"Bearer {token}"},
                                      json={"messaging_product": "whatsapp", "to": msg.get("from"),
                                            "type": "text", "text": {"body": reply}}, timeout=30)
                        if media_url:
                            requests.post(f"https://graph.facebook.com/{version}/{phone_id}/messages",
                                          headers={"Authorization": f"Bearer {token}"},
                                          json={"messaging_product": "whatsapp", "to": msg.get("from"),
                                                "type": "document",
                                                "document": {"link": media_url, "filename": "invoice.pdf"}}, timeout=30)
                    continue
                if kind not in ("image", "document"):
                    continue
                media = msg[kind]
                info = requests.get(f"https://graph.facebook.com/{version}/{media['id']}",
                                    headers={"Authorization": f"Bearer {token}"}, timeout=30).json()
                file_bytes = requests.get(info["url"], headers={"Authorization": f"Bearer {token}"},
                                          timeout=60).content
                reply = _store_and_read(file_bytes, info.get("mime_type", media.get("mime_type", "")),
                                        msg.get("from", ""), media.get("caption", ""), "WhatsApp (Meta)")
                phone_id = os.environ.get("META_PHONE_NUMBER_ID")
                if phone_id:
                    requests.post(f"https://graph.facebook.com/{version}/{phone_id}/messages",
                                  headers={"Authorization": f"Bearer {token}"},
                                  json={"messaging_product": "whatsapp", "to": msg.get("from"),
                                        "type": "text", "text": {"body": reply}}, timeout=30)
    return "ok"


@app.get("/")
def health():
    return "CashGuard WhatsApp webhook is running."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5055)))

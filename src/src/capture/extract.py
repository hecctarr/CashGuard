"""
Invoice capture: read a supplier invoice and run safety checks.

Where AI is used (and only here). Tried in this order:
  1. A vision model on RunPod: set RUNPOD_API_KEY + RUNPOD_ENDPOINT_ID for a RunPod Serverless
     vLLM endpoint (OpenAI-compatible) running GLM-OCR. Or set EXTRACT_MODEL_URL to any other
     OpenAI-compatible vision endpoint (plus EXTRACT_MODEL_NAME / EXTRACT_MODEL_KEY).
  2. EXTRACT_API_URL - any custom service that accepts the file and returns JSON fields.
  3. Demo invoices: pre-extracted fields from demo_invoices/fallback.json, so the demo
     never breaks during judging.
  4. Otherwise an empty form for manual entry.
A person ALWAYS checks and confirms the fields before anything is saved.
"""

import base64
import json
import os
import re

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FALLBACK = os.path.join(BASE, "demo_invoices", "fallback.json")
FIELDS = ["supplier", "invoice_no", "amount", "issue_date", "due_date"]

PROMPT = (
    "Read this image. Return ONLY JSON with keys: is_invoice (true if it is a supplier invoice or "
    "bill asking for payment, false for anything else such as a receipt, menu or chat photo), "
    "supplier, invoice_no, amount "
    "(total due as a number), issue_date (YYYY-MM-DD), due_date (YYYY-MM-DD), line_items "
    "(list of {description, qty, unit_price, total}), confidence (object giving 'high' or 'low' "
    "for each of supplier, invoice_no, amount, issue_date, due_date). Use null for anything "
    "you cannot read. Never guess a number you cannot see."
)


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def _model_endpoint():
    """(base_url, api_key) for the vision model, or (None, None) if not configured."""
    if os.environ.get("EXTRACT_MODEL_URL"):
        return os.environ["EXTRACT_MODEL_URL"], os.environ.get("EXTRACT_MODEL_KEY")
    if os.environ.get("RUNPOD_API_KEY") and os.environ.get("RUNPOD_ENDPOINT_ID"):
        return (f"https://api.runpod.ai/v2/{os.environ['RUNPOD_ENDPOINT_ID']}/openai/v1",
                os.environ["RUNPOD_API_KEY"])
    return None, None


def _from_model(file_name: str, file_bytes: bytes) -> dict:
    import requests
    base, key = _model_endpoint()
    url = base.rstrip("/") + "/chat/completions"
    mime = "image/png" if file_name.lower().endswith(".png") else "image/jpeg"
    image = f"data:{mime};base64,{base64.b64encode(file_bytes).decode()}"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    resp = requests.post(url, headers=headers, timeout=90, json={
        "model": os.environ.get("EXTRACT_MODEL_NAME", "zai-org/GLM-OCR"),
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": image}}]}],
    })
    resp.raise_for_status()
    data = _parse_json(resp.json()["choices"][0]["message"]["content"])
    return {"fields": {**{k: data.get(k) for k in FIELDS}, "line_items": data.get("line_items") or []},
            "confidence": data.get("confidence") or {}, "method": "AI model (vision endpoint)",
            "is_invoice": data.get("is_invoice", True)}


def extract(file_name: str, file_bytes: bytes) -> dict:
    if _model_endpoint()[0] and not file_name.lower().endswith(".pdf"):
        try:
            return _from_model(file_name, file_bytes)
        except Exception as exc:  # fall through to the safe options
            print("AI model extraction failed, using fallback:", exc)
    api = os.environ.get("EXTRACT_API_URL")
    if api:
        try:
            import requests
            resp = requests.post(api, files={"file": (file_name, file_bytes)}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return {"fields": {**{k: data.get(k) for k in FIELDS}, "line_items": data.get("line_items") or []},
                    "confidence": data.get("confidence", {}), "method": "AI model (API)"}
        except Exception as exc:
            print("AI extraction failed, using fallback:", exc)
    if os.path.exists(FALLBACK):
        with open(FALLBACK) as f:
            demo = json.load(f)
        if file_name in demo:
            return {**demo[file_name], "method": "Demo extraction (pre-extracted fallback)"}
    return {"fields": {**{k: None for k in FIELDS}, "line_items": []}, "confidence": {},
            "method": "Manual entry"}


def line_items_check(fields: dict) -> list:
    """Maths check: line items must add up to the invoice total."""
    items = fields.get("line_items") or []
    out = []
    try:
        totals = [float(i.get("total") or 0) for i in items]
        for i in items:
            if i.get("qty") is not None and i.get("unit_price") is not None and i.get("total") is not None:
                if abs(float(i["qty"]) * float(i["unit_price"]) - float(i["total"])) > 0.05:
                    out.append(("warning", f"Line '{i.get('description', '?')}': qty x price does not equal its total"))
        if items and fields.get("amount") is not None and abs(sum(totals) - float(fields["amount"])) > 0.05:
            out.append(("error", f"Line items add up to RM{sum(totals):,.2f} but the total says "
                                 f"RM{float(fields['amount']):,.2f}. Please check the amount."))
    except (TypeError, ValueError):
        out.append(("warning", "Could not check the line items - please review them."))
    return out


def checks(fields: dict, bills: pd.DataFrame, today: pd.Timestamp) -> list:
    """Return a list of (level, message). level: 'error' blocks saving, 'warning' flags it."""
    out = []
    missing = [k for k in FIELDS if not fields.get(k)]
    if missing:
        out.append(("error", f"Missing: {', '.join(missing)}"))
    try:
        amount = float(fields.get("amount") or 0)
    except ValueError:
        amount = 0
    if amount <= 0:
        out.append(("error", "Amount must be more than RM0"))
    dup = bills[(bills["supplier"] == fields.get("supplier")) &
                (bills["bill_no"] == fields.get("invoice_no"))]
    if len(dup):
        out.append(("error", f"Duplicate: {fields.get('invoice_no')} from this supplier is already recorded"))
    past = bills[(bills["supplier"] == fields.get("supplier")) & (bills["bill_no"] != fields.get("invoice_no"))]
    if len(past) and amount > 2 * past["amount"].mean():
        out.append(("warning", f"Unusual amount: more than 2x this supplier's average "
                               f"(RM{past['amount'].mean():,.0f})"))
    if fields.get("due_date") and pd.Timestamp(fields["due_date"]) < today:
        out.append(("warning", "Due date has already passed"))
    out += line_items_check(fields)
    return out

"""
RunPod Serverless handler - CashGuard invoice reader (GPU workload).

Two ways to run the invoice-reading model on RunPod:

  A. Recommended (no custom code): create a Serverless endpoint from RunPod's ready-made vLLM
     worker with model `zai-org/GLM-OCR`. The app calls it directly through RunPod's
     OpenAI-compatible URL  https://api.runpod.ai/v2/<ENDPOINT_ID>/openai/v1
     using RUNPOD_API_KEY + RUNPOD_ENDPOINT_ID (see src/capture/extract.py).

  B. Custom worker (this file): build a worker image that runs a vLLM OpenAI server for
     GLM-OCR inside the container (VLLM_BASE_URL, default http://localhost:8000/v1) and uses
     this handler. Input:  {"input": {"image_base64": "...", "mime": "image/png"}}
                    Output: {"fields": {...}, "line_items": [...], "confidence": {...}}

The handler only READS invoices. It never approves or pays anything.
"""

import json
import os
import re

import requests
import runpod

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("MODEL_NAME", "zai-org/GLM-OCR")
FIELDS = ["supplier", "invoice_no", "amount", "issue_date", "due_date"]
PROMPT = (
    "Read this supplier invoice. Return ONLY JSON with keys: supplier, invoice_no, amount "
    "(total due as a number), issue_date (YYYY-MM-DD), due_date (YYYY-MM-DD), line_items "
    "(list of {description, qty, unit_price, total}), confidence (object giving 'high' or 'low' "
    "for each of supplier, invoice_no, amount, issue_date, due_date). Use null for anything "
    "you cannot read. Never guess a number you cannot see."
)


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def handler(job):
    data = job.get("input") or {}
    image_b64 = data.get("image_base64")
    if not image_b64:
        return {"error": "image_base64 is required"}
    mime = data.get("mime", "image/png")
    resp = requests.post(f"{VLLM_BASE_URL}/chat/completions", timeout=120, json={
        "model": MODEL,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ]}],
    })
    resp.raise_for_status()
    out = _parse_json(resp.json()["choices"][0]["message"]["content"])
    return {"fields": {k: out.get(k) for k in FIELDS},
            "line_items": out.get("line_items") or [],
            "confidence": out.get("confidence") or {}}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

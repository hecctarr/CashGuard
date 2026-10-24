"""
Draw fictional supplier invoices for the demo (PNG) + their fallback JSON.
Run:  python -m capture.make_demo_invoices
"""

import json
import os

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "demo_invoices")

INVOICES = [
    {
        "file": "kopi_bean_SB-552.png",
        "supplier": "Kopi Bean Trading (demo)", "address": "Lot 12, Jalan Contoh, 40000 Shah Alam",
        "invoice_no": "SB-552", "issue_date": "2026-10-27", "due_date": "2026-11-05",
        "lines": [("Arabica beans 1kg", 40, 32.0), ("House blend 1kg", 20, 26.0)],
        # What the "AI" returns: due date misread on purpose so staff must correct it
        "extracted": {"due_date": "2026-11-04"},
        "confidence": {"supplier": "high", "invoice_no": "high", "amount": "high",
                       "issue_date": "high", "due_date": "low"},
    },
    {
        "file": "fresh_dairy_SB-560.png",
        "supplier": "Fresh Dairy Supply (demo)", "address": "No. 8, Jalan Sampel, 47300 Petaling Jaya",
        "invoice_no": "SB-560", "issue_date": "2026-10-27", "due_date": "2026-11-12",
        "lines": [("Fresh milk 1L", 150, 4.2), ("Whipping cream 1L", 10, 2.0)],
        "extracted": {},
        "confidence": {"supplier": "high", "invoice_no": "high", "amount": "high",
                       "issue_date": "high", "due_date": "high"},
    },
]


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for p in (f"/usr/share/fonts/truetype/dejavu/{name}", name):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw(inv):
    img = Image.new("RGB", (800, 1000), "white")
    d = ImageDraw.Draw(img)
    d.text((50, 50), inv["supplier"], font=font(30, True), fill="black")
    d.text((50, 95), inv["address"], font=font(16), fill="#444")
    d.text((50, 120), "DEMO INVOICE - FICTIONAL COMPANY", font=font(14), fill="#b00")
    d.text((560, 50), "INVOICE", font=font(34, True), fill="#333")
    y = 190
    for k, v in (("Invoice no.", inv["invoice_no"]), ("Invoice date", inv["issue_date"]),
                 ("Due date", inv["due_date"]), ("Bill to", "Demo Café")):
        d.text((50, y), k, font=font(18), fill="#555")
        d.text((250, y), v, font=font(18, True), fill="black")
        y += 36
    y += 30
    d.line((50, y, 750, y), fill="#999", width=2)
    d.text((50, y + 10), "Item", font=font(17, True), fill="black")
    d.text((420, y + 10), "Qty", font=font(17, True), fill="black")
    d.text((520, y + 10), "Unit (RM)", font=font(17, True), fill="black")
    d.text((660, y + 10), "Total", font=font(17, True), fill="black")
    y += 45
    total = 0.0
    for item, qty, unit in inv["lines"]:
        line_total = qty * unit
        total += line_total
        d.text((50, y), item, font=font(17), fill="black")
        d.text((420, y), str(qty), font=font(17), fill="black")
        d.text((520, y), f"{unit:,.2f}", font=font(17), fill="black")
        d.text((660, y), f"{line_total:,.2f}", font=font(17), fill="black")
        y += 34
    d.line((50, y + 10, 750, y + 10), fill="#999", width=2)
    d.text((480, y + 30), "TOTAL DUE (RM)", font=font(20, True), fill="black")
    d.text((660, y + 30), f"{total:,.2f}", font=font(20, True), fill="black")
    d.text((50, 900), "Payment terms: please pay by the due date.", font=font(15), fill="#555")
    return img, total


def main():
    os.makedirs(OUT, exist_ok=True)
    fallback = {}
    for inv in INVOICES:
        img, total = draw(inv)
        img.save(os.path.join(OUT, inv["file"]))
        fields = {"supplier": inv["supplier"], "invoice_no": inv["invoice_no"],
                  "amount": round(total, 2), "issue_date": inv["issue_date"],
                  "due_date": inv["due_date"],
                  "line_items": [{"description": d, "qty": q, "unit_price": u, "total": round(q * u, 2)}
                                 for d, q, u in inv["lines"]]}
        fields.update(inv["extracted"])
        fallback[inv["file"]] = {"fields": fields, "confidence": inv["confidence"]}
    with open(os.path.join(OUT, "fallback.json"), "w") as f:
        json.dump(fallback, f, indent=2)
    print("Demo invoices written to", OUT)


if __name__ == "__main__":
    main()

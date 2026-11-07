"""Normalize an FDA tainted-supplements export into data/tainted_supplements.csv.

1. Open FDA's "Health Fraud Product Database" / "Tainted Products Marketed as Dietary Supplements"
   page in a browser and export/download the table (CSV or XLSX).
   Page: https://www.fda.gov/consumers/health-fraud-scams/health-fraud-product-database
   It has no export button (checked 2026-11-07): select the table, paste into Google Sheets,
   File > Download > CSV.
2. python -m scripts.import_tainted path/to/download.csv

Column names vary between exports, so we map by fuzzy header match.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from app.evidence.tainted import CSV_PATH

TARGET = ["date", "product_name", "company", "hidden_ingredients", "category", "url"]
ALIASES = {
    "date": ["date", "posted", "warning date"],
    "product_name": ["product", "product name", "name"],
    "company": ["company", "firm", "distributor", "manufacturer"],
    # FDA Health Fraud Product Database (checked 2026-11-07) columns: Date, Product, Firm,
    # Firm Address, Source/URL(s), Subject, Action, Program Area(s), Additional Outcome.
    # The hidden drug is usually named in "Subject".
    "hidden_ingredients": ["hidden", "ingredient", "undeclared", "subject"],
    "category": ["category", "program", "marketed"],
    "url": ["url", "link", "notification", "source"],
}


def map_headers(headers: list[str]) -> dict[str, str | None]:
    out = {}
    for t in TARGET:
        out[t] = next((h for h in headers if any(a in h.lower() for a in ALIASES[t])), None)
    return out


def main(src: str) -> None:
    path = Path(src)
    if path.suffix.lower() in (".xlsx", ".xls"):
        import pandas as pd  # pip install pandas openpyxl
        rows = pd.read_excel(path).fillna("").astype(str).to_dict("records")
        headers = list(rows[0].keys()) if rows else []
    else:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers, rows = reader.fieldnames or [], list(reader)
    m = map_headers(headers)
    print("header mapping:", m)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TARGET)
        w.writeheader()
        for r in rows:
            w.writerow({t: (r.get(m[t]) or "").strip() if m[t] else "" for t in TARGET})
    print(f"wrote {len(rows)} rows to {CSV_PATH}")


if __name__ == "__main__":
    main(sys.argv[1])

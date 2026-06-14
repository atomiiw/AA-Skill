#!/usr/bin/env python3
"""
Extract purchase transactions from Bank of America PDF eStatements into a small
bofa_raw.jsonl — WITHOUT loading the (large) PDF text into the chat.

Each statement line looks like:
    04/13/26   MOBILE PURCHASE 0410 SQ *PHO N MOR Los Angeles CA   -18.52
We keep money-OUT purchases (negative amounts), drop transfers / Zelle / bill
pay / deposits, and emit {date, raw_desc, amount, currency} per transaction.
An LLM (Claude) then reads bofa_raw.jsonl and turns each cryptic raw_desc into a
real brand + item for bills.jsonl.

Needs `pdftotext` (poppler).  brew install poppler   if missing.

Functions-only module — no CLI. The front door is ../run.py, which calls
parse_bofa(). The BofA folder is an EXTERNAL path the user points to; the
bofa_raw.jsonl output is written to the current working directory.
"""

import glob
import json
import os
import re
import subprocess
from datetime import datetime

# date  ....description....  amount(at end of line, optional minus, 2 decimals)
TXN_RE = re.compile(r"^\s*(\d{2}/\d{2}/\d{2})\s+(.*\S)\s+(-?[\d,]+\.\d{2})\s*$")

# Lines that are NOT purchases even if they carry an amount.
SKIP = re.compile(
    r"\bZelle\b|\bDES:|\bBILL PAY\b|\bPPD\b|payment from|payment to|"
    r"\bTRANSFER\b|\bDEPOSIT\b|\bINTEREST\b|Beginning balance|Ending balance",
    re.IGNORECASE,
)


def pdf_text(path):
    return subprocess.run(
        ["pdftotext", "-layout", path, "-"],
        capture_output=True,
        text=True,
    ).stdout


def parse_amount(s):
    return float(s.replace(",", ""))


def parse_bofa(folder, since=None, until=None, out="bofa_raw.jsonl"):
    """Parse every BofA PDF in `folder`, write purchases to `out`, return count.

    `since`/`until` are inclusive "YYYY-MM-DD" strings (or None for no bound).
    """
    folder = os.path.expanduser(folder)
    since_d = datetime.strptime(since, "%Y-%m-%d").date() if since else None
    until_d = datetime.strptime(until, "%Y-%m-%d").date() if until else None

    pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    if not pdfs:
        raise SystemExit(f"No PDFs in {folder}")

    seen = set()  # (date, desc, amount) dedupe across overlapping statements
    n = 0
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for pdf in pdfs:
            for line in pdf_text(pdf).splitlines():
                m = TXN_RE.match(line)
                if not m:
                    continue
                raw_date, desc, raw_amt = m.group(1), m.group(2).strip(), m.group(3)
                amount = parse_amount(raw_amt)
                if amount >= 0:  # money in (deposit/Zelle/refund) — not a bill
                    continue
                if SKIP.search(desc):
                    continue
                mm, dd, yy = raw_date.split("/")
                d = datetime(2000 + int(yy), int(mm), int(dd)).date()
                if (since_d and d < since_d) or (until_d and d > until_d):
                    continue
                key = (d.isoformat(), desc, amount)
                if key in seen:
                    continue
                seen.add(key)
                fh.write(
                    json.dumps(
                        {
                            "date": d.isoformat(),
                            "raw_desc": desc,
                            "amount": round(-amount, 2),  # store as positive money spent
                            "currency": "$",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                n += 1

    print(f"Wrote {n} BofA purchases -> {out}")
    return n

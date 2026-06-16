#!/usr/bin/env python3
"""
Write-side helpers over bills.jsonl / split_bills.jsonl (Stages 2–4).
Functions-only module — the front door is ../run.py.

These exist so the ledger is built and edited ONLY through run.py subcommands,
never through inline `python3 -c` or hand-written scripts:
  add_rows(rows_path, bills)  -> append rows Claude wrote (after normalizing a
                                 brand/item) to bills.jsonl, dedupe against what
                                 is already there, keep it sorted by date asc.
  sort_bills(bills)           -> re-sort bills.jsonl by date asc.
  trim(since, bills)          -> drop rows before a (flexibly parsed) start day.
  ledger_text(bills)          -> a stable, numbered, date-sorted listing.
  write_splits(indices, bills, out) -> append the chosen ledger rows to
                                 split_bills.jsonl (Stage 4, "append as you go").

All functions tolerate a missing file (treated as empty) and skip malformed
lines, so a half-written ledger never crashes the pipeline.
"""

import json
import os
import re
from datetime import date

_MONTH_NAMES = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]


def _load(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _amount(total):
    """Bare numeric string from a total like '$18.52' / '¥1,200.00' for dedupe."""
    m = re.search(r"[0-9][0-9,]*\.\d{2}", total or "")
    return m.group(0).replace(",", "") if m else (total or "").strip()


def _key(r):
    return (str(r.get("brand", "")).lower(), _amount(r.get("total")), r.get("date"))


def _sort_key(r):
    return (r.get("date") or "", str(r.get("brand") or ""))


def sort_bills(path="bills.jsonl"):
    rows = _load(path)
    rows.sort(key=_sort_key)
    _write(path, rows)
    return {"sorted": len(rows)}


def add_rows(rows_path, bills_path="bills.jsonl"):
    """Append new rows to bills.jsonl, skipping ones already present, then sort.

    Dedupe key is (brand, amount, date); an existing row wins (so a BofA row is
    preferred over a duplicate email receipt for the same charge).
    """
    existing = _load(bills_path)
    new = _load(rows_path)
    seen = {_key(r) for r in existing}
    added = 0
    for r in new:
        k = _key(r)
        if k in seen:
            continue
        seen.add(k)
        existing.append(r)
        added += 1
    existing.sort(key=_sort_key)
    _write(bills_path, existing)
    return {"added": added, "skipped_duplicates": len(new) - added, "total": len(existing)}


def _iso(y, mo, d):
    try:
        return date(y, mo, d).isoformat()
    except (ValueError, TypeError):
        return None


def _month_num(token):
    token = token.lower()
    if len(token) < 3:
        return None
    for i, name in enumerate(_MONTH_NAMES, 1):
        if name.startswith(token):
            return i
    return None


def parse_flexible_date(s, year_hint=None):
    """Parse a user-typed start day in many formats -> ISO 'YYYY-MM-DD' or None.

    Accepts e.g. 2026-04-16, 2026/4/16, 4/16, 04-16, 4.16, 0416, 'April 16',
    'Apr 16 2026'. When the year is omitted, `year_hint` supplies it.
    """
    s = (s or "").strip()
    # ISO-ish: YYYY-MM-DD with -, / or .
    m = re.match(r"^(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Month name + day [+ year]
    m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:[,\s]+(20\d{2}))?$", s)
    if m:
        mo = _month_num(m.group(1))
        y = int(m.group(3)) if m.group(3) else year_hint
        if mo and y:
            return _iso(y, mo, int(m.group(2)))
    # M/D or M-D or M.D [+ year]
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})(?:[-/.](20\d{2}))?$", s)
    if m:
        y = int(m.group(3)) if m.group(3) else year_hint
        if y:
            return _iso(y, int(m.group(1)), int(m.group(2)))
    # Compact MMDD
    m = re.match(r"^(\d{2})(\d{2})$", s)
    if m and year_hint:
        return _iso(year_hint, int(m.group(1)), int(m.group(2)))
    return None


def _year_hint(rows):
    for r in rows:
        d = r.get("date") or ""
        if re.match(r"^20\d{2}-", d):
            return int(d[:4])
    return None


def trim(since, bills_path="bills.jsonl"):
    """Drop rows dated before `since` (flexibly parsed), rewrite, report counts.

    Raises SystemExit with a clear message if `since` can't be parsed, so the
    caller re-asks instead of silently guessing.
    """
    rows = _load(bills_path)
    iso = parse_flexible_date(since, _year_hint(rows))
    if not iso:
        raise SystemExit(
            f"Could not parse start day '{since}'. Try e.g. 2026-04-16, 4/16, or 'April 16'."
        )
    kept = [r for r in rows if (r.get("date") or "") >= iso]
    kept.sort(key=_sort_key)
    removed = len(rows) - len(kept)
    _write(bills_path, kept)
    return {"since": iso, "removed": removed, "remaining": len(kept)}


def ledger_text(bills_path="bills.jsonl"):
    """Stable, numbered, date-sorted listing — indices match write_splits().

    Rows carrying a truthy `unverified` flag (vendor that could not be confidently
    identified) are marked with a trailing ⚠, and counted in the header, so an
    unconfirmed guess is never mistaken for a verified brand.
    """
    rows = _load(bills_path)
    rows.sort(key=_sort_key)
    unverified = sum(1 for r in rows if r.get("unverified"))
    header = f"{len(rows)} bills (idx | date | brand | item | total | source | card)"
    if unverified:
        header += f"  — ⚠ {unverified} unverified (eyeball these)"
    out = [header]
    for i, r in enumerate(rows):
        flag = "  ⚠ unverified" if r.get("unverified") else ""
        out.append(
            f"[{i:>3}] {r.get('date', '?'):10} {str(r.get('brand', '?')):22} | "
            f"{r.get('item', '')} | {r.get('total', '')} | {r.get('source', '')} | "
            f"{r.get('card', '')}{flag}"
        )
    return "\n".join(out)


def write_splits(indices, bills_path="bills.jsonl", out="split_bills.jsonl"):
    """Append the chosen ledger rows (by ledger_text index) to split_bills.jsonl."""
    rows = _load(bills_path)
    rows.sort(key=_sort_key)
    picked = [rows[i] for i in indices if 0 <= i < len(rows)]
    bad = [i for i in indices if not (0 <= i < len(rows))]
    existing = _load(out)
    existing.extend(picked)
    _write(out, existing)
    return {"appended": len(picked), "out_of_range": bad, "total": len(existing)}

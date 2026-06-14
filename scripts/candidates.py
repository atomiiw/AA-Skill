#!/usr/bin/env python3
"""
Read-side helpers over candidates.jsonl (Stage 3 triage). Functions-only module —
the front door is ../run.py.

These exist so Claude never has to read the (often >1 MB) candidates.jsonl into
context, and never has to hand-write a python3 -c loop to inspect it:
  triage(path)            -> a compact one-line-per-email index (source, money
                             flag, from, subject) for deciding what to read.
  show(indices, path)     -> full from/subject/date/body for specific indices,
                             so the brand/item/total can be extracted by judgment.

Both use the SAME robust loader (malformed JSON lines are skipped, not fatal), so
the index printed by triage matches the index accepted by show.
"""

import json
import re
import sys

CURRENCY_RE = re.compile(r"\$|¥|￥|\bRMB\b|\bCNY\b|\bUSD\b|元", re.IGNORECASE)


def _load(path):
    """Load candidates.jsonl LENIENTLY: skip blank/malformed lines with a warning.

    This tolerance exists only to keep reading *older* files that predate the
    strict writer — newly harvested files are verified strict (see verify_jsonl)
    and should never need it. Warnings go to stderr so stdout stays clean JSON.
    """
    rows = []
    skipped = 0
    with open(path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                skipped += 1
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
                print(f"  (warning: skipped malformed line {n} in {path})", file=sys.stderr)
    if skipped:
        print(
            f"  (warning: skipped {skipped} blank/malformed line(s) in {path}; "
            f"regenerate it to get a strict file)",
            file=sys.stderr,
        )
    return rows


def verify_jsonl(path, max_report=10):
    """STRICT check that `path` is valid JSON Lines: one JSON object per line.

    Returns (ok, errors). Fails — and records the exact 1-based line number — on:
      * any blank / whitespace-only line
      * any line that is not valid JSON
      * any line whose top-level value is not a JSON object
    Reports at most `max_report` problems. A file with zero lines is valid (no
    candidates found is a legitimate result).
    """
    errors = []
    with open(path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n")
            if line.strip() == "":
                errors.append(f"line {n}: blank line")
            else:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"line {n}: invalid JSON ({exc})")
                else:
                    if not isinstance(obj, dict):
                        errors.append(f"line {n}: not a JSON object (got {type(obj).__name__})")
            if len(errors) >= max_report:
                break
    return (not errors), errors


def triage(path="candidates.jsonl"):
    """One compact line per candidate: [idx] source $ from | subject."""
    rows = _load(path)
    out = [f"{len(rows)} candidates (idx | source | $=has-currency | from | subject)"]
    for i, o in enumerate(rows):
        blob = (o.get("subject", "") or "") + "\n" + (o.get("body", "") or "")
        money = "$" if CURRENCY_RE.search(blob) else " "
        frm = (o.get("from", "") or "")[:34]
        sub = (o.get("subject", "") or "")[:64]
        out.append(f"[{i:>3}] {o.get('source', '?'):5} {money} {frm:34} | {sub}")
    return "\n".join(out)


def show(indices, path="candidates.jsonl", max_chars=4000):
    """Full headers + (truncated) body for the given candidate indices."""
    rows = _load(path)
    out = []
    for i in indices:
        if not (0 <= i < len(rows)):
            out.append(f"===== [{i}] OUT OF RANGE (have {len(rows)}) =====")
            continue
        o = rows[i]
        out.append(f"===== [{i}] {o.get('source', '?')} =====")
        out.append(f"From:    {o.get('from', '')}")
        out.append(f"Subject: {o.get('subject', '')}")
        out.append(f"Date:    {o.get('date_header', '')}")
        out.append("Body:")
        out.append((o.get("body", "") or "")[:max_chars])
        out.append("")
    return "\n".join(out)

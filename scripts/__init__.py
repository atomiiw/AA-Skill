"""
split-bills scripts package — private implementation behind ../run.py.

Modules expose functions only (no CLI). run.py is the single front door; nothing
in here is meant to be executed directly.

  daterange  — Stage 1 date-range selector logic (start_years / start_months /
               end_options / resolve)
  parse_bofa — Stage 2 BofA PDF parser (parse_bofa)
  receipts   — Stage 3 QQ + Gmail receipt harvester (harvest)
  candidates — Stage 3 triage/show over candidates.jsonl (triage / show)
  ledger     — Stages 2–4 bills.jsonl ops (add_rows / sort_bills / trim /
               ledger_text / write_splits)
"""

from . import candidates, daterange, ledger, parse_bofa, receipts

__all__ = ["candidates", "daterange", "ledger", "parse_bofa", "receipts"]

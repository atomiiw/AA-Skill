#!/usr/bin/env python3
"""
Single entrypoint ("front door") for the split-bills skill. The scripts/ package
holds the private implementation (functions only); this file is the ONLY thing
Claude runs, so the skill needs just ONE Bash allow rule:

    Bash(python3 .claude/skills/split-bills/run.py:*)

Commands:
    # Stage 1 — date-range selectors (print JSON)
    python3 run.py daterange start-years  [--today YYYY-MM-DD]
    python3 run.py daterange start-months --year YYYY [--today YYYY-MM-DD]
    python3 run.py daterange end-options  --start YYYY-MM [--today YYYY-MM-DD]
    python3 run.py daterange resolve      --start YYYY-MM --end YYYY-MM [--today YYYY-MM-DD]

    # Stage 2 — BofA PDFs -> split_bill_outputs/intermediate/bofa_raw.jsonl
    python3 run.py parse-bofa --dir "<BofA folder>" [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                              [--out PATH]

    # Stage 3 — QQ + Gmail -> split_bill_outputs/intermediate/email_raw.jsonl
    python3 run.py receipts --secrets-dir "<dir>" [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                            [--qq-auth FILE] [--gmail-pw FILE] [--out PATH]
                            [--max-chars N] [--only qq,gmail]

    # Stage 3 — inspect harvested candidates (no big file in context)
    python3 run.py triage [--in PATH]
    python3 run.py show --indices 4,5,6 [--in PATH] [--max-chars N]

    # Stages 2-4 — build/edit the ledger (Claude writes a *_processed.jsonl file, run.py merges)
    python3 run.py add  --from PATH [--bills PATH]   # append + dedupe + sort
    python3 run.py sort [--bills PATH]
    python3 run.py trim --since <flexible date> [--bills PATH]
    python3 run.py ledger [--bills PATH]             # numbered, date-sorted
    python3 run.py split --indices 0,3,7 [--bills PATH] [--out PATH]

All outputs default into ./split_bill_outputs/ (created automatically) under the
current working directory:
    intermediate/  bofa_raw.jsonl  bofa_processed.jsonl
                   email_raw.jsonl  email_processed.jsonl
    deliverables/  bills.jsonl  split_bills.jsonl
"""

import argparse
import json
from datetime import date

from scripts import candidates, daterange, ledger, parse_bofa, receipts

# --- canonical output layout (relative to the current working directory) ------
OUT_ROOT = "split_bill_outputs"
INTERMEDIATE = OUT_ROOT + "/intermediate"
DELIVERABLES = OUT_ROOT + "/deliverables"

BOFA_RAW = INTERMEDIATE + "/bofa_raw.jsonl"  # parse-bofa output
BOFA_PROCESSED = INTERMEDIATE + "/bofa_processed.jsonl"  # Claude writes; add reads
EMAIL_RAW = INTERMEDIATE + "/email_raw.jsonl"  # receipts output; triage/show read
EMAIL_PROCESSED = INTERMEDIATE + "/email_processed.jsonl"  # Claude writes; add reads
BILLS = DELIVERABLES + "/bills.jsonl"  # the ledger deliverable
SPLIT = DELIVERABLES + "/split_bills.jsonl"  # the splittable deliverable


def _indices(s):
    """Parse '0,3, 7' / '0 3 7' into a list of ints."""
    return [int(x) for x in s.replace(",", " ").split()]


def _today(args):
    return date.fromisoformat(args.today) if args.today else date.today()


def cmd_daterange(args):
    today = _today(args)
    if args.op == "start-years":
        result = daterange.start_years(today)
    elif args.op == "start-months":
        if args.year is None:
            raise SystemExit("daterange start-months needs --year YYYY")
        result = daterange.start_months(today, args.year)
    elif args.op == "end-options":
        if not args.start:
            raise SystemExit("daterange end-options needs --start YYYY-MM")
        result = daterange.end_options(today, args.start)
    elif args.op == "start-days":
        if not args.start:
            raise SystemExit("daterange start-days needs --start YYYY-MM")
        result = daterange.start_days(args.start)
    elif args.op == "resolve":
        if not (args.start and args.end):
            raise SystemExit("daterange resolve needs --start and --end (YYYY-MM)")
        result = daterange.resolve(today, args.start, args.end)
    else:  # unreachable: argparse restricts choices
        raise SystemExit(f"unknown daterange op: {args.op}")
    print(json.dumps(result))


def cmd_parse_bofa(args):
    parse_bofa.parse_bofa(args.dir, since=args.since, until=args.until, out=args.out)


def cmd_receipts(args):
    only = {s.strip() for s in args.only.split(",")} if args.only else None
    receipts.harvest(
        since=args.since,
        until=args.until,
        secrets_dir=args.secrets_dir,
        qq_auth=args.qq_auth,
        gmail_pw=args.gmail_pw,
        out=args.out,
        max_chars=args.max_chars,
        only=only,
    )


def cmd_triage(args):
    print(candidates.triage(args.infile))


def cmd_show(args):
    print(candidates.show(_indices(args.indices), args.infile, max_chars=args.max_chars))


def cmd_add(args):
    print(json.dumps(ledger.add_rows(args.from_, bills_path=args.bills)))


def cmd_sort(args):
    print(json.dumps(ledger.sort_bills(args.bills)))


def cmd_trim(args):
    print(json.dumps(ledger.trim(args.since, bills_path=args.bills)))


def cmd_ledger(args):
    print(ledger.ledger_text(args.bills))


def cmd_split(args):
    result = ledger.write_splits(_indices(args.indices), bills_path=args.bills, out=args.out)
    print(json.dumps(result))


def build_parser():
    ap = argparse.ArgumentParser(prog="run.py", description="split-bills front door")
    sub = ap.add_subparsers(dest="cmd", required=True)

    dr = sub.add_parser("daterange", help="Stage 1 date-range selectors (JSON out)")
    dr.add_argument(
        "op", choices=["start-years", "start-months", "end-options", "start-days", "resolve"]
    )
    dr.add_argument("--today", help="Override today's date (YYYY-MM-DD) for testing.")
    dr.add_argument("--year", type=int, help="start-months: which year.")
    dr.add_argument("--start", help="end-options/resolve: start month YYYY-MM.")
    dr.add_argument("--end", help="resolve: end month YYYY-MM.")
    dr.set_defaults(func=cmd_daterange)

    pb = sub.add_parser("parse-bofa", help=f"Stage 2 BofA PDFs -> {BOFA_RAW}")
    pb.add_argument("--dir", required=True, help="Folder of BofA eStatement PDFs.")
    pb.add_argument("--since", help="Inclusive start YYYY-MM-DD.")
    pb.add_argument("--until", help="Inclusive end YYYY-MM-DD.")
    pb.add_argument("--out", default=BOFA_RAW, help="Output path.")
    pb.set_defaults(func=cmd_parse_bofa)

    rc = sub.add_parser("receipts", help=f"Stage 3 QQ + Gmail -> {EMAIL_RAW}")
    rc.add_argument(
        "--secrets-dir", default=".", help="Folder holding qq_auth.txt / gmail_app_pw.txt."
    )
    rc.add_argument("--since", help="Inclusive start YYYY-MM-DD (default: 12 months ago).")
    rc.add_argument("--until", help="Inclusive end YYYY-MM-DD (default: today).")
    rc.add_argument("--qq-auth", help="Explicit path to the QQ auth-code file.")
    rc.add_argument("--gmail-pw", help="Explicit path to the Gmail app-password file.")
    rc.add_argument("--out", default=EMAIL_RAW, help="Output path.")
    rc.add_argument("--max-chars", type=int, default=6000, help="Truncate each cleaned body.")
    rc.add_argument("--only", help="Comma-separated account names (e.g. 'qq' or 'qq,gmail').")
    rc.set_defaults(func=cmd_receipts)

    tr = sub.add_parser("triage", help=f"Stage 3 compact index of {EMAIL_RAW}")
    tr.add_argument("--in", dest="infile", default=EMAIL_RAW, help="candidates file.")
    tr.set_defaults(func=cmd_triage)

    sh = sub.add_parser("show", help="Stage 3 full headers+body for candidate indices")
    sh.add_argument("--indices", required=True, help="e.g. 4,5,6")
    sh.add_argument("--in", dest="infile", default=EMAIL_RAW, help="candidates file.")
    sh.add_argument("--max-chars", type=int, default=4000, help="Truncate each body.")
    sh.set_defaults(func=cmd_show)

    ad = sub.add_parser("add", help=f"Append a *_processed rows file to {BILLS} (dedupe + sort)")
    ad.add_argument("--from", dest="from_", required=True, help="JSONL rows file to merge in.")
    ad.add_argument("--bills", default=BILLS, help=f"Ledger file (default: {BILLS}).")
    ad.set_defaults(func=cmd_add)

    so = sub.add_parser("sort", help="Sort the ledger by date ascending")
    so.add_argument("--bills", default=BILLS, help="Ledger file.")
    so.set_defaults(func=cmd_sort)

    tm = sub.add_parser("trim", help="Drop bills before a (flexibly parsed) start day")
    tm.add_argument("--since", required=True, help="Start day, any format (e.g. 4/16, April 16).")
    tm.add_argument("--bills", default=BILLS, help="Ledger file.")
    tm.set_defaults(func=cmd_trim)

    lg = sub.add_parser("ledger", help="Print the numbered, date-sorted ledger")
    lg.add_argument("--bills", default=BILLS, help="Ledger file.")
    lg.set_defaults(func=cmd_ledger)

    sp = sub.add_parser("split", help=f"Append chosen ledger rows to {SPLIT}")
    sp.add_argument("--indices", required=True, help="Ledger indices, e.g. 0,3,7")
    sp.add_argument("--bills", default=BILLS, help="Ledger file.")
    sp.add_argument("--out", default=SPLIT, help="Splittable output file.")
    sp.set_defaults(func=cmd_split)

    return ap


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

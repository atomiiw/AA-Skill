# split-bills — a Claude Code skill

Tally and split personal expenses for a chosen date range by combining **Bank of
America PDF statements**, **QQ mail**, and **Gmail receipts** into one ledger,
then interactively picking which bills to split.

It normalizes cryptic card-statement vendor strings (`SQ *PHO N MOR`,
`TST* MOVITA JUICE`) into real brands, keeps big PDF/email text out of the model's
context, and runs entirely through one entrypoint so it needs just a single
permission grant.

## Install

This repo **is** the skill folder. Drop it into a `.claude/skills/` directory:

```bash
# project-local (this project only)
git clone <repo-url> /path/to/your/project/.claude/skills/split-bills

# or user-global (every project)
git clone <repo-url> ~/.claude/skills/split-bills
```

The folder name must be `split-bills` (it's the skill's identity). Then open
Claude Code in that project and run the skill (e.g. `/split-bills`, or just ask to
"track and split my bills").

## Requirements

- **python3** (3.11+), standard library only — no pip install needed.
- **pdftotext** (from Poppler) for BofA parsing: `brew install poppler`.
- **IMAP credentials** for the email stages (optional if you only want BofA):
  - `qq_auth.txt` — a QQ Mail IMAP authorization code.
  - `gmail_app_pw.txt` — a Gmail **app password** (Security → App passwords).
  - Put both in one folder; you point the skill at it in Stage 0. They can also
    be supplied via `$QQ_AUTH_CODE` / `$GMAIL_APP_PW`.

## How it works

```
Preflight  Permissions   (add one allow rule, or approve prompts)
Stage 0    Locate inputs  → BofA folder + secrets folder
Stage 1    Date range     → month-granularity selectors
Stage 2    BofA PDFs      → intermediate/bofa_raw.jsonl  → normalize → bills.jsonl
Stage 3    QQ + Gmail     → intermediate/email_raw.jsonl → parse    → bills.jsonl
Stage 3.5  Start day      → trim the ledger
Stage 4    Split picks    → deliverables/split_bills.jsonl
```

Stages 0, 1, 3.5, 4 are interactive; 2 and 3 are automatic. The skill is the only
thing that runs scripts, always through `run.py`.

## Single entrypoint

`run.py` is the **only** script Claude executes; `scripts/` holds the private
implementation (functions only), `tools/` holds maintenance utilities.

```bash
python3 run.py daterange <start-years|start-months|end-options|resolve> ...
python3 run.py parse-bofa --dir "<BofA folder>" [--since ...] [--until ...]
python3 run.py receipts   --secrets-dir "<dir>" [--since ...] [--until ...]
python3 run.py triage | show --indices 4,5,6
python3 run.py add --from <rows.jsonl> | sort | trim --since <date> | ledger
python3 run.py split --indices 0,3,7
```

## Permission

Because everything routes through `run.py`, the recipient grants exactly one rule
(the Preflight offers to add it for you):

```json
"Bash(python3 .claude/skills/split-bills/run.py:*)"
```

## Output layout

All artifacts land under `split_bill_outputs/` in the working directory (created
automatically, git-ignored):

```
split_bill_outputs/
├── intermediate/   bofa_raw.jsonl  bofa_processed.jsonl
│                   email_raw.jsonl  email_processed.jsonl   (scratch)
└── deliverables/   bills.jsonl  split_bills.jsonl           (the keepers)
```

## Development

```bash
python3 tools/validate_skill.py          # structural self-check (stdlib only)
ruff check . --fix && ruff format .       # lint/format (config in pyproject.toml)
```

No personal data is tracked — `.gitignore` excludes `secrets/`, `bofa*/`, `*.pdf`,
`*.jsonl`, and `split_bill_outputs/`.

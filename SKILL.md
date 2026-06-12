---
name: split-bills
description: >-
  Tally and split personal expenses for a chosen date range by combining Bank of
  America PDF statements, QQ mail, and Gmail receipts into one bills.jsonl, then
  interactively pick which bills to split into split_bills.jsonl. Use when the
  user wants to track bills/expenses, gather receipts across accounts, normalize
  cryptic card-statement vendor names into real brands, or decide what to split.
---

# Split Bills

Build a unified expense ledger from three sources, then let the user choose what
to split. Three stages are **interactive** (locate inputs, date range, split
selection); the middle stages are **fully automatic (your own work — do not ask
the user)**.

```
Preflight Permissions     ← INTERACTIVE (guided: add allow rules, or approve prompts as they come)
Stage 0  Locate inputs    ← INTERACTIVE (ask for BofA folder + secrets dir; remember for the session)
Stage 1  Date range       ← INTERACTIVE (selector form, no free-text dates)
Stage 2  BofA PDFs   → bills.jsonl   (parse + normalize cryptic vendors)   AUTO
Stage 3  QQ + Gmail  → bills.jsonl   (receipts + LLM filter; ALWAYS sort by date) AUTO
Stage 3.5 Start day  → trim bills.jsonl   ← INTERACTIVE (1st-of-month, or typed date)
Stage 4  Split selection → split_bills.jsonl   ← INTERACTIVE (append as you go)
```

## ⛔ Interaction contract — READ FIRST, applies to the whole skill

The Permissions preflight and the interactive stages (0, 1, 4) are **mandatory
STOP points**. At each one you MUST ask the user and **wait for their actual
reply** before doing anything else.

**You are forbidden to assume, default, guess, or auto-fill any interactive
input — even when an obvious answer exists.** Specifically:
- Do **not** treat the presence of a folder like `./bofa Apr to Jun records`, or
  `qq_auth.txt` in the cwd, as permission to skip Stage 0. A plausible path is
  NOT an answer — the user must give it to you.
- Do **not** pick the end month (or "the full window", or "through the current
  month") yourself in Stage 1. Every month boundary comes from the user.
- Do **not** carry on to the next stage, run any script, or say things like
  "I'll use the obvious locations" / "I'll take it through June". That is the
  exact failure this contract exists to prevent.

The only thing you may reuse without re-asking is an answer the user **already
gave you in this same session** (e.g. a path captured in Stage 0). There is no
"defaults" shortcut; if you have not been told, you ask. When in doubt, ask.

Each interactive stage below ends with a **STOP** line — when you reach it, send
the question and end your turn. Do not pre-run later stages "to save time".

## Files & where things live

**Skill code** lives in this skill folder (the directory that holds this
SKILL.md — currently `.claude/skills/split-bills/`). There is a **single
entrypoint**, `run.py`; the stage logic lives in the private `pipeline/` package
(functions only — never invoked directly). Always call `run.py` and a subcommand,
e.g. `python3 .claude/skills/split-bills/run.py parse-bofa …`. If the folder ever
moves, use its new path; the commands below assume `.claude/skills/split-bills/`:
- `run.py daterange <start-years|start-months|end-options|resolve>` — computes
  Stage 1 selector options (valid start years/months, end months, and the
  resolved `--since`/`--until`) from today's date; prints JSON.
- `run.py parse-bofa` — extracts purchases from the BofA PDFs →
  `…/intermediate/bofa_raw.jsonl` (keeps big PDF text OUT of context). Takes
  `--dir <BofA folder>`.
- `run.py receipts` — pulls QQ + Gmail receipt candidates →
  `…/intermediate/email_raw.jsonl` (server-side keyword filter + currency gate).
  Takes `--secrets-dir <dir>`.
- `run.py triage` — prints a compact one-line-per-email index of
  `…/intermediate/email_raw.jsonl` (source, currency flag, from, subject) so you
  decide what to open WITHOUT reading the whole (often >1 MB) file.
- `run.py show --indices 4,5,6` — prints full headers + body for those candidate
  indices, so you read just the plausible receipts.
- `run.py add --from <…_processed.jsonl>` — appends rows you wrote to the ledger
  `…/deliverables/bills.jsonl`, de-duplicates (brand+amount+date), and re-sorts by
  date ascending.
- `run.py sort` / `run.py trim --since <date>` / `run.py ledger` — sort, trim by
  start day (flexible date parsing), and print the numbered date-sorted ledger.
- `run.py split --indices 0,3,7` — appends the chosen ledger rows to
  `…/deliverables/split_bills.jsonl` (Stage 4).

**⛔ HARD RULE — `run.py` is the ONLY script you run.** Never write a throwaway
`.py` file, never use `python3 -c …`, and never append `&& echo …`, `| wc -l`, or
any other shell helper to a `run.py` call — those break out of the single allow
rule and trigger a fresh permission prompt (this is exactly what caused the prompt
flood before). Every mechanical step already has a subcommand that prints its own
summary. To get rows into the ledger, compose them with the **Write tool** into the
matching `…/intermediate/<bofa|email>_processed.jsonl` file, then
`run.py add --from <that file>`. That is the entire write path — there is no
ad-hoc-script path.

**Inputs** are EXTERNAL paths the user gives you in Stage 0 (BofA PDF folder; the
secrets folder holding `qq_auth.txt` / `gmail_app_pw.txt`). Never hardcode them.

**Outputs go in the current working directory**, NOT in the skill folder — the
skill folder holds only code so it stays portable; run artifacts belong in the
user's workspace. Run every command from that working directory. Every output
lands under a single **`split_bill_outputs/`** tree (each `run.py` subcommand
creates it automatically, and you Write the `*_processed.jsonl` files into it):
```
split_bill_outputs/
├── intermediate/   ← scratch; safe to delete after a run
│   ├── bofa_raw.jsonl         (run.py parse-bofa)
│   ├── bofa_processed.jsonl   (you Write it; cleaned BofA rows)
│   ├── email_raw.jsonl        (run.py receipts)
│   └── email_processed.jsonl  (you Write it; parsed receipt rows)
└── deliverables/   ← the keepers
    ├── bills.jsonl
    └── split_bills.jsonl
```
The defaults already point here, so plain `run.py add` / `ledger` / `trim` /
`split` need no path flags; only `--from` (a `*_processed.jsonl` you wrote) is
given explicitly.

## Preflight — Permissions (INTERACTIVE, guided — do this FIRST, before any script)

This skill runs one local entrypoint (`run.py`) via Bash. Permissions are
user/project-local and are NOT shipped with the skill, so on a fresh setup Claude
Code prompts on every run. Handle this for the user as a guided step — **do not**
make them read docs or hand-edit JSON. Run this once at the very start, before
Stage 1.

1. Read the project `.claude/settings.local.json` (it may not exist). Check
   whether this single `permissions.allow` rule is already present (use this
   skill folder's real path if it isn't `.claude/skills/split-bills/`):
   - `Bash(python3 .claude/skills/split-bills/run.py:*)`
2. **Present** → say "permissions ready" and continue, no question.
3. **Missing** → ask with `AskUserQuestion` (one question):
   *"Let this skill's scripts run without asking each time?"*
   - **Yes — add allow rule** → merge the rule into `permissions.allow`
     in `.claude/settings.local.json` (create the file and keys if absent; keep
     every existing entry). The `:*` makes one approval cover every subcommand
     and argument. Confirm in one line.
   - **No — ask me each time** → continue; Claude Code will prompt per command,
     and the user can still pick "don't ask again" on each native prompt.
   Then **STOP** until they answer.

Editing the settings file is allowed **only** on an explicit "Yes" here — that
consent is the authorization. Never edit it otherwise.

## Output schema
`bills.jsonl` and `split_bills.jsonl` — one JSON object per line:
```json
{"brand": "UberEats", "item": "poke bowl", "total": "$18.52", "date": "2026-04-13", "source": "bofa"}
```
- **brand** — a recognizable company/restaurant name (NOT the raw descriptor).
- **item** — what was bought (`groceries`, `1 yr subscription`, a dish, clothing…).
- **total** — string with currency symbol, `$` or `¥` (RMB).
- **date** — ISO `YYYY-MM-DD`.
- **source** — `bofa` | `qq` | `gmail` (helps dedupe & trace).

---

## Stage 0 — Locate inputs (INTERACTIVE) — do this FIRST

Get **two paths** from the user with **`AskUserQuestion`**, one question at a time:
the **BofA folder** and the **secrets folder**. The secrets folder is one
directory that holds **both** credential files together — `qq_auth.txt` and
(optionally) `gmail_app_pw.txt`; you pass it once as `--secrets-dir`. Do **not**
scrape the filesystem for candidates — the user supplies each path directly.

**Expect nothing, pre-fill nothing.** Do not look up, compute, or guess a default
path — no cwd, no `./qq_auth.txt`, no "obvious" location. Guessing presumes input
the user hasn't given and wastes tokens/time. You know **zero** paths until the
user types or drops one. The path always arrives through the harness's built-in
**"Other"** free-text box.

**Tool reality (don't fight it):** `AskUserQuestion` requires **2–4 explicit
options** — a lone option errors with `InputValidationError` — and the harness
**always** appends its own free-text **"Other"** entry. So you can't render a
blank/one-option picker; the user sees your options plus "Other". Use exactly two
fixed options, neither of which is a guessed path:

```
Question: <what path is needed>? Paste or drop it in the "Other" field.
Options:
  1. Paste / drop path   (reminder to use the built-in "Other" box)
  2. Skip
```

Interpret the answer:
- **Other (free text)** → the typed/dropped string is the path. This is the
  normal path-in route.
- **Skip** → do **not** guess a fallback. Pause and tell the user this input is
  required; re-ask when they're ready.

Keep wording minimal — short labels, no filler. Ask twice, STOP after each:
1. **BofA folder** → `--dir "<path>"`. Then **STOP**.
2. **Secrets folder** (the directory holding `qq_auth.txt` and, if you have it,
   `gmail_app_pw.txt`) → `--secrets-dir "<path>"`. Then **STOP**.

For both, the two fixed options are **Paste / drop path** and **Skip** — never a
pre-filled path; the value is dropped via "Other". The secrets folder must contain
at least `qq_auth.txt`; `gmail_app_pw.txt` is optional — if it's absent from the
folder, `run.py receipts` skips Gmail and still does QQ.

Remember both for the session; reuse them and never re-ask. If a chosen path is
wrong/empty, say so and re-ask that one. Outputs always go to the current working
directory.

---

## Stage 1 — Date range (INTERACTIVE, selector only)

Pick **start month** then **end month** — **month granularity only, no day
selection**. Every option set is computed from **today's date** by
`run.py daterange`; never ask for a typed date, and never offer a month past the
current month. Use `AskUserQuestion` selectors only.

The selectable window is the **current month and the 3 months before it** (4
months max). Start can be any month in that window; end is any month from the
start through the current month (a one-month range is fine). Because the window
is ≤4 months, each step is a single ≤4-option question — **no quarter step**.

`AskUserQuestion` needs **2–4 options** (the auto-added "Other" doesn't count). If
a step's helper returns only **one** month, you still MUST ask — do not treat a
single computed option as license to auto-pick. Present that one month plus a
second explicit option such as "Pick a different start month" (which loops back to
the prior step); never skip the question because the choice looks forced.

Run the helper for each step (override the clock only for testing with
`--today YYYY-MM-DD`). **Present every option in the EXACT order the script
returns it** — the `months` arrays are already sorted chronologically (oldest →
newest). Never reorder, re-rank, or move the "recommended" one first; the user
expects March, April, May, June in that order.

1. **Start year** — `python3 .claude/skills/split-bills/run.py daterange start-years`
   - One year returned → use it silently, no question.
   - Two returned (only when today is Jan–Mar; current year first) → **call
     `AskUserQuestion`** ("Which year does the range start in?") with the two
     years as options, then **STOP** until the user picks.

2. **Start month** — `python3 .claude/skills/split-bills/run.py daterange start-months --year <chosen-year>`
   **Call `AskUserQuestion`** ("Which month does the range start in?"), presenting
   the returned `label`s as the options in the returned (chronological) order —
   the window months in that year. Then **STOP** until the user picks.

3. **End month** — `python3 .claude/skills/split-bills/run.py daterange end-options --start <YYYY-MM>`
   **Call `AskUserQuestion`** ("Which month does the range end in?"), presenting
   the returned `label`s as the options in the returned (chronological) order —
   every month from the start through the current month, inclusive. Year is baked
   into each label, so no separate end-year step. **You must ASK this with the
   tool — never assume the end is the current month or "the full window", and
   never just print the question as text. Wait for the pick.**

   **STOP** after the start-month question until the user picks; then **STOP**
   again after the end-month question until they pick. Two separate selector
   prompts, two waits. Only once you hold BOTH a user-chosen start and a
   user-chosen end do you run `resolve`.

4. **Resolve** — `python3 .claude/skills/split-bills/run.py daterange resolve --start <YYYY-MM> --end <YYYY-MM>`
   Prints `{"since","until"}`: `since` = 1st of the start month; `until` = last
   day of the end month, or **today** if the end month is the current month
   (never the future). Use these as `--since`/`--until`. Show the resolved
   window in plain text once, then proceed.

---

## Stage 2 — BofA → bills.jsonl (AUTOMATIC)

1. Run the parser (PDF text never enters context), using the BofA folder from
   Stage 0:
   ```bash
   python3 .claude/skills/split-bills/run.py parse-bofa --dir "<BofA folder>" --since <START> --until <END>
   ```
   → `split_bill_outputs/intermediate/bofa_raw.jsonl` with
   `{date, raw_desc, amount, currency}` for each purchase.
2. Read `split_bill_outputs/intermediate/bofa_raw.jsonl` and turn each cryptic
   `raw_desc` into a clean record. **Normalize the vendor name** (see *Vendor
   normalization* below) — this is the whole point: BofA's item/amount/date are
   clean, but its vendor strings are not.
3. **Infer `item`** from the brand/category, since statements have no line items:
   restaurant → the cuisine/dish (`pho`, `coffee`), grocery → `groceries`,
   rideshare → `ride`, SaaS → `subscription`, hotel → `hotel stay`, parking →
   `parking`, etc.
4. **Write** the cleaned rows (each `{brand, item, total:"$X.XX", date,
   source:"bofa"}`) with the Write tool into
   `split_bill_outputs/intermediate/bofa_processed.jsonl`, then merge them into
   the ledger:
   ```bash
   python3 .claude/skills/split-bills/run.py add --from split_bill_outputs/intermediate/bofa_processed.jsonl
   ```
   `add` creates `…/deliverables/bills.jsonl` if absent, de-dupes, and keeps it
   date-sorted. Do NOT hand-edit `bills.jsonl` or use `python3 -c` to write it.

## Stage 3 — QQ + Gmail → bills.jsonl (AUTOMATIC)

1. Run the harvester for the SAME window, using the secrets folder from Stage 0:
   ```bash
   python3 .claude/skills/split-bills/run.py receipts --secrets-dir "<secrets folder>" --since <START> --until <END>
   ```
   → `split_bill_outputs/intermediate/email_raw.jsonl`
   (`{source, from, subject, date_header, body}` per email).
   It writes incrementally; it may take a few minutes (run it and wait).

   **Strict JSONL invariant.** `email_raw.jsonl` is **one physical line = one
   complete JSON object**. Every row is produced by real JSON serialization
   (`json.dumps`), and every email-derived field (`from`, `subject`,
   `date_header`, `body`) is normalized first — CRLF/CR/NEL/LS/PS folded to `\n`,
   invisible Unicode control/format characters (BOM, zero-width, bidi marks)
   stripped, Chinese/emoji/tabs kept, truncation applied only after that. The
   harvester then **verifies the file it just wrote** and fails loudly on any
   blank line, non-JSON line, or non-object line. Never hand-write raw email body
   text into the file. (The reader/triage side still tolerates and warns on
   malformed lines, purely to keep reading older pre-strict files.)
2. **Triage WITHOUT reading the raw file** — never open `email_raw.jsonl` with
   the Read tool (it is often >1 MB). Instead:
   ```bash
   python3 .claude/skills/split-bills/run.py triage
   ```
   That prints one compact line per email (index, source, currency flag, from,
   subject). From the subjects/senders, with your own judgment, **drop
   newsletters, promotions, and ads** (e.g. "40% off", "Member Days", bonus-miles
   offers, "GUNS FOR SALE") and keep only plausible receipts/order
   confirmations/payment emails.
3. Open just the plausible ones by index to read their bodies:
   ```bash
   python3 .claude/skills/split-bills/run.py show --indices 4,5,6,12
   ```
   For each real receipt, extract `{brand, item, total, date, source}`:
   - `brand` from the sender/subject (Anthropic, Vercel, SKIMS, Uber Eats…).
   - `item` from the body (the product/plan/dish).
   - `total` with the right symbol — `$` or `¥` (QQ mail may be RMB).
   - `date` from `date_header` → ISO.
4. **Write** those rows with the Write tool into
   `split_bill_outputs/intermediate/email_processed.jsonl`, then merge:
   ```bash
   python3 .claude/skills/split-bills/run.py add --from split_bill_outputs/intermediate/email_processed.jsonl
   ```
   `add` de-dupes against the BofA rows already present (same brand + amount +
   date → kept once, BofA preferred) and re-sorts by date. No manual appends, no
   `python3 -c`.

When Stage 3 finishes, briefly report the total counts per source. Do NOT ask the
user anything yet.

**HARD RULE — the ledger stays sorted by `date` ascending at all times.** `add`
already re-sorts on every merge, so no separate sort step is needed; if you ever
suspect it drifted, run `python3 .claude/skills/split-bills/run.py sort`.

---

## Stage 3.5 — Start day (INTERACTIVE) → trim bills.jsonl

After the **full, sorted** `bills.jsonl` exists, ask the user **which specific day
the history should start on**, then drop every row dated before it. Use
`AskUserQuestion` (one question). Per the tool's rules you need 2–4 fixed options
plus the auto-added free-text **"Other"** box — present exactly:

```
Question: Which day should the bill history start on? Type a date in the "Other"
          box (any format), or keep the first of the month.
Options:
  1. First of the month is fine   (keep everything; no trimming)
  2. Type a specific start day    (reminder to use the built-in "Other" box)
```

Interpret the answer:
- **First of the month is fine** → do not trim; keep the whole ledger.
- **Other (free text)** → the typed string is the start day. Pass it straight to
  `trim`, which accepts **any format** (`4/16`, `4.16`, `04-16`, `0416`,
  `April 16`, `2026-04-16`, …), infers the year from the ledger when omitted,
  drops rows before that day, rewrites `bills.jsonl`, and prints
  `{since, removed, remaining}`:
  ```bash
  python3 .claude/skills/split-bills/run.py trim --since "<what the user typed>"
  ```
  Report the `removed`/`remaining` counts. If `trim` prints a "Could not parse"
  error, the string was ambiguous — say so and re-ask; never guess silently.

**STOP** here: send the question and wait for the user's pick before trimming.

---

## Stage 4 — Split selection (INTERACTIVE) → split_bills.jsonl

First get the stable, numbered ledger (do not Read `bills.jsonl` directly):
```bash
python3 .claude/skills/split-bills/run.py ledger
```
Each row prints with an index `[N]`. Those indices are what you feed to `split`
below; they stay stable because both `ledger` and `split` sort identically. Go
through the ledger and ask the user, **for every line**, whether it is splittable
(a shared expense) or personal.

- **Batch = ONE simple question of exactly 3 real items, NO "None" option.** Keep
  it clean and low-misclick: each batch is a single `multiSelect: true` question
  listing **3 real ledger items** as its options. Do **not** add a "None" option,
  and do **not** stack sub-questions in one call — that expands awkwardly on
  "Next" and causes misclicks. One question, one batch; advance 3 items at a time
  through the whole list. (Last batch may hold fewer than 3 items.)
- **HARD RULE — the picker's auto-added free-text "Other" box IS the
  "none / all personal" signal.** `AskUserQuestion` always appends an "Other"
  field that cannot be removed; repurpose it instead of fighting it. Interpret the
  answer as: any **real items checked** → those are splittable; **"Other" selected
  with no real items checked** → none in this batch are splittable. If both are
  somehow selected, take the checked real items and ignore "Other".
- **HARD RULE — a blank / empty answer == "none / all personal", NOT a
  dismissal.** When the user picks "Other" and types nothing, the harness returns
  an **empty answer** (it can surface as "the user did not answer"). Do **not**
  treat this as a cancel and do **not** re-ask, pause, or ask "are we good" —
  record **zero splittable** for that batch and advance to the next batch
  automatically.
- **HARD RULE — show the FULL `item` text in every option label.** Label each as
  `brand — <full item> — total`, with the date in the option description. Never
  condense, abbreviate, or truncate the `item` (e.g. keep the complete restaurant
  name + address for Uber Eats rows).
- **HARD RULE — append to `split_bills.jsonl` as you go, via `split`.** After
  *each* batch, immediately write that batch's checked rows by their ledger index:
  ```bash
  python3 .claude/skills/split-bills/run.py split --indices 3,7
  ```
  `split` appends those exact ledger rows (unchanged) to `split_bills.jsonl`,
  creating it on the first call. Do not hand-write the file or wait until the end.
  For a batch with zero splittable items, simply call no `split` for that batch.
- At the end, report: kept N of M as splittable, and where the file is.

**STOP** at every batch: send the call and wait. Never decide for the user which
items are splittable, and never auto-classify the whole list to skip the prompts —
each item is the user's call.

---

## Vendor normalization (the cryptic-name problem)

BofA descriptors are `[<TYPE> <NNNN>] [<PROCESSOR>*]<NAME> <CITY><STATE> [phone]`.
Resolve to a real **brand** in two passes:

**Pass A — strip mechanically:**
- Leading transaction type: `MOBILE PURCHASE 0410`, `PURCHASE 0412`,
  `CHECKCARD 0411`, `RECURRING`.
- Processor prefixes (the brand is what FOLLOWS them):
  `SQ *` = Square · `TST*` = Toast (restaurant) · `CHE*` = Chegg ·
  `UEP*` / `LINK.COM*` = payment processors · `GOOGLE *` = Google service ·
  `OPENAI *` = OpenAI.
- Trailing `CITY` + 2-letter `STATE`, phone numbers, store/auth numbers.

**Pass B — identify what's left:**
- Obvious brands → use directly: `FIGMA`, `NOTION`, `ANTHROPIC`/`CLAUDE.AI`,
  `WINGSTOP`, `CHIPOTLE`, `HEYTEA`, `EREWHON`, `CVS`, `WAYMO`, `EXTRA SPACE`,
  `AMERICAN` (Airlines), `HOTEL NIKKO`, `DUKECARD`, `YOGURTLAND`.
- Cryptic/abbreviated/unknown (`SQ *PHO N MOR`, `PARKO`, `DISCORD NITROMON`,
  `UEP*THE PUBLIC IZ`, `TST* MOVITA JUICE`) → **WebSearch** `"<cleaned name>
  <city> <state>"` to find the real business, then use that brand. Examples:
  `PHO N MOR` → *Pho N More* (Vietnamese), `PARKO` → parking app,
  `DISCORD NITROMON` → *Discord* (item: Nitro subscription),
  `MOVITA JUICE` → *Movita Juice Bar*.
- If a name is still unresolvable after a lookup, keep the best cleaned form and
  move on — don't block the pipeline.

There is no free personal API for reverse-descriptor lookup (Mastercard/Visa
offer one but require issuer credentials), so the WebSearch fallback is the
intended method.

## Notes
- Only Stages 0, 1, and 4 are interactive. Never pause Stages 2–3 for input.
- Capture the BofA folder and secrets folder once in Stage 0 and reuse them for
  the whole session — don't re-ask in Stages 2/3.
- All run artifacts live under `split_bill_outputs/` in the working directory.
  `intermediate/` holds the scratch files (`bofa_raw.jsonl`,
  `bofa_processed.jsonl`, `email_raw.jsonl`, `email_processed.jsonl`); the
  deliverables are `deliverables/bills.jsonl` and `deliverables/split_bills.jsonl`.
  Each `run.py` subcommand creates the tree automatically.
- Credentials are `qq_auth.txt` / `gmail_app_pw.txt` in the user's secrets
  folder (or `$QQ_AUTH_CODE` / `$GMAIL_APP_PW`); if Gmail's is missing,
  `run.py receipts` skips Gmail and still does QQ.

---

## Validation

Before sharing or publishing this skill, run the validator (and `ruff` if it's
installed) from the project root:

```bash
python3 .claude/skills/split-bills/tools/validate_skill.py
ruff check .claude/skills/split-bills --fix
ruff format .claude/skills/split-bills
```

The skill exposes exactly **one** public entrypoint — Claude only ever calls:

```bash
python3 .claude/skills/split-bills/run.py <command> ...
```

The implementation lives in the private `scripts/` package and is never invoked
directly. Because of the single entrypoint, the skill needs just one Claude Code
permission allow rule:

```json
"Bash(python3 .claude/skills/split-bills/run.py:*)"
```

Do not require users to approve separate Bash rules for internal modules such as
`daterange.py`, `parse_bofa.py`, or `receipts.py`.

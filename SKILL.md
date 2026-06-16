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

The Permissions preflight and the interactive stages (0, 1, 3.5, 4) are
**mandatory STOP points**. At each one, every value comes from the user's reply
**in this session** — a path, a month, a start day, a split choice. Ask the
question, then wait for that reply before continuing.

The one thing you may reuse without re-asking is an answer the user already gave
you earlier in this same session (e.g. a path captured in Stage 0). Anything you
haven't been told yet, you ask for. When in doubt, ask.

Each interactive stage below ends with a **STOP** line — when you reach it, send
the question and end your turn. Work one stage at a time, in order.

## Files & where things live

**Skill code** lives in this skill folder (the directory that holds this
SKILL.md — currently `.claude/skills/split-bills/`). There is a **single
entrypoint**, `run.py`; the stage logic lives in the private `scripts/` package
(functions only — never invoked directly). Always call `run.py` and a subcommand,
e.g. `python3 .claude/skills/split-bills/run.py parse-bofa …`. If the folder ever
moves, use its new path; the commands below assume `.claude/skills/split-bills/`:
- `run.py daterange <start-years|start-months|end-options|start-days|resolve>` —
  computes Stage 1 selector options (valid start years/months, end months, and the
  resolved `--since`/`--until`) from today's date, plus the Stage 3.5 `start-days`
  options (1st + Mondays of the start month); prints JSON.
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
  date ascending. There are only ever **two** processed files written by hand:
  `bofa_processed.jsonl` and `email_processed.jsonl` — one BofA, one email, each
  produced directly from its `_raw` counterpart.
- `run.py sort` / `run.py trim --since <date>` / `run.py ledger` — sort, trim by
  start day (flexible date parsing), and print the numbered date-sorted ledger.
- `run.py split --indices 0,3,7` — appends the chosen ledger rows to
  `…/deliverables/split_bills.jsonl` (Stage 4).

**⛔ HARD RULE — `run.py` is the ONLY script you run.** Call exactly one
`run.py <subcommand>` per Bash command — each prints its own summary, so a single
clean command does the job. The one allow rule covers every subcommand and
argument, keeping the run prompt-free. To put rows in the ledger, compose them with
the **Write tool** into the matching `…/intermediate/<bofa|email>_processed.jsonl`
file, then `run.py add --from <that file>`.

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
{"brand": "UberEats", "item": "poke bowl", "total": "$18.52", "date": "2026-04-13", "source": "bofa", "card": "bofa"}
```
- **brand** — **whoever takes the money**, as a recognizable name (NOT the raw
  descriptor). Food ordered through a platform → brand = the platform (e.g.
  UberEats) and the restaurant/dish goes in `item`; paid the restaurant directly
  (in person / its own site) → the restaurant is the brand.
- **item** — what was bought (`groceries`, `1 yr subscription`, a dish, clothing…).
- **total** — string with currency symbol, `$` or `¥` (RMB).
- **date** — ISO `YYYY-MM-DD`.
- **source** — `bofa` | `qq` | `gmail` (helps dedupe & trace).
- **card** — which card paid. For a **BofA** row, always the literal `"bofa"`. For
  an **email receipt**, the card's **last 4 digits** when the body shows them
  (e.g. `Visa ••••9261`, `ending in 9920`, `************7525` → `"9261"` /
  `"9920"` / `"7525"`); if no card is shown, use `""`. Never guess the digits.
- **unverified** — *optional* boolean. Set `true` on a row whose vendor you could
  only guess (see *Vendor normalization*); omit it on confident rows. `ledger`
  flags these with a `⚠` for the user to eyeball.

---

## Stage 0 — Locate inputs (INTERACTIVE) — do this FIRST

You need **two paths** from the user, asked one at a time in **plain text** — no
`AskUserQuestion`, no options. Send the pre-written line, end your turn, and resume
when the user replies (they paste or drag-and-drop the path).

1. **BofA folder** — send verbatim:
   > Paste the path to your **Bank of America statements folder** (the folder of PDF eStatements).

   **STOP** and wait; the reply becomes `--dir "<path>"`.
2. **Secrets folder** — send verbatim:
   > Paste the path to your **secrets folder** (holds `qq_auth.txt`, optionally `gmail_app_pw.txt`).

   **STOP** and wait; the reply becomes `--secrets-dir "<path>"`.

The secrets folder needs at least `qq_auth.txt`; without `gmail_app_pw.txt`,
`run.py receipts` does QQ only. Reuse both paths for the rest of the session; if one
turns out wrong/empty, say so and ask again. Outputs go to the current working
directory.

---

## Stage 1 — Date range (INTERACTIVE, selector only)

Pick **start month** then **end month** — **month granularity only**. Every option
set is computed from **today's date** by `run.py daterange`, and you present it with
`AskUserQuestion` selectors. The options the script returns already stop at the
current month, so just offer what it gives you.

The selectable window is the **current month and the 3 months before it** (4
months max). Start can be any month in that window; end is any month from the
start through the current month (a one-month range is fine). Because the window
is ≤4 months, each step is a single ≤4-option question — **no quarter step**.

`AskUserQuestion` needs **2–4 options** (the auto-added "Other" doesn't count). When
a step's helper returns only **one** month, still ask: present that month plus a
second option like "Pick a different start month" (which loops back a step), and let
the user choose.

Run the helper for each step (override the clock only for testing with
`--today YYYY-MM-DD`). **Present options in the exact order the script returns
them** — the `months` arrays are already chronological (oldest → newest), e.g.
March, April, May, June.

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
   the returned `label`s in order — every month from the start through the current
   month, inclusive (the year is baked into each label). Send it as a real selector
   and use the month the user picks.

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
   `parking`, etc. **Only when the vendor is confirmed** — if you couldn't verify
   it, mark the row `unverified` and use `item:"unknown"` (see the no-fabrication
   HARD RULE in *Vendor normalization*).
4. **Write** the cleaned rows (each `{brand, item, total:"$X.XX", date,
   source:"bofa", card:"bofa"}`, plus `"unverified": true` on any you couldn't
   confirm) with
   the Write tool into `split_bill_outputs/intermediate/bofa_processed.jsonl`,
   then merge them into the ledger:
   ```bash
   python3 .claude/skills/split-bills/run.py add --from split_bill_outputs/intermediate/bofa_processed.jsonl
   ```
   `add` creates `…/deliverables/bills.jsonl` if absent, de-dupes, and keeps it
   date-sorted.
5. **Report unverified vendors.** Run `run.py ledger`, then tell the user how many
   rows are `⚠ unverified` and list their brands, so they can correct any before
   splitting.

## Stage 3 — QQ + Gmail → bills.jsonl (AUTOMATIC)

1. Run the harvester for the SAME window, using the secrets folder from Stage 0:
   ```bash
   python3 .claude/skills/split-bills/run.py receipts --secrets-dir "<secrets folder>" --since <START> --until <END>
   ```
   → `split_bill_outputs/intermediate/email_raw.jsonl`
   (`{source, from, subject, date_header, body}` per email).
   It writes incrementally; it may take a few minutes (run it and wait).

   `receipts` writes verified strict JSONL (one JSON object per line) and you read
   it back through `triage`/`show` below — so let the harvester own that file and
   work from its subcommands.
Now turn `email_raw.jsonl` into its processed counterpart,
`split_bill_outputs/intermediate/email_processed.jsonl` — the email twin of
`bofa_processed.jsonl` — by going through the emails once:

2. Scan the inbox with `triage` (it keeps the often >1 MB raw file out of context,
   so read it this way rather than with the Read tool):
   ```bash
   python3 .claude/skills/split-bills/run.py triage
   ```
   It prints one compact line per email (index, source, currency flag, from,
   subject). Keep the genuine receipts, order confirmations, and payment emails;
   let the newsletters, promotions, and ads (e.g. "40% off", "Member Days",
   bonus-miles offers, "GUNS FOR SALE") fall away.
3. Read the bodies of the ones you kept:
   ```bash
   python3 .claude/skills/split-bills/run.py show --indices 4,5,6,12
   ```
   Turn each into one row `{brand, item, total, date, source, card}` — `brand`
   from the sender/subject (Anthropic, Vercel, SKIMS, Uber Eats…), `item`/`total`
   from the body (`$` or `¥` as written), `date` from `date_header` as ISO, and
   `card` = the last 4 digits if the body shows them (`Visa ••••9261` → `"9261"`),
   else `""`.

   **Vendor specifics** (apply only when the email actually shows it — invent nothing):
   - **Food platforms** (UberEats, DoorDash, Grubhub…) — brand = the platform;
     `item` = the restaurant + dish (e.g. brand `UberEats`, item `Wingstop — 8pc combo`).
   - **UberEats** — also include the **delivered time** in `item` when the email shows it.
   - **Rideshare** (Uber, Lyft, Waymo) — put as much **location** as the email gives
     into `item`: best is depart + destination; otherwise at least the city.
4. Collect those rows into the single file `email_processed.jsonl`, then merge it
   into the ledger:
   ```bash
   python3 .claude/skills/split-bills/run.py add --from split_bill_outputs/intermediate/email_processed.jsonl
   ```
   `add` de-dupes against the BofA rows already present (same brand + amount +
   date → kept once, BofA preferred) and re-sorts by date.

When Stage 3 finishes, briefly report the total counts per source. Do NOT ask the
user anything yet.

`add` keeps the ledger sorted by date on every merge, so there's no separate sort
step; if you ever need to re-sort, run
`python3 .claude/skills/split-bills/run.py sort`.

---

## Stage 3.5 — Start day (INTERACTIVE) → trim bills.jsonl

After the **full, sorted** `bills.jsonl` exists, ask the user **which day the
history should start on**, then drop every row before it.

First get the candidate days for the **start month** (the start month from Stage 1):
```bash
python3 .claude/skills/split-bills/run.py daterange start-days --start <YYYY-MM>
```
It returns `[{label, value}]` — the **1st**, then each **Monday**, oldest first
(value = ISO date). Take the **first four** (1st + first 3 Mondays) as the
`AskUserQuestion` options; the auto-added **"Other"** box covers a later Monday or
any custom day.

**Ask (verbatim):**
> Which day should the bill history start on? Pick one, or type any date in "Other".

Options — use the returned `label`s, in order:
- `1st — <Mon> 1` (keep everything; no trimming)
- `Mon <Mon> <d>` · `Mon <Mon> <d>` · `Mon <Mon> <d>` (each option's `value` is its ISO start day)

Interpret the answer:
- **The 1st option** → do not trim; keep the whole ledger.
- **A Monday option** → trim to that option's `value` (ISO date).
- **Other (free text)** → the typed string is the start day (e.g. a later Monday).

For a Monday option or "Other", pass the date straight to `trim` — it accepts the
ISO `value` **or** any loose format (`4/16`, `April 16`, `0416`, …), infers the
year from the ledger, rewrites `bills.jsonl`, and prints `{since, removed, remaining}`:
```bash
python3 .claude/skills/split-bills/run.py trim --since "<ISO value, or what the user typed>"
```
Report the `removed`/`remaining` counts. If `trim` prints a "Could not parse"
error, say so and re-ask; never guess silently.

**STOP** here: send the question and wait for the user's pick before trimming.

---

## Stage 4 — Split selection (INTERACTIVE) → split_bills.jsonl

First get the stable, numbered ledger with `ledger`:
```bash
python3 .claude/skills/split-bills/run.py ledger
```
Each row prints with an index `[N]`; those indices feed `split` below and stay
stable because both `ledger` and `split` sort identically. Go through the ledger
and ask the user, **for every line**, whether it is splittable (a shared expense)
or personal.

**Ask (verbatim) for each batch:**
> Which of these are **splittable** (shared)? Check the shared ones — leave a row unchecked to keep it personal.

- **One batch = one `multiSelect` question of 3 real ledger items.** Advance 3 at a
  time through the whole list (the last batch may hold fewer). Keep each batch a
  single flat question — that's the low-misclick shape.
- **The picker's auto-added "Other" box is your "none / all personal" signal.**
  `AskUserQuestion` always appends an "Other" field; use it. Read the answer as:
  real items checked → those are splittable; "Other" with nothing real checked →
  none in this batch. If both appear, take the checked items and ignore "Other".
- **A blank / empty answer means "none / all personal."** When the user picks
  "Other" and types nothing, the harness returns an empty answer (it may surface as
  "the user did not answer"). Record zero splittable for that batch and move on to
  the next batch automatically — it's a valid answer.
- **Label each option with the full `item` text:** `brand — <full item> — total`,
  with the date in the description (keep the complete restaurant name + address for
  Uber Eats rows).
- **Write each batch's picks as you go, via `split`.** After every batch, write
  that batch's checked rows by their ledger index:
  ```bash
  python3 .claude/skills/split-bills/run.py split --indices 3,7
  ```
  `split` appends those exact ledger rows to `split_bills.jsonl`, creating it on
  the first call. For a batch with nothing splittable, just skip the `split` call.
- At the end, report: kept N of M as splittable, and where the file is.

**STOP** at every batch: send the question and wait. Each item's splittable /
personal call is the user's — ask every batch.

---

## Vendor normalization (the cryptic-name problem)

BofA descriptors are `[<TYPE> <NNNN>] [<PROCESSOR>*]<NAME> <CITY><STATE> [phone]`.
Resolve to a real **brand** in two passes:

**Pass A — strip mechanically:**
- Leading transaction type — strip it from `brand`, but **carry its meaning into
  `item`** as a short phrase. The 4 digits right after it are the `MMDD`, not a
  code to keep:
  - `MOBILE PURCHASE` — tapped a mobile wallet (Apple/Google Pay) in person →
    e.g. "apple paid on the spot".
  - `PURCHASE` — physical card used in person → e.g. "paid in person".
  - `CHECKCARD` — debit card keyed, often card-not-present → e.g. "online order"
    (only when it fits; don't assert online for a clear storefront).
  - `RECURRING` — an automatic subscription charge → e.g. "recurring subscription".
- Processor prefixes (the brand is what FOLLOWS them):
  `SQ *` = Square · `TST*` = Toast (restaurant) · `CHE*` = Chegg ·
  `UEP*` / `LINK.COM*` = payment processors · `GOOGLE *` = Google service ·
  `OPENAI *` = OpenAI.
- Trailing `CITY` + 2-letter `STATE`, phone numbers, store/auth numbers.

**Pass B — identify what's left, then build a rich `brand`:**
- Obvious brands → use directly: `FIGMA`, `NOTION`, `ANTHROPIC`/`CLAUDE.AI`,
  `WINGSTOP`, `CHIPOTLE`, `HEYTEA`, `EREWHON`, `CVS`, `WAYMO`, `EXTRA SPACE`,
  `AMERICAN` (Airlines), `HOTEL NIKKO`, `DUKECARD`, `YOGURTLAND`.
- Cryptic/abbreviated/unknown (`SQ *PHO N MOR`, `PARKO`, `DISCORD NITROMON`,
  `UEP*THE PUBLIC IZ`, `TST* MOVITA JUICE`) → **WebSearch** to identify the real
  business. **Search technique:** searching the whole descriptor (codes and all)
  returns nothing — isolate the part that is *neither a code nor a location* (that
  is the vendor name) and search **that name with the location**, e.g.
  `fast times venice CA`, not `fast times`. The location usually disambiguates.

**Build `brand` = name + category + location** once identified — e.g.
`MOBILE PURCHASE 0428 SQ *FAST TIMES Venice CA` → `Fast Times (coffee shop, Venice CA)`.
For an internet service with no physical location use `online` (most descriptors
still carry a state code). If you can't get all three with confidence, keep the
original descriptor in `brand` and flag the row (see the HARD RULE below) — never
invent a category or a fuller name.

**⛔ HARD RULE — flag any vendor you can't verify; an honest "unknown" beats a
confident guess.** A vendor counts as verified only when it's an obvious known
brand or a WebSearch returns a clear matching business. For anything short of that
(e.g. `SPICY EVERY DAY LOS ANGELES` with no convincing hit):
1. Keep `brand` as the cleaned descriptor verbatim (Pass A output, e.g.
   `Spicy Every Day`) — the literal name, nothing embellished.
2. Set `item` to `"unknown"`.
3. Add `"unverified": true`.
Verified rows omit `unverified`. The `ledger` `⚠` and your Stage 2/3 report surface
these for the user to confirm.

**No auto-expansion (BofA *and* email).** Never lengthen or "correct" an
abbreviated vendor name unless a WebSearch confirms the longer form. A short name
is often the real one — e.g. `pho n mor` stays `Pho N Mor`, **not** `Pho N More`,
until a match proves the expansion. Same for email senders: take the name as
written unless you've verified a fuller one.

There is no free personal API for reverse-descriptor lookup (Mastercard/Visa
offer one but require issuer credentials), so the WebSearch fallback is the
intended method.

## Notes
- Stages 0, 1, 3.5, and 4 are interactive; Stages 2–3 run start to finish without
  pausing for input.
- Capture the BofA folder and secrets folder once in Stage 0 and reuse them all
  session.
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

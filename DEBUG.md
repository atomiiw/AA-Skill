# DEBUG — split-bills trials & improvements

## 1. 2026-06-14 — Stage 0 file-path input: picker → plain ask
- **Issue:** Stage 0 collected the BofA folder and secrets folder paths through an
  `AskUserQuestion` 2-option picker ("Paste / drop path" + "Skip"). A file path is
  free text, so the menu added friction with no benefit.
- **Demand:** make the file-path steps a plain pause-and-resume — ask for the path
  in plain text, STOP, and resume skill execution when the user provides it. No
  selection UI.

## 2. 2026-06-14 — Glanceable wording for interactive steps
- **Issue:** the text shown to the user at each interactive step (Stage 0 path
  asks, Stage 1 month selectors, Stage 3.5 start-day, Stage 4 split batches) may be
  longer/wordier than needed.
- **Demand:** do a run-through of every interactive step's user-facing language and
  make sure each prompt is readable at a glance — short, scannable, no wall of text.

## 3. 2026-06-14 — Add card field to each bill
- **Demand:** carry one more piece of info per bill — the card used. For an email
  receipt, capture the card's **last 4 digits** when the receipt shows them; for a
  BofA row, just write `bofa`. (i.e. extend the output schema with a `card` field:
  last-4 for email receipts, `bofa` for BofA.)

## 4. 2026-06-14 — Pre-write every interactive prompt
- **Demand:** make every interactive step's user-facing prompt pre-written.

## 5. 2026-06-14 — Stage 3.5 start-day options: offer the month's Mondays
- **Demand:** for "Which day should the bill history start on?", offer one option
  per Monday in the month (e.g. April → 4/6, 4/13, 4/20, 4/27), plus "first of the
  month", plus a blank field for the user to type a custom day.

## 6. 2026-06-14 — Decode txn-type into `item`; richer `brand` (name + category + location)
- **Part 1 (`item`):** first figure out what the transaction-type keywords mean —
  `PURCHASE`, `MOBILE PURCHASE`, `CHECKCARD` — and reflect that nuance in the `item`
  field as a short matching phrase (e.g. "apple paid on the spot", "online ordered").
- **Part 2 (`brand`):** look the vendor up online using the FULL descriptor
  **including location** — e.g. for `MOBILE PURCHASE 0428 SQ *FAST TIMES Venice CA`,
  search "fast times venice CA", not just "fast times". Then set `brand` to
  name + category + location — e.g. "Fast Times" (brand) + "coffee shop" (category)
  + "Venice CA" (location). For internet services with no location, write "online";
  most should have at least a state code. If you can't provide all three, keep the
  original descriptor in `brand` to show there's no match.
- **Search technique:** searching the entire descriptor with its codes returns
  nothing. Identify the part of the descriptor that is neither a code nor a location
  — that isolates the vendor name — and search that vendor name to find out what the
  vendor is. Sometimes adding the location alongside gives a more accurate result.

## 7. 2026-06-14 — Email rideshare (Uber/Lyft/Waymo): include location
- **Demand:** for Uber/Lyft/Waymo items from email, include as much location info as
  the email provides (don't make anything up if it's not there). Best case: the
  depart location and the destination. Second best: at least the city.

## 8. 2026-06-14 — No auto-expansion of vendor names without an internet match
- **Demand:** in both email and BofA, do not auto-expand vendor names unless proven
  with an internet search. E.g. `pho n mor` is the full name, but it always gets
  written `pho n more` — don't do that without a confirmed match.

## 9. 2026-06-14 — UberEats (email): include delivered time
- **Demand:** for UberEats items from email, include the delivered time for any time
  info available.

## 10. 2026-06-14 — `brand` = whoever takes the money (food: the ordering platform)
- **Demand:** `brand` means whoever takes the money. If I order Wingstop from
  UberEats, the platform takes the money, so `brand` = UberEats and `item` =
  Wingstop. For food, the brand is always the platform I ordered on, unless I paid
  offline at a restaurant.


## 11. 2026-06-14 — Required dependency (pdftotext) handling
- **Situation:** `parse-bofa` shells out to `pdftotext` (from Poppler), a system
  binary that isn't pip/env-installable, so today it needs a manual
  `brew install poppler`. Options discussed: have `run.py` detect-and-install it (a
  child process, so it stays under the single run.py allow rule, no extra prompt), or
  switch PDF parsing to a pip-installable Python extractor; caveats are system
  mutation, brew-absent / non-mac, and network.
- **Demand:** look up online how other skills conventionally take care of a required
  dependency.

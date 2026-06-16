# split-bills

A Claude Code skill that builds one expense ledger from your **Bank of America PDF
statements**, **QQ mail**, and **Gmail receipts**, then walks you through picking
which bills to split. Along the way it turns cryptic card-statement names like
`SQ *PHO N MOR` into real brands.

## Install

Clone it into your Claude Code skills folder (keep the folder named `split-bills`):

```bash
git clone <repo-url> ~/.claude/skills/split-bills
```

## Use

Open Claude Code and ask to "track and split my bills" (or run `/split-bills`).
It's interactive: it asks for your statement folder and a date range, gathers
everything, and lets you check off what's splittable. Results land in
`split_bill_outputs/deliverables/`.

## What you'll need

- **pdftotext** (from Poppler) to read the BofA PDFs. The skill checks for it up
  front and, if it's missing, prints the install command for your OS:
  - macOS: `brew install poppler`
  - Debian/Ubuntu: `sudo apt-get install -y poppler-utils`
  - Fedora: `sudo dnf install -y poppler-utils`
  - Windows: `winget install poppler` (or `conda install -c conda-forge poppler`)
- For the email step (optional): a **QQ IMAP code** and a **Gmail app password**,
  kept together in one folder you point the skill at.

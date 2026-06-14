#!/usr/bin/env python3
"""
Harvest receipt-like emails from QQ + Gmail (IMAP, read-only) into candidates.jsonl.

Per account: server-side keyword search inside the date window, then keep only
mail whose text also has a currency sign, then write one strict JSON line each.
Amounts/vendors are NOT parsed here — Claude reads candidates.jsonl afterwards.

Functions-only module; the front door is ../run.py -> harvest(). Auth resolves
per account as: explicit file path, then $ENV, then <secrets_dir>/<file>. See
SKILL.md for the full auth / Gmail app-password / output details.
"""

import contextlib
import email
import html
import imaplib
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from email.header import decode_header


def _load_secret(env_name, filename, secrets_dir, explicit=None):
    """Resolve a secret: explicit file path, then $ENV, then <secrets-dir>/file."""
    if explicit:
        path = os.path.expanduser(explicit)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read().strip()
        print(f"  (no file at {path})")
        return ""
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    path = os.path.join(os.path.expanduser(secrets_dir), filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    return ""


# auth is filled in by harvest() once secrets_dir / qq_auth / gmail_pw are known;
# "auth_env" / "auth_file" tell _load_secret where to look per account.
ACCOUNTS = [
    {
        "name": "qq",
        "host": "imap.qq.com",
        "port": 993,
        "email": "xiaoaojianghu1357@qq.com",
        "mailbox": "INBOX",
        "auth_env": "QQ_AUTH_CODE",
        "auth_file": "qq_auth.txt",
    },
    {
        "name": "gmail",
        "host": "imap.gmail.com",
        "port": 993,
        "email": "maidouatomwang@gmail.com",
        # Sentinel: auto-detect the "All Mail" folder by its \All flag, so receipts
        # that filters auto-archive are found. (Gmail localizes the folder name.)
        "mailbox": r"\All",
        "auth_env": "GMAIL_APP_PW",
        "auth_file": "gmail_app_pw.txt",
    },
]

# An email is a candidate only if its text contains one of these currency signals.
CURRENCY_RE = re.compile(r"\$|¥|￥|(?:\bRMB\b)|(?:\bCNY\b)|(?:\bUSD\b)|元", re.IGNORECASE)

# PRELIMINARY keyword gate (server-side): only DOWNLOAD emails that match at least
# one of these. This avoids fetching the whole mailbox. The currency gate is
# still applied afterward, on the downloaded text, as a second filter.
KEYWORDS = [
    # English
    "receipt",
    "invoice",
    "order",
    "payment",
    "purchase",
    "transaction",
    "refund",
    "subscription",
    "renewal",
    "renew",
    "billed",
    "charged",
    # Chinese
    "收据",
    "账单",
    "付款",
    "订单",
    "发票",
    "消费",
    "交易",
    "支付",
    "扣款",
    "订阅",
    "续费",
    "会员",
    "扣费",
    "预订",
]


def decode_mime(value):
    """Decode an RFC2047-encoded header into a readable string."""
    if not value:
        return ""
    out = []
    for text, enc in decode_header(value):
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def extract_body_text(msg):
    """Extract plain text from an email.message.Message, preferring text/plain."""
    plain, html_text = [], []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition", "").startswith("attachment"):
                continue
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ctype == "text/plain":
                plain.append(decoded)
            elif ctype == "text/html":
                html_text.append(decoded)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            (plain if msg.get_content_type() == "text/plain" else html_text).append(decoded)

    text = "\n".join(plain) if plain else "\n".join(html_text)
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)  # drop script/style
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)  # br -> newline
    text = re.sub(r"<[^>]+>", " ", text)  # strip tags
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)  # collapse runs of spaces/tabs
    text = re.sub(r"\n\s*\n+", "\n", text)  # collapse blank lines
    return text.strip()


# Line breaks that must all collapse to a single '\n' before serialization:
# CRLF, lone CR, NEL (U+0085), LINE SEPARATOR (U+2028), PARAGRAPH SEPARATOR (U+2029).
_LINEBREAKS_RE = re.compile("\r\n|[\r\u0085\u2028\u2029]")
_KEEP_CONTROL = {"\t", "\n"}  # the only control chars we keep as real content


def normalize_jsonl_text(value):
    """Normalize raw email text before JSONL serialization. Keeps tab/newline,
    folds every line-break variant to '\n', drops invisible control/format chars;
    caller truncates AFTER this so a body is never cut mid-escape."""
    if not value:
        return ""
    out = []
    for ch in _LINEBREAKS_RE.sub("\n", value):
        # drop control (Cc), invisible-format (Cf) and lone-surrogate (Cs) chars;
        # Cs would otherwise crash the utf-8 write.
        if ch in _KEEP_CONTROL or unicodedata.category(ch) not in ("Cc", "Cf", "Cs"):
            out.append(ch)
    return "".join(out)


def dump_jsonl(record):
    """Serialize ONE record to a single JSONL line (real JSON, no trailing '\n').
    Safety valve: json.dumps already escapes newlines, but reject any that slip
    through so one record can never become two physical lines."""
    line = json.dumps(record, ensure_ascii=False)
    if any(sep in line for sep in ("\n", "\r", "\u2028", "\u2029")):
        raise ValueError("serialized record contains a raw line separator; refusing to write")
    return line


def append_candidate(f, candidate):
    """Append one candidate as a single JSON line; flush so the file grows live."""
    f.write(dump_jsonl(candidate) + "\n")
    f.flush()  # cheap: makes the row visible to a watcher; no per-row fsync()


def search_ids(M, base_criteria, keywords):
    """Server-side union search: (date window) AND (any one keyword).

    One IMAP SEARCH per keyword; union the matching message IDs so we only
    download receipt-ish mail. ASCII keywords use a plain SEARCH (universally
    supported); non-ASCII (e.g. Chinese) keywords need CHARSET UTF-8, which not
    every server accepts.

      - If NO search runs successfully, fall back to a full date-window scan.
      - If only the UTF-8 ones fail, warn (some non-Latin receipts may be
        missed) but keep the keyword results we did get.
      - An empty-but-successful search is a valid answer, NOT a reason to fall
        back to a full scan.
    """
    seen = set()
    ran_ok = False  # at least one SEARCH returned OK
    utf8_attempted = utf8_ok = False
    for kw in keywords:
        is_ascii = kw.isascii()
        try:
            if is_ascii:
                typ, data = M.search(None, *base_criteria, "TEXT", kw)
            else:
                utf8_attempted = True
                typ, data = M.search("UTF-8", *base_criteria, "TEXT", kw.encode("utf-8"))
        except imaplib.IMAP4.error:
            continue
        if typ != "OK":
            continue
        ran_ok = True
        if not is_ascii:
            utf8_ok = True
        if data and data[0]:
            seen.update(data[0].split())

    if not ran_ok:
        print("  (keyword search unsupported by server — falling back to full scan)")
        try:
            typ, data = M.search(None, "(" + " ".join(base_criteria) + ")")
        except imaplib.IMAP4.error:
            return []
        return data[0].split() if (typ == "OK" and data and data[0]) else []

    if utf8_attempted and not utf8_ok:
        print(
            "  (server rejected non-ASCII keyword search — some Chinese-only "
            "receipts may be missed)"
        )
    return sorted(seen, key=lambda b: int(b))


def resolve_mailbox(M, wanted):
    """Resolve a mailbox name to SELECT.

    The sentinel r'\\All' auto-detects the provider's "All Mail" folder via its
    \\All special-use flag — Gmail localizes that folder name (e.g. Chinese), so
    we can't hardcode it. Falls back to INBOX if not found.
    """
    if wanted != r"\All":
        return wanted
    typ, boxes = M.list()
    if typ == "OK" and boxes:
        for b in boxes:
            line = b.decode(errors="replace") if isinstance(b, bytes) else b
            if r"\All" in line:
                m = re.search(r'"([^"]*)"\s*$', line)  # last quoted token = folder name
                if m:
                    return '"' + m.group(1) + '"'
    print("  (could not find All-Mail folder — using INBOX)")
    return "INBOX"


def parse_date(s, label):
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise SystemExit(f"Could not parse {label} '{s}'. Use YYYY-MM-DD, e.g. 2026-04-01.")


def build_candidate(msg, source, max_chars):
    """Turn one fetched email into a candidate record, or None if it has no money
    sign. Every email-derived field is normalized before the body is truncated."""
    body = normalize_jsonl_text(extract_body_text(msg))
    subject = normalize_jsonl_text(decode_mime(msg.get("Subject")))
    if not CURRENCY_RE.search(subject + "\n" + body):
        return None
    return {
        "source": source,
        "from": normalize_jsonl_text(decode_mime(msg.get("From"))),
        "subject": subject,
        "date_header": normalize_jsonl_text(msg.get("Date", "")),
        "body": body[:max_chars],
    }


def pull_account(account, base_criteria, max_chars, out):
    """Scan ONE mailbox with the shared KEYWORDS + currency gate; append hits.

    Returns the number of candidates kept for this account. Both accounts use
    the identical KEYWORDS list and the identical IMAP TEXT search (which spans
    header + body), so QQ and Gmail are treated the same way.
    """
    name, host, port = account["name"], account["host"], account["port"]
    email_addr, auth, mailbox = account["email"], account["auth"], account["mailbox"]

    if not auth:
        print(
            f"[{name}] no auth code set — skipping. "
            f"(Set the env var or sibling file shown in CONFIG to enable.)\n"
        )
        return 0

    print(f"[{name}] connecting to {host} as {email_addr} ...")
    M = imaplib.IMAP4_SSL(host, port)
    M.login(email_addr, auth)
    with contextlib.suppress(Exception):
        M._simple_command("ID", '("name" "receipts-script" "version" "2.0")')
    # read-only: fetching must not mark the user's mail as read.
    mailbox = resolve_mailbox(M, mailbox)
    M.select(mailbox, readonly=True)

    ids = search_ids(M, base_criteria, KEYWORDS)
    print(
        f"[{name}] {len(ids)} emails matched a receipt keyword; "
        f"checking each for a currency sign ..."
    )

    count = 0
    for num in ids:
        typ, msg_data = M.fetch(num, "(RFC822)")
        if typ != "OK" or not msg_data or not msg_data[0]:
            continue
        candidate = build_candidate(email.message_from_bytes(msg_data[0][1]), name, max_chars)
        if candidate is None:  # no currency sign — skip
            continue
        append_candidate(out, candidate)
        count += 1
        print(f"  + [{name} {count}] {candidate['subject'][:70]}")

    M.logout()
    print(f"[{name}] kept {count} candidates.\n")
    return count


def harvest(
    since=None,
    until=None,
    secrets_dir=".",
    qq_auth=None,
    gmail_pw=None,
    out="candidates.jsonl",
    max_chars=6000,
    only=None,
):
    """Harvest receipt candidates from QQ + Gmail into `out`, return total kept.

    `since`/`until` are inclusive "YYYY-MM-DD" strings (defaults: 12 months ago /
    today). `only` is an iterable of account names to restrict to (e.g. {"qq"}).
    """
    since_dt = parse_date(since, "--since") if since else datetime.now() - timedelta(days=365)
    until_dt = parse_date(until, "--until") + timedelta(days=1) if until else None

    base_criteria = ["SINCE", since_dt.strftime("%d-%b-%Y")]
    if until_dt:
        base_criteria += ["BEFORE", until_dt.strftime("%d-%b-%Y")]

    explicit = {"qq": qq_auth, "gmail": gmail_pw}
    only = set(only) if only else None
    accounts = []
    for a in ACCOUNTS:
        if only is not None and a["name"] not in only:
            continue
        auth = _load_secret(a["auth_env"], a["auth_file"], secrets_dir, explicit.get(a["name"]))
        accounts.append({**a, "auth": auth})

    window = f"{since_dt.strftime('%Y-%m-%d')} to {until or 'today'}"
    print(f"Window: {window}")
    print(f"Accounts: {', '.join(a['name'] for a in accounts)}\n")

    out_path = os.path.expanduser(out)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    total = 0
    # truncate/create now so the file is visible immediately and grows live.
    with open(out_path, "w", encoding="utf-8") as fh:
        print(f"Created {out_path} — watching it grow as candidates are found.\n")
        for account in accounts:
            try:
                total += pull_account(account, base_criteria, max_chars, fh)
            except Exception as e:
                print(f"[{account['name']}] ERROR: {e}\n")

    print(f"Done. Kept {total} candidate emails total across {len(accounts)} account(s).")
    print(f"Wrote -> {out_path}")

    # Strict writer-side gate: the file we just produced MUST be valid JSONL
    # (one JSON object per physical line). Fail loudly if not — never ship a
    # broken file that crashes the reader later.
    from scripts.candidates import verify_jsonl

    ok, errors = verify_jsonl(out_path)
    if ok:
        print(f"Strict JSONL check: PASS ({out_path}: one JSON object per line).")
    else:
        print(f"Strict JSONL check: FAIL — {len(errors)} bad line(s) in {out_path}:")
        for err in errors:
            print(f"  {err}")
        raise SystemExit(1)

    print("Next: tell Claude to read candidates.jsonl and build the table.")
    return total

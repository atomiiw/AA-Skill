#!/usr/bin/env python3
"""
Validate the split-bills skill before sharing it.

Run:  python3 .claude/skills/split-bills/tools/validate_skill.py

Checks (PASS / WARN / FAIL):
  * SKILL.md and run.py exist; scripts/__init__.py exists
  * every .py under the skill parses (syntax)
  * the scripts/ package imports cleanly (catches import errors, not just syntax)
  * every .py file named in SKILL.md actually exists somewhere in the skill
  * SKILL.md routes Claude through run.py, not the internal modules directly
  * SKILL.md documents the single run.py wildcard permission rule (and not stale
    per-module rules)
  * SKILL.md has no interactive-flow phrasing that assumes unavailable UI
  * basic Markdown hygiene (headings, tabs, long lines) outside code fences

Exit code 1 if there are any FAILs, else 0. Standard library only.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SKILL_DIR_REF = ".claude/skills/split-bills"
RUN_PERMISSION = f"Bash(python3 {SKILL_DIR_REF}/run.py:*)"
INTERNAL_MODULES = ["daterange.py", "parse_bofa.py", "receipts.py", "candidates.py", "ledger.py"]

RISKY_PHRASES = [
    "folder picker",
    "blank folder",
    "blank input",
    "single option",
    "only one option",
    "drop a folder field",
    "drag-and-drop folder widget",
]


def pass_msg(msg: str) -> None:
    print(f"PASS: {msg}")


def warn_msg(msg: str) -> None:
    print(f"WARN: {msg}")


def fail_msg(msg: str) -> None:
    print(f"FAIL: {msg}")


def iter_non_fenced(lines: list[str]):
    """Yield (lineno, text) for lines OUTSIDE ``` fenced code blocks."""
    in_fence = False
    for idx, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield idx, line


def check_jsonl_writer(skill_root: Path, failures: list[str]) -> None:
    """Regression: hostile email text must serialize to strict one-line JSONL.

    Feeds records full of CRLF, lone CR, NEL/LS/PS, Chinese, emoji, tabs, an
    over-long body, and invisible bidi/zero-width/BOM marks through the writer's
    clean_text + dump_jsonl, then confirms the file is exactly one physical line
    per record and passes the strict verify_jsonl gate. All hostile characters are
    spelled with explicit \\u escapes so the test source itself stays clean ASCII.
    """
    import json as _json
    import os as _os
    import tempfile

    # Invisible / line-break characters that clean_text must remove or fold to \n.
    HOSTILE = (
        "\u200b"  # zero-width space
        "\u200d"  # zero-width joiner
        "\ufeff"  # BOM / zero-width no-break space
        "\u202e"  # right-to-left override
        "\u2066\u2069"  # bidi isolates
        "\u0085"  # NEL
        "\u2028"  # line separator
        "\u2029"  # paragraph separator
    )

    sys.path.insert(0, str(skill_root))
    try:
        from scripts.candidates import verify_jsonl
        from scripts.receipts import dump_jsonl, normalize_jsonl_text

        hostile = [
            {
                "source": "qq",
                "from": "Sender <a@x.com>",
                "subject": "Order\r\n wrapped\r and split",
                "date_header": "Wed, 1 Apr 2026 21:46:01 +0000",
                "body": ("line1\r\nline2\rline3 " + HOSTILE
                         + " tab\there \u4e2d\u6587\u6536\u636e emoji \U0001f9fe end "
                         + "x" * 9000),
            },
            {
                "source": "gmail",
                "from": "Vercel Inc.",
                "subject": "\u53d1\u7968 #2367",
                "date_header": "Thu, 2 May 2026 03:05:39 -0700",
                "body": "Total $20.00\r\nThanks \U0001f600\tfine",
            },
            {"source": "qq", "from": "C", "subject": "plain", "date_header": "z", "body": "ok"},
        ]

        cleaned = []
        for rec in hostile:
            row = {k: (normalize_jsonl_text(v) if isinstance(v, str) else v) for k, v in rec.items()}
            row["body"] = row["body"][:6000]
            cleaned.append(row)

        fd, tmp = tempfile.mkstemp(suffix=".jsonl")
        _os.close(fd)
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                for row in cleaned:
                    fh.write(dump_jsonl(row) + "\n")

            with open(tmp, encoding="utf-8") as fh:
                physical = fh.readlines()

            problems: list[str] = []
            if len(physical) != len(cleaned):
                problems.append(f"expected {len(cleaned)} physical lines, got {len(physical)}")
            for i, ln in enumerate(physical, start=1):
                try:
                    _json.loads(ln)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"line {i} failed to reparse: {exc}")
            ok, errors = verify_jsonl(tmp)
            if not ok:
                problems.append("verify_jsonl reported: " + "; ".join(errors))
            for row in cleaned:
                if "\r" in row["body"] or any(c in row["body"] for c in HOSTILE):
                    problems.append("hostile character survived clean_text")
                    break

            if problems:
                failures.append("JSONL writer regression: " + " | ".join(problems))
            else:
                pass_msg("JSONL writer regression: hostile records -> strict one-line-per-record JSONL")
        finally:
            _os.unlink(tmp)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"JSONL writer regression could not run: {type(exc).__name__}: {exc}")
    finally:
        sys.path.pop(0)


def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]

    failures: list[str] = []
    warnings: list[str] = []

    skill_md = skill_root / "SKILL.md"
    run_py = skill_root / "run.py"
    package_init = skill_root / "scripts" / "__init__.py"

    # --- file presence ----------------------------------------------------
    if skill_md.exists():
        pass_msg("SKILL.md exists")
        skill_text = skill_md.read_text(encoding="utf-8")
    else:
        failures.append("SKILL.md is missing")
        skill_text = ""

    if run_py.exists():
        pass_msg("run.py exists")
    else:
        failures.append("run.py is missing")

    if package_init.exists():
        pass_msg("scripts/__init__.py exists")
    else:
        warnings.append("scripts/__init__.py is missing; package imports may be fragile")

    # --- python syntax ----------------------------------------------------
    py_files = sorted(p for p in skill_root.rglob("*.py") if "__pycache__" not in p.parts)
    if not py_files:
        failures.append("No Python files found")
    for py_file in py_files:
        rel = py_file.relative_to(skill_root)
        try:
            ast.parse(py_file.read_text(encoding="utf-8"))
            pass_msg(f"Python syntax OK: {rel}")
        except SyntaxError as exc:
            failures.append(f"Python syntax error in {rel}: line {exc.lineno}: {exc.msg}")

    # --- import smoke test (catches import errors, not just syntax) --------
    sys.path.insert(0, str(skill_root))
    try:
        import importlib

        importlib.import_module("scripts")
        importlib.import_module("run")
        pass_msg("scripts package and run.py import cleanly")
    except Exception as exc:  # noqa: BLE001 — surface any import failure
        failures.append(f"Import error: {type(exc).__name__}: {exc}")
    finally:
        sys.path.pop(0)

    # --- strict-JSONL writer regression ----------------------------------
    check_jsonl_writer(skill_root, failures)

    # --- .py files named in SKILL.md exist somewhere ----------------------
    known_py = {p.name for p in py_files}
    for ref in sorted(set(re.findall(r"[\w./-]+\.py", skill_text))):
        normalized = ref.strip("`\"'")
        name = Path(normalized).name
        if (skill_root / normalized).exists() or name in known_py:
            continue
        warnings.append(f"SKILL.md references a Python file that may not exist: {ref}")

    # --- direct internal-script calls (should route through run.py) -------
    pattern = re.compile(rf"python3\s+\S*{re.escape(SKILL_DIR_REF)}/(\S+\.py)")
    for hit in sorted(set(pattern.findall(skill_text))):
        if hit == "run.py" or hit.startswith("tools/"):
            continue
        warnings.append(
            f"SKILL.md appears to call an internal script directly: {hit}. "
            "Prefer routing through run.py."
        )

    # --- permission documentation ----------------------------------------
    if RUN_PERMISSION in skill_text:
        pass_msg("SKILL.md documents the run.py wildcard permission rule")
    else:
        warnings.append(f"SKILL.md does not document the recommended permission rule: {RUN_PERMISSION}")

    for module in INTERNAL_MODULES:
        stale = f"Bash(python3 {SKILL_DIR_REF}/{module}:*)"
        if stale in skill_text:
            warnings.append(
                f"SKILL.md still documents a per-module permission rule for {module}. "
                "run.py is the only entrypoint — remove it."
            )

    # --- interactive-flow phrasing ---------------------------------------
    low = skill_text.lower()
    for phrase in RISKY_PHRASES:
        if phrase in low:
            warnings.append(
                f"SKILL.md contains interactive-flow phrase '{phrase}'. "
                "Verify it does not assume unavailable Claude Code UI behavior."
            )

    # --- markdown hygiene (outside code fences) --------------------------
    for idx, line in iter_non_fenced(skill_text.splitlines()):
        if line.startswith("#") and not re.match(r"^#{1,6}\s", line):
            warnings.append(f"Markdown heading may be malformed at SKILL.md:{idx}: {line}")
        if "\t" in line:
            warnings.append(f"Tab character found at SKILL.md:{idx}")
        if len(line) > 140:
            warnings.append(f"Long Markdown line over 140 chars at SKILL.md:{idx}")

    # --- report -----------------------------------------------------------
    for warning in warnings:
        warn_msg(warning)
    for failure in failures:
        fail_msg(failure)

    print("")
    print(f"Validation finished with {len(failures)} failure(s) and {len(warnings)} warning(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

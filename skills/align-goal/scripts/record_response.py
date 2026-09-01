#!/usr/bin/env python3
"""Append-only, hash-chained user response log for align-goal.

The user executes this script themselves — Claude Code: `!python3 …/record_response.py
docs/goals/<slug>.responses.jsonl "C1=ALT2"`, Codex: run the same command in a
terminal. The planning LLM must never run it on the user's behalf: the log's value
is that every confirmation bound by the validator traces to a command the user
typed, so a fabricated confirmation requires a visible tool call in the session
transcript instead of a silent edit. This is tamper-evidence, not tamper-proofing.

Entry shape (JSONL, one object per line, exact keys):
  {"seq": 1, "at": "<RFC3339>", "text": "<verbatim>", "prev": null|"sha256:…", "hash": "sha256:…"}

hash = sha256 of the NFC-normalized canonical JSON of {seq, at, text, prev};
prev = previous entry's hash (null for seq 1); seq is contiguous from 1 and
`at` is nondecreasing. The canonicalization must stay byte-identical to
validate_goal_spec.py's `canon`.

Exit codes: 0 = success, 1 = chain verification failure, 2 = I/O or usage failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ENTRY_KEYS = ("seq", "at", "text", "prev")
RFC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$")
SHA = re.compile(r"^sha256:[0-9a-f]{64}$")


def nfc(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [nfc(item) for item in value]
    if isinstance(value, dict):
        return {nfc(key): nfc(item) for key, item in value.items()}
    return value


def canon(value):
    return json.dumps(nfc(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def chain_hash(entry):
    return "sha256:" + hashlib.sha256(canon({key: entry.get(key) for key in ENTRY_KEYS})).hexdigest()


def instant(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None


def load_entries(path):
    """Parse a response log. Returns (entries, errors); entries stop at the first bad line."""
    entries, errors = [], []
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], []
    except (OSError, UnicodeError) as exc:
        return [], [f"response log unreadable: {exc}"]
    # Split on the record separator "\n" ONLY. json.dumps escapes \n/\r/\t but
    # emits U+2028/U+2029/U+0085 raw with ensure_ascii=False; str.splitlines()
    # would tear a valid entry on those, so the recorder could write a log it
    # cannot read back. Splitting on "\n" alone keeps every entry intact.
    for index, line in enumerate(raw.split("\n"), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {index}: invalid JSON: {exc}")
            return entries, errors
        if not isinstance(entry, dict) or set(entry) != {*ENTRY_KEYS, "hash"}:
            errors.append(f"line {index}: exact keys seq, at, text, prev, hash required")
            return entries, errors
        entries.append(entry)
    return entries, errors


def verify_entries(entries):
    """Verify the full hash chain. Returns a list of errors (empty = valid)."""
    errors = []
    previous_hash = None
    previous_at = None
    for index, entry in enumerate(entries):
        label = f"entry {index + 1}"
        if entry.get("seq") != index + 1:
            errors.append(f"{label}: seq must be contiguous from 1 (got {entry.get('seq')!r})")
        at = entry.get("at")
        if not isinstance(at, str) or not RFC.fullmatch(at):
            errors.append(f"{label}: at must be RFC3339")
        elif previous_at is not None:
            now, before = instant(at), instant(previous_at)
            if now is not None and before is not None and now < before:
                errors.append(f"{label}: at must be nondecreasing")
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{label}: text must be a nonempty string")
        if entry.get("prev") != previous_hash:
            errors.append(f"{label}: prev must equal the previous entry hash")
        recorded = entry.get("hash")
        if not isinstance(recorded, str) or not SHA.fullmatch(recorded):
            errors.append(f"{label}: hash must be sha256:64 lowercase hex")
        elif recorded != chain_hash(entry):
            errors.append(f"{label}: hash does not match entry content")
        previous_hash = recorded if isinstance(recorded, str) else None
        previous_at = at if isinstance(at, str) else previous_at
    return errors


def append_entry(path, text):
    entries, errors = load_entries(path)
    errors += verify_entries(entries)
    if errors:
        return 1, {"appended": False, "errors": errors}
    entry = {
        "seq": len(entries) + 1,
        "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "text": unicodedata.normalize("NFC", text),
        "prev": entries[-1]["hash"] if entries else None,
    }
    entry["hash"] = chain_hash(entry)
    try:
        log_path = Path(path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    except (OSError, UnicodeError) as exc:
        return 2, {"appended": False, "errors": [f"response log unwritable: {exc}"]}
    return 0, {"appended": True, "seq": entry["seq"], "at": entry["at"], "hash": entry["hash"]}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="record_response.py",
        description="Append a verbatim user response to a hash-chained align-goal log, or verify the chain. Run this yourself; do not let the planning LLM run it for you.",
    )
    parser.add_argument("log_path", help="path to the .responses.jsonl log")
    parser.add_argument("text", nargs="*", help="verbatim response text (joined by spaces); omit to read stdin")
    parser.add_argument("--verify", action="store_true", help="verify the existing chain and exit")
    args = parser.parse_args(argv)
    if args.verify:
        if args.text:
            print(json.dumps({"errors": ["--verify takes no response text"]}, ensure_ascii=False))
            return 2
        entries, errors = load_entries(args.log_path)
        errors += verify_entries(entries)
        print(json.dumps({"valid": not errors, "entries": len(entries), "errors": errors}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    text = " ".join(args.text) if args.text else sys.stdin.read().strip()
    if not text.strip():
        print(json.dumps({"errors": ["response text must be nonempty"]}, ensure_ascii=False))
        return 2
    code, result = append_entry(args.log_path, text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

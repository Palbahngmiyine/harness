#!/usr/bin/env python3
"""Validate structural invariants of a grill-prfaq PR/FAQ Markdown file."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FRONTMATTER_KEYS = ("title", "status", "customer", "created", "updated", "confirmed_at")
STATUSES = ("hypothesis", "prfaq", "rejected")
CUSTOMERS = ("external", "internal", "none")
GRADES = ("poor", "borderline", "solid", "outstanding")
PR_PLACEHOLDER = "(비어 있음 — status가 prfaq가 된 뒤에 쓴다)"
ROOT_SLOTS = 5
NOT_APPLICABLE = "「해당 없음」"

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
SECTION_RE = re.compile(r"^## ([1-5])\.\s")
ITEM_RE = re.compile(r"^### F(\d+)\.\s*(.*)$")
TAG_RE = re.compile(r"^\*\*(사실|결정|가정|프로토타입 필요)\*\*")
FID_RE = re.compile(r"(?<![A-Za-z0-9])F(\d+)(?![0-9])")
LIST_RE = re.compile(r"^\s*([-*+]|\d+\.)\s")
TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
QUOTE_RE = re.compile(r"「(.*?)」")
ROUND_RE = re.compile(r"\(R\d+\)")
OPTION_PICK_RE = re.compile(r"[A-Za-z0-9]")
CONFIRMATION_RE = re.compile(r"「.+?」\s*\((\d{4}-\d{2}-\d{2})\)")
ACCEPTED = "**사용자 수용** 「"


class Item:
    def __init__(self, number: int, title: str, section: int) -> None:
        self.number = number
        self.title = title
        self.section = section
        self.lines: list[str] = []

    @property
    def tag_lines(self) -> list[str]:
        return [line for line in self.lines if TAG_RE.match(line)]

    @property
    def tag(self) -> str | None:
        match = TAG_RE.match(self.tag_lines[0]) if self.tag_lines else None
        return match.group(1) if match else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check a PR/FAQ file written by the grill-prfaq skill."
    )
    parser.add_argument("prfaq", type=Path, help="Path to docs/prfaq/<date>-<slug>.md")
    return parser.parse_args()


def split_frontmatter(text: str) -> tuple[dict[str, str] | None, str, list[str]]:
    errors: list[str] = []
    if not text.startswith("---\n"):
        return None, text, ["frontmatter must start at line 1 with '---'"]
    end = text.find("\n---", 4)
    if end == -1:
        return None, text, ["frontmatter closing '---' not found"]
    raw = text[4:end]
    body = text[end + 4 :]
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            errors.append(f"frontmatter line is not 'key: value': {line!r}")
            continue
        meta[key.strip()] = value.strip()
    return meta, body, errors


def check_frontmatter(meta: dict[str, str]) -> list[str]:
    errors: list[str] = []
    keys = set(meta)
    expected = set(FRONTMATTER_KEYS)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        if missing:
            errors.append(f"frontmatter missing keys: {', '.join(missing)}")
        if extra:
            errors.append(f"frontmatter has unknown keys: {', '.join(extra)}")
        return errors
    if not meta["title"]:
        errors.append("frontmatter title is empty")
    if meta["status"] not in STATUSES:
        errors.append(f"status must be one of {STATUSES}, got {meta['status']!r}")
    if meta["customer"] not in CUSTOMERS:
        errors.append(f"customer must be one of {CUSTOMERS}, got {meta['customer']!r}")
    for key in ("created", "updated"):
        if not DATE_RE.fullmatch(meta[key]):
            errors.append(f"{key} must be YYYY-MM-DD, got {meta[key]!r}")
    if meta["confirmed_at"] and not DATE_RE.fullmatch(meta["confirmed_at"]):
        errors.append(f"confirmed_at must be YYYY-MM-DD or empty, got {meta['confirmed_at']!r}")
    return errors


def split_sections(body: str) -> tuple[dict[int, list[str]], list[str]]:
    sections: dict[int, list[str]] = {}
    current: int | None = None
    for line in body.splitlines():
        match = SECTION_RE.match(line)
        if match:
            current = int(match.group(1))
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    errors = [f"section '## {n}.' missing" for n in range(1, 6) if n not in sections]
    return sections, errors


def parse_items(sections: dict[int, list[str]]) -> list[Item]:
    items: list[Item] = []
    for section in (1, 2):
        current: Item | None = None
        for line in sections.get(section, []):
            match = ITEM_RE.match(line)
            if match:
                current = Item(int(match.group(1)), match.group(2).strip(), section)
                items.append(current)
            elif current is not None:
                current.lines.append(line)
    return items


def check_items(items: list[Item], sections: dict[int, list[str]], gate_on: bool) -> list[str]:
    errors: list[str] = []
    numbers = [item.number for item in items]
    if numbers != list(range(1, len(items) + 1)):
        errors.append(f"F ids must be unique and consecutive from F1, got {numbers}")
    root = [item.number for item in items if item.section == 1]
    if root != list(range(1, ROOT_SLOTS + 1)):
        errors.append(f"section 1 must hold exactly F1..F{ROOT_SLOTS}, got {root}")
    scope_ids = {int(n) for n in FID_RE.findall("\n".join(sections.get(3, [])))}
    for item in items:
        label = f"F{item.number}"
        tag_lines = item.tag_lines
        if not tag_lines and item.section == 1 and not gate_on:
            if any(line.strip() for line in item.lines):
                errors.append(f"{label} has prose but no tag line; open slots stay blank")
            continue
        if len(tag_lines) != 1:
            errors.append(f"{label} must have exactly one tag line, found {len(tag_lines)}")
            continue
        line = tag_lines[0]
        tag = item.tag
        if tag == "사실" and not ("출처:" in line and DATE_RE.search(line)):
            errors.append(f"{label} 사실 needs '출처: <path|URL>, YYYY-MM-DD' on the tag line")
        if tag == "결정":
            quote = QUOTE_RE.search(line)
            if not quote:
                errors.append(f"{label} 결정 must quote the user verbatim inside 「 」")
            elif not ROUND_RE.search(line):
                errors.append(f"{label} 결정 needs a round marker (R<n>)")
            elif item.number == 4 and OPTION_PICK_RE.fullmatch(quote.group(1).strip()):
                errors.append("F4 결정 must be the user's own observation, not an option pick")
            if item.section == 1 and NOT_APPLICABLE in line:
                errors.append(f"{label} {NOT_APPLICABLE} is not a settled decision; park it in section 3")
        if tag == "가정" and not ("검증 계획:" in line or ACCEPTED in line):
            errors.append(f"{label} 가정 needs '검증 계획:' or '{ACCEPTED}…」'")
        if tag == "프로토타입 필요" and item.section == 1 and item.number not in scope_ids:
            errors.append(f"{label} is parked but not listed in section 3")
        text = "\n".join(item.lines)
        if item.section == 1 and "➡️" in text:
            errors.append(f"{label} root slot may not hold a ➡️ recommendation")
        if item.number == 4 and (tag == "프로토타입 필요" or "추천" in text):
            errors.append("F4 (근거) allows only 사실/결정/가정 and no recommendation")
    return errors


def parse_gate_table(lines: list[str]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for line in lines:
        match = TABLE_ROW_RE.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in match.group(1).split("|")]
        if len(cells) != 3 or cells[0] in ("차원", "") or set(cells[0]) <= {"-"}:
            continue
        rows.append((cells[0], cells[1], cells[2]))
    return rows


def gate_field(lines: list[str], name: str) -> str:
    prefix = f"- {name}:"
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def grade_ceiling(slot: Item | None) -> str | None:
    """Highest grade the root slot's own tag line allows (gate.md §1)."""
    if slot is None:
        return None
    if slot.tag == "프로토타입 필요":
        return "borderline"
    if slot.tag == "가정" and ACCEPTED not in slot.tag_lines[0]:
        return "borderline"
    return None


def check_gate(
    sections: dict[int, list[str]], items: list[Item], status: str, confirmed_at: str
) -> list[str]:
    errors: list[str] = []
    lines = sections.get(4, [])
    rows = parse_gate_table(lines)
    if len(rows) != ROOT_SLOTS:
        errors.append(f"gate table must have {ROOT_SLOTS} dimension rows, found {len(rows)}")
    facts = {item.number for item in items if item.tag == "사실"}
    known = {item.number for item in items}
    root = {item.number: item for item in items if item.section == 1}
    grades = [row[1] for row in rows]
    for index, (dimension, grade, evidence) in enumerate(rows):
        if grade not in GRADES:
            errors.append(f"gate row {dimension!r}: grade must be one of {GRADES}, got {grade!r}")
            continue
        ids = {int(n) for n in FID_RE.findall(evidence)}
        if not ids:
            errors.append(f"gate row {dimension!r}: evidence must cite at least one F-id")
        unknown = sorted(ids - known)
        if unknown:
            errors.append(f"gate row {dimension!r}: unknown F-ids {unknown}")
        if grade == "outstanding" and not ids & facts:
            errors.append(f"gate row {dimension!r}: outstanding requires a 사실 item as evidence")
        ceiling = grade_ceiling(root.get(index + 1))
        if ceiling and GRADES.index(grade) > GRADES.index(ceiling):
            errors.append(
                f"gate row {dimension!r}: F{index + 1} is parked or an unaccepted 가정, "
                f"grade may not exceed {ceiling}"
            )
    if "poor" in grades:
        errors.append("gate has a poor dimension; PR may not be written")
    if grades.count("borderline") > 1:
        errors.append("gate has more than one borderline dimension; PR may not be written")
    if not gate_field(lines, "프론티어 재도출"):
        errors.append("gate needs '- 프론티어 재도출: …' filled")
    verifier = gate_field(lines, "검증기")
    if status == "prfaq" and not (verifier.startswith("통과") or verifier.startswith("수동")):
        errors.append("gate needs '- 검증기: 통과|수동, YYYY-MM-DD' while status=prfaq")
    confirmation = CONFIRMATION_RE.fullmatch(gate_field(lines, "확인 문장"))
    if not confirmation:
        errors.append("gate needs '- 확인 문장: 「<user's words>」 (YYYY-MM-DD)'")
    elif confirmed_at and confirmation.group(1) != confirmed_at:
        errors.append("confirmation date must equal confirmed_at")
    return errors


def check_pr(sections: dict[int, list[str]], status: str) -> list[str]:
    errors: list[str] = []
    content = [line for line in sections.get(5, []) if line.strip()]
    if status in ("hypothesis", "rejected"):
        if content != [PR_PLACEHOLDER]:
            errors.append(f"section 5 must be exactly the placeholder while status={status}")
        return errors
    if not content or PR_PLACEHOLDER in content:
        errors.append("section 5 PR is empty or still holds the placeholder while status=prfaq")
    bullets = [line for line in content if LIST_RE.match(line)]
    if bullets:
        errors.append(f"section 5 PR must be prose; found {len(bullets)} list line(s)")
    return errors


def validate(text: str) -> tuple[list[str], dict[str, int | str]]:
    meta, body, errors = split_frontmatter(text)
    if meta is None:
        return errors, {}
    errors.extend(check_frontmatter(meta))
    if errors:
        return errors, {}
    if not any(line.startswith("**작성 규칙**") for line in body.splitlines()):
        errors.append("body must state the '**작성 규칙**' line near the top")
    sections, section_errors = split_sections(body)
    errors.extend(section_errors)
    if section_errors:
        return errors, {}
    status = meta["status"]
    confirmed_at = meta["confirmed_at"]
    gate_on = status == "prfaq" or bool(gate_field(sections[4], "확인 문장"))
    items = parse_items(sections)
    errors.extend(check_items(items, sections, gate_on))
    if meta["customer"] == "none" and NOT_APPLICABLE not in "\n".join(sections[3]):
        errors.append(f"customer=none requires a '{NOT_APPLICABLE}' line in section 3")
    if status == "prfaq" and not confirmed_at:
        errors.append("status=prfaq requires confirmed_at")
    if status != "prfaq" and confirmed_at:
        errors.append(f"confirmed_at must be empty while status={status}")
    if gate_on:
        errors.extend(check_gate(sections, items, status, confirmed_at))
    errors.extend(check_pr(sections, status))
    tags = [item.tag for item in items]
    summary: dict[str, int | str] = {
        "status": status,
        "facts": tags.count("사실"),
        "decisions": tags.count("결정"),
        "assumptions": tags.count("가정"),
        "parked": tags.count("프로토타입 필요"),
        "faq": sum(1 for item in items if item.section == 2),
        "open": sum(1 for item in items if item.section == 1 and item.tag is None),
    }
    return errors, summary


def main() -> int:
    args = parse_args()
    try:
        text = args.prfaq.read_text(encoding="utf-8")
    except OSError as error:
        print(f"ERROR: cannot read {args.prfaq}: {error}")
        return 1
    errors, summary = validate(text)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    counts = ", ".join(f"{key}={value}" for key, value in summary.items())
    print(f"Validated {args.prfaq}: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

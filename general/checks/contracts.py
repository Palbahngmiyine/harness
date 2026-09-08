"""Registered rules and local inline Markdown links; no semantic purity analysis."""
from pathlib import Path
import re
from urllib.parse import unquote

RULE_GROUPS = {
    'AGENTS': (('GOV', 6), ('FP', 8), ('FX', 4), ('VER', 3), ('PKG', 1)),
    'profiles/c': (('C', 14),),
    'profiles/rust': (('RS', 14),),
    'fp/verification': (('CHK', 14),),
    'fp/evolution': (('EVO', 10),),
}
ID = re.compile(r'^\*\*([A-Z]+-\d{3})\*\*', re.MULTILINE)
LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')


def registered_ids(name: str) -> list[str]:
    return [f'{prefix}-{n:03}' for prefix, count in RULE_GROUPS[name] for n in range(1, count + 1)]


def heading_ids(text: str) -> set[str]:
    """Support the package's ATX headings and duplicate-heading suffixes."""
    found = set()
    fenced = False
    for line in text.splitlines():
        if line.startswith(('```', '~~~')):
            fenced = not fenced
            continue
        match = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line)
        if not match or fenced:
            continue
        base = re.sub(r'[^\w\- ]', '', match[1].strip().lower()).replace(' ', '-')
        slug, number = base, 0
        while slug in found:
            number += 1
            slug = f'{base}-{number}'
        found.add(slug)
    return found


def document_findings(path: Path, text: str, base: Path) -> list[str]:
    findings = []
    for match in re.finditer(r'^\*\*([A-Z]+-\d{3})\*\*([^\n]*)', text, re.MULTILINE):
        if not match[2].strip():
            findings.append(f'empty rule: {path}: {match[1]}')
    for link in LINK.findall(text):
        if '://' in link or link.startswith('mailto:'):
            continue
        address, separator, fragment = link.partition('#')
        target = (path.parent / unquote(address)).resolve() if address else path
        if not target.is_relative_to(base) or not target.is_file():
            findings.append(f'broken/outside link: {path}: {link}')
            continue
        if separator:
            try:
                target_text = target.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                findings.append(f'unreadable fragment target: {path}: {link}')
                continue
            if unquote(fragment) not in heading_ids(target_text):
                findings.append(f'unknown fragment: {path}: {link}')
    return findings

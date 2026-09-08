"""Validate this guidance package's structure, not program purity or translation meaning."""
from pathlib import Path
import json
import re
import sys

from contracts import ID, RULE_GROUPS, document_findings, registered_ids

PAIRS = tuple(RULE_GROUPS)
CODE = {'.py', '.c', '.h', '.rs', '.sh'}


def validate(root: Path) -> list[str]:
    """Return concrete structural findings; an empty list is only structural success."""
    base = (root / 'general').resolve()
    required = [base / f'{p}{lang}.md' for p in PAIRS for lang in ('', '.ko')]
    required += [base / 'references/functional-programming.md', base / 'evals/cases.json']
    errors = [f'missing: {p.relative_to(base)}' for p in required if not p.is_file()]
    if errors:
        return errors
    texts = {}
    for path in sorted(base.rglob('*')):
        if not path.is_file() or path.suffix not in CODE | {'.md', '.json'}:
            continue
        if path.is_symlink():
            errors.append(f'symlink not validated: {path}')
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode('utf-8')
        except (OSError, UnicodeError) as exc:
            errors.append(f'unreadable: {path}: {exc}')
            continue
        texts[path] = text
        if not text or not text.endswith('\n') or '\r' in text or '\ufeff' in text:
            errors.append(f'text format: {path}')
        if any(line.rstrip() != line for line in text.splitlines()):
            errors.append(f'trailing whitespace: {path}')
        if re.search(r'^(<<<<<<< |=======|>>>>>>> )', text, re.MULTILINE):
            errors.append(f'conflict marker: {path}')
        if path.suffix in CODE and len(text.splitlines()) > 100:
            errors.append(f'source over 100 lines: {path}')
        if path.suffix == '.md':
            errors.extend(document_findings(path, text, base))
    known = set()
    for name in PAIRS:
        english = ID.findall(texts.get(base / f'{name}.md', ''))
        korean = ID.findall(texts.get(base / f'{name}.ko.md', ''))
        if english != registered_ids(name):
            errors.append(f'registered rules differ: {name}')
        if not english or english != korean:
            errors.append(f'rule parity: {name}')
        if len(set(english)) != len(english) or known.intersection(english):
            errors.append(f'duplicate rule ID: {name}')
        known.update(english)
    try:
        corpus = json.loads(texts[base / 'evals/cases.json'])
        cases = corpus['cases']
        if corpus['split'] != 'development' or not isinstance(cases, list) or len(cases) < 8:
            raise ValueError('expected at least eight public development cases')
        names = set()
        for case in cases:
            if not all(isinstance(case[k], str) and case[k].strip() for k in ('id', 'task', 'expected')):
                raise ValueError('empty or non-string case field')
            refs = case['rules']
            if case['id'] in names or not isinstance(refs, list) or not refs:
                raise ValueError('duplicate case or empty rules')
            if not all(isinstance(r, str) and r in known for r in refs):
                raise ValueError('unknown rule ID')
            names.add(case['id'])
    except (KeyError, ValueError, TypeError) as exc:
        errors.append(f'corpus: {exc}')
    return errors


if __name__ == '__main__':
    findings = validate(Path(__file__).resolve().parents[2])
    print('\n'.join(findings) if findings else 'PASS: package structure only')
    sys.exit(bool(findings))

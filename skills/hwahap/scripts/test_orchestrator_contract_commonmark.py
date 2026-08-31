"""Conservative visible-ATX-H2 scanner used by the docs contract oracle."""
import re
import unittest
from dataclasses import dataclass
@dataclass(frozen=True)
class VisibleH2:
    normalized: str
    start: int
    end: int
def _without_comments(line, in_comment):
    visible, cursor = [], 0
    while True:
        if in_comment:
            close = line.find("-->", cursor)
            if close < 0: return "".join(visible), True
            cursor, in_comment = close + 3, False
        begin = line.find("<!--", cursor)
        if begin < 0: return "".join(visible) + line[cursor:], in_comment
        visible.append(line[cursor:begin])
        cursor, in_comment = begin + 4, True
def _atx_h2(line, start):
    match = re.fullmatch(r" {0,3}##(?:[ \t]+(.*?))?[ \t]*", line)
    if not match: return None
    content = (match.group(1) or "").strip()
    content = re.sub(r"[ \t]+#+[ \t]*$", "", content).strip()
    return VisibleH2(" ".join(content.split()), start, start + len(line))
def _fence(line):
    match = re.match(r"^ {0,3}([`~])\1{2,}(.*)$", line)
    if not match or (match.group(1) == "`" and "`" in match.group(2)): return None
    prefix = match.group(0)[:-len(match.group(2))] if match.group(2) else match.group(0)
    return match.group(1), len(prefix.strip(" "))
def _closes_fence(line, fence):
    char, length = fence
    return re.fullmatch(rf" {{0,3}}{re.escape(char)}{{{length},}}[ \t]*", line) is not None
def visible_h2s(text):
    headings, offset, in_comment, fence = [], 0, False, None
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        if in_comment:
            _, in_comment = _without_comments(line, True)
            offset += len(raw)
            continue
        if fence:
            if _closes_fence(line, fence): fence = None
            offset += len(raw)
            continue
        if re.match(r"^(?: {4,}|\t)", line): offset += len(raw); continue
        opener = _fence(line)
        if opener: fence = opener; offset += len(raw); continue
        visible, in_comment = _without_comments(line, False)
        heading = _atx_h2(visible, offset)
        if heading: headings.append(heading)
        offset += len(raw)
    return tuple(headings)
def _visible_region(text, start, end):
    visible, offset, in_comment, fence = [], 0, False, None
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        line_ending = raw[len(line):]
        if in_comment:
            _, in_comment = _without_comments(line, True)
            offset += len(raw)
            continue
        if fence:
            if _closes_fence(line, fence): fence = None
        elif not re.match(r"^(?: {4,}|\t)", line):
            opener = _fence(line)
            if opener: fence = opener
            else:
                clean, in_comment = _without_comments(line, False)
                if offset >= start and offset + len(raw) <= end: visible.append(clean + line_ending)
        offset += len(raw)
    return "".join(visible)
def normative_section(text, target):
    matches = [heading for heading in visible_h2s(text) if heading.normalized == target]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one visible H2: {target!r}")
    start = matches[0].end
    end = next((heading.start for heading in visible_h2s(text) if heading.start > start), len(text))
    return _visible_region(text, start, end)
class CommonMarkScannerTests(unittest.TestCase):
    def test_states_and_normalization_are_deterministic(self):
        text = ("<!-- ## Hidden -->\n## Roles   and units ###\n"
                "  ``` info\n## Roles and units\n  ```   \n  ~~~python\n## Fake\n  ~~~  \n"
                "    ## Indented\n\t## Tabbed\n## Next\n")
        self.assertEqual([(h.normalized, h.start) for h in visible_h2s(text)],
                         [("Roles and units", 19), ("Next", len(text) - 8)])
    def test_noop_guards_and_unclosed_regions(self):
        for text in ("plain text\n", "<!-- no close\n## Hidden\n", "~~~\n## Hidden\n"):
            self.assertEqual(visible_h2s(text), ())
        self.assertEqual([h.normalized for h in visible_h2s("~~~\n## hidden\n~~~\t\n## visible\n")], ["visible"])
        with self.assertRaises(AssertionError):
            normative_section("## One\n## One ##\n", "One")
        self.assertEqual(normative_section("## Target\nvisible\n<!-- hidden -->\n~~~\n## Fake\n~~~\n    hidden\n## Next\n", "Target"),
                         "visible\n\n")
if __name__ == "__main__":
    unittest.main()

"""Post-PR counterexamples: these fail against the original checker."""
from pathlib import Path
from tempfile import TemporaryDirectory
import re
import shutil
import unittest

from validate import validate

SOURCE = Path(__file__).resolve().parents[1]


class AdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE, self.root / 'general', ignore=shutil.ignore_patterns('__pycache__'))

    def rewrite_pair(self, transform):
        for name in ('AGENTS.md', 'AGENTS.ko.md'):
            path = self.root / 'general' / name
            path.write_text(transform(path.read_text(encoding='utf-8')), encoding='utf-8')

    def append_link(self, link):
        path = self.root / 'general/AGENTS.md'
        path.write_text(path.read_text(encoding='utf-8') + f'\n[probe]({link})\n', encoding='utf-8')

    def test_symmetric_rule_deletion_is_rejected(self):
        self.rewrite_pair(lambda s: re.sub(r'^\*\*FX-004\*\*.*\n\n?', '', s, flags=re.M))
        self.assertTrue(any('registered rules' in e for e in validate(self.root)))

    def test_empty_rule_body_is_rejected(self):
        self.rewrite_pair(lambda s: re.sub(r'^\*\*FP-007\*\*.*$', '**FP-007**', s, flags=re.M))
        self.assertTrue(any('empty rule' in e for e in validate(self.root)))

    def test_missing_local_heading_is_rejected(self):
        self.append_link('profiles/c.md#heading-that-does-not-exist')
        self.assertTrue(any('fragment' in e for e in validate(self.root)))

    def test_existing_local_heading_is_accepted(self):
        self.append_link('profiles/c.md#semantic-model-and-representation')
        self.assertEqual(validate(self.root), [])

    def test_same_document_heading_is_accepted(self):
        self.append_link('#semantic-core')
        self.assertEqual(validate(self.root), [])

    def test_missing_same_document_heading_is_rejected(self):
        self.append_link('#heading-that-does-not-exist')
        self.assertTrue(any('fragment' in e for e in validate(self.root)))


if __name__ == '__main__':
    unittest.main()

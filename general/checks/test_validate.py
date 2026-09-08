"""Regression tests for the package validator, including intentional corruptions."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import unittest

from validate import validate

SOURCE = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE, self.root / 'general', ignore=shutil.ignore_patterns('__pycache__'))

    def edit(self, name, transform):
        path = self.root / 'general' / name
        path.write_text(transform(path.read_text(encoding='utf-8')), encoding='utf-8')

    def assert_finding(self, fragment):
        self.assertTrue(any(fragment in item for item in validate(self.root)))

    def test_valid_package_is_accepted(self):
        self.assertEqual(validate(self.root), [])

    def test_missing_profile_is_rejected(self):
        (self.root / 'general/profiles/c.md').unlink()
        self.assert_finding('missing: profiles/c.md')

    def test_broken_link_is_rejected(self):
        self.edit('AGENTS.md', lambda s: s.replace('(profiles/c.md)', '(profiles/absent.md)'))
        self.assert_finding('broken/outside link')

    def test_translation_id_mismatch_is_rejected(self):
        self.edit('profiles/rust.ko.md', lambda s: s.replace('RS-001', 'RS-999'))
        self.assert_finding('rule parity')

    def test_duplicate_rule_is_rejected(self):
        self.edit('profiles/c.md', lambda s: s + '\n**C-001** Duplicate.\n')
        self.assert_finding('duplicate rule ID')

    def test_source_limit_is_not_document_limit(self):
        (self.root / 'general/checks/oversized.py').write_text('# x\n' * 101)
        self.assert_finding('source over 100 lines')
        (self.root / 'general/checks/oversized.py').unlink()
        (self.root / 'general/references/long.md').write_text('Text.\n' * 101)
        self.assertEqual(validate(self.root), [])

    def test_unknown_corpus_rule_is_rejected(self):
        self.edit('evals/cases.json', lambda s: s.replace('FP-002', 'FP-999'))
        self.assert_finding('corpus:')

    def test_empty_corpus_is_rejected(self):
        self.edit('evals/cases.json', lambda _: json.dumps({'split': 'development', 'cases': []}) + '\n')
        self.assert_finding('corpus:')

    def test_format_errors_are_rejected(self):
        self.edit('AGENTS.md', lambda s: s + 'bad space \n')
        self.assert_finding('trailing whitespace')
        self.edit('AGENTS.md', lambda s: s + '<<<<<<< conflict\n')
        self.assert_finding('conflict marker')

    def test_outside_link_is_rejected(self):
        self.edit('AGENTS.md', lambda s: s + '\n[escape](../outside.md)\n')
        self.assert_finding('broken/outside link')


if __name__ == '__main__':
    unittest.main()

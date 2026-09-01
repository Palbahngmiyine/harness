#!/usr/bin/env python3
"""Tests for the hash-chained align-goal response log recorder."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "record_response.py"
sys.path.insert(0, str(HERE))
import record_response as record  # noqa: E402
import validate_goal_spec as validator  # noqa: E402


def run(*args, stdin=None):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True, input=stdin)


class RecordResponseTests(unittest.TestCase):
    def test_append_builds_verifiable_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            log = str(Path(directory) / "goal.responses.jsonl")
            first = run(log, "C1=ALT2")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            payload = json.loads(first.stdout)
            self.assertEqual(payload["seq"], 1)
            second = run(log, "C2=ALT1;", "C3=OTHER: 5s per attempt")
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(json.loads(second.stdout)["seq"], 2)
            verify = run(log, "--verify")
            self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
            result = json.loads(verify.stdout)
            self.assertTrue(result["valid"])
            self.assertEqual(result["entries"], 2)
            entries, errors = record.load_entries(log)
            self.assertEqual(errors, [])
            self.assertIsNone(entries[0]["prev"])
            self.assertEqual(entries[1]["prev"], entries[0]["hash"])
            self.assertEqual(entries[1]["text"], "C2=ALT1; C3=OTHER: 5s per attempt")

    def test_tampered_text_fails_verification_and_blocks_append(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "goal.responses.jsonl"
            run(str(log), "C1=ALT1")
            entry = json.loads(log.read_text(encoding="utf-8"))
            entry["text"] = "C1=ALT2"
            log.write_text(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            verify = run(str(log), "--verify")
            self.assertEqual(verify.returncode, 1)
            self.assertIn("hash does not match", verify.stdout)
            blocked = run(str(log), "C2=ALT1")
            self.assertEqual(blocked.returncode, 1, blocked.stdout)

    def test_stdin_nfc_normalization_and_usage_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            log = str(Path(directory) / "goal.responses.jsonl")
            nfd = unicodedata.normalize("NFD", "C1=한글 값")
            appended = run(log, stdin=nfd + "\n")
            self.assertEqual(appended.returncode, 0, appended.stdout + appended.stderr)
            entries, _ = record.load_entries(log)
            self.assertEqual(entries[0]["text"], unicodedata.normalize("NFC", "C1=한글 값"))
            empty = run(log, stdin="   \n")
            self.assertEqual(empty.returncode, 2)
            bad_verify = run(log, "extra", "--verify")
            self.assertEqual(bad_verify.returncode, 2)

    def test_canonicalization_matches_validator(self):
        sample = {"seq": 3, "at": "2026-08-31T09:00:00+09:00", "text": unicodedata.normalize("NFD", "가정용"), "prev": None}
        self.assertEqual(record.canon(sample), validator.canon(sample))
        self.assertEqual("sha256:" + __import__("hashlib").sha256(record.canon(sample)).hexdigest(), record.chain_hash(sample))

    def test_unicode_line_separators_round_trip(self):
        # U+2028/U+2029/U+0085 are emitted raw by json.dumps(ensure_ascii=False)
        # but must NOT tear an entry on read-back; the recorder must read what it wrote.
        with tempfile.TemporaryDirectory() as directory:
            log = str(Path(directory) / "goal.responses.jsonl")
            text = "C1=OTHER: line one line two line threeend"
            appended = run(log, stdin=text + "\n")
            self.assertEqual(appended.returncode, 0, appended.stdout + appended.stderr)
            verify = run(log, "--verify")
            self.assertEqual(verify.returncode, 0, verify.stdout)
            entries, errors = record.load_entries(log)
            self.assertEqual(errors, [])
            self.assertEqual(entries[0]["text"], unicodedata.normalize("NFC", text))
            second = run(log, "C2=ALT1")
            self.assertEqual(second.returncode, 0, second.stdout)

    def test_verify_missing_file_is_empty_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            verify = run(str(Path(directory) / "absent.jsonl"), "--verify")
            self.assertEqual(verify.returncode, 0, verify.stdout)
            self.assertEqual(json.loads(verify.stdout)["entries"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

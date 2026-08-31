#!/usr/bin/env python3
"""Deterministic shape and coverage tests for behavioral eval fixtures."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURE = SCRIPT_DIR.parent / "references" / "evals" / "behavioral-cases.json"
VALIDATOR = SCRIPT_DIR / "validate_behavioral_evals.py"
SPEC = importlib.util.spec_from_file_location("validate_behavioral_evals", VALIDATOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BehavioralEvalFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_canonical_fixture_is_valid_and_complete(self) -> None:
        self.assertEqual(MODULE.validate(copy.deepcopy(self.document)), [])
        capabilities = [case["capability"] for case in self.document["cases"]]
        self.assertEqual(len(self.document["cases"]), 14)
        self.assertEqual(capabilities.count("cold_domain_plan"), 5)

    def test_target_projection_does_not_leak_followups_or_oracle(self) -> None:
        case = self.document["cases"][0]
        projection = MODULE._target_projection(self.document, case)
        rendered = json.dumps(projection, ensure_ascii=False)
        self.assertNotIn("oracle", projection)
        self.assertNotIn("follow_ups", projection)
        self.assertNotIn(case["oracle"]["must_observe"][0], rendered)
        self.assertEqual(projection["initial_user_message"], case["stimulus"]["initial_user_message"])

    def test_required_cold_domains_are_distinct(self) -> None:
        cold = [
            case["domains"][0]
            for case in self.document["cases"]
            if case["capability"] == "cold_domain_plan"
        ]
        self.assertEqual(
            set(cold),
            {"cli", "api", "ui", "stateful_workflow", "data_migration"},
        )

    def test_schema_rejects_structural_and_coverage_mutations(self) -> None:
        mutations = []

        missing_key = copy.deepcopy(self.document)
        del missing_key["cases"][0]["oracle"]
        mutations.append(missing_key)

        duplicate_id = copy.deepcopy(self.document)
        duplicate_id["cases"][1]["id"] = duplicate_id["cases"][0]["id"]
        mutations.append(duplicate_id)

        unsafe_path = copy.deepcopy(self.document)
        unsafe_path["cases"][0]["workspace"]["files"][0]["path"] = "../secret"
        mutations.append(unsafe_path)

        invalid_repeat = copy.deepcopy(self.document)
        invalid_repeat["cases"][0]["stimulus"]["follow_ups"][0]["repeat"] = "always"
        mutations.append(invalid_repeat)

        missing_domain_case = copy.deepcopy(self.document)
        missing_domain_case["cases"] = [
            case for case in missing_domain_case["cases"] if case["id"] != "E13"
        ]
        mutations.append(missing_domain_case)

        for mutated in mutations:
            with self.subTest():
                self.assertTrue(MODULE.validate(mutated))

    def test_cli_validates_and_emits_separated_views(self) -> None:
        valid = subprocess.run(
            [sys.executable, "-B", str(VALIDATOR), str(FIXTURE), "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertTrue(json.loads(valid.stdout)["valid"])

        target = subprocess.run(
            [sys.executable, "-B", str(VALIDATOR), str(FIXTURE), "--emit-target", "E01"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(target.returncode, 0, target.stderr)
        target_payload = json.loads(target.stdout)
        self.assertNotIn("oracle", target_payload)
        self.assertNotIn("follow_ups", target_payload)

        oracle = subprocess.run(
            [sys.executable, "-B", str(VALIDATOR), str(FIXTURE), "--emit-oracle", "E01"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(oracle.returncode, 0, oracle.stderr)
        oracle_payload = json.loads(oracle.stdout)
        self.assertIn("oracle", oracle_payload)
        self.assertIn("follow_ups", oracle_payload)

    def test_cli_uses_exit_1_for_invalid_fixture_and_2_for_io(self) -> None:
        invalid = copy.deepcopy(self.document)
        invalid["cases"][0]["mode"] = "unit_test"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            failure = subprocess.run(
                [sys.executable, "-B", str(VALIDATOR), str(path), "--json"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failure.returncode, 1)
            self.assertFalse(json.loads(failure.stdout)["valid"])

        io_failure = subprocess.run(
            [sys.executable, "-B", str(VALIDATOR), "/definitely/missing/evals.json", "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(io_failure.returncode, 2)
        self.assertFalse(json.loads(io_failure.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()

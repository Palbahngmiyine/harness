"""Discovery launcher for split repository-security tests."""

from __future__ import annotations

import importlib
from pathlib import Path
import unittest


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None):
    if pattern is not None:
        return tests
    suite = unittest.TestSuite()
    for path in sorted(Path(__file__).parent.glob("test_repository_security_0*.py")):
        suite.addTests(loader.loadTestsFromModule(importlib.import_module(path.stem)))
    return suite


if __name__ == "__main__":
    unittest.main()

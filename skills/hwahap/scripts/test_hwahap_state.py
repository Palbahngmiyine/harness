"""Discovery launcher for the split Hwahap state tests."""

from __future__ import annotations

import importlib
from pathlib import Path
import unittest


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None):
    """Run split cases when this launcher is invoked directly."""
    if pattern is not None:
        return tests
    suite = unittest.TestSuite()
    root = Path(__file__).parent
    for path in sorted(root.glob("test_state_case_*.py")):
        module = importlib.import_module(path.stem)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


if __name__ == "__main__":
    unittest.main()

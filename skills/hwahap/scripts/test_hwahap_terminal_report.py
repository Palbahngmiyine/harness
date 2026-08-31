"""Discover terminal report test slices."""

import importlib
import unittest


def load_tests(loader, tests, pattern):
    if pattern is not None:
        return tests
    suite = unittest.TestSuite()
    for index in range(1, 3):
        name = f"test_terminal_{index:02d}"
        try:
            module = importlib.import_module(f".{name}", __package__)
        except (ImportError, TypeError):
            module = importlib.import_module(name)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


if __name__ == "__main__":
    unittest.main()

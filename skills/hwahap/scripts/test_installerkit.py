"""Shared fixture and imports for installer tests."""

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def load_tests(loader, tests, pattern):
    if pattern is None:
        return tests
    return unittest.TestSuite()


def _load_installer():
    path = Path(__file__).with_name("install_project_agents.py")
    spec = importlib.util.spec_from_file_location("installer", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = _load_installer()


class InstallerFixture:
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def run_install(self, root=None):
        output = io.StringIO()
        with redirect_stdout(output):
            installer.install(str(root or self.root))
        return output.getvalue()


__all__ = [name for name in globals() if not name.startswith("__")]

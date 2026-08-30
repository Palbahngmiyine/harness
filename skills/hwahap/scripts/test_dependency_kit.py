"""Shared dependency test helpers."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).parent
class DependencyIntegrityTests(unittest.TestCase):
    def _load(self, name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    def _copy_scripts(self, directory):
        for name in ("hwahap_state.py", "hwahap_report.py", "hwahap_credentials.py", "install_project_agents.py"):
            shutil.copy2(ROOT / name, directory / name)
__all__ = [name for name in globals() if not name.startswith("__")]

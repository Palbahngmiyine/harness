"""Shared dependency test helpers."""
from __future__ import annotations
import ast
import importlib.util
import os
from pathlib import Path
import re
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
        sources = list(ROOT.glob("hwahap_state*.py"))
        sources.extend(ROOT.glob("hwahap_agent_*.py"))
        sources.extend(ROOT.glob("hwahap_credential_*.py"))
        sources.append(ROOT / "hwahap_state_manifest.json")
        sources.extend(ROOT / name for name in (
            "hwahap_report.py", "hwahap_credentials.py", "install_project_agents.py"))
        for source in sources:
            shutil.copy2(source, directory / source.name)

    def _copy_report_graph(self, directory):
        scripts = directory / "scripts"
        assets = directory / "assets" / "report"
        scripts.mkdir(parents=True)
        assets.mkdir(parents=True)
        sources = list(ROOT.glob("hwahap_report*.py"))
        sources.extend(ROOT.glob("hwahap_credential_*.py"))
        sources.extend((ROOT / "hwahap_report_manifest.json",
                        ROOT / "hwahap_credentials.py"))
        for source in sources:
            shutil.copy2(source, scripts / source.name)
        shutil.copy2(ROOT.parent / "assets" / "report" / "style.css",
                     assets / "style.css")
        return scripts
__all__ = [name for name in globals() if not name.startswith("__")]

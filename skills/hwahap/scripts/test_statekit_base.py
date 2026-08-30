"""Shared imports for state test slices."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

def load_tests(loader, tests, pattern):
    if pattern is None:
        return tests
    return unittest.TestSuite()

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
ROOT = Path(__file__).parent
MODULE_PATH = ROOT / "hwahap_state.py"
hwahap_state = _load("hwahap_state", ROOT / "hwahap_state.py")
hwahap_report = _load("hwahap_report", ROOT / "hwahap_report.py")
installer = _load("install_project_agents", ROOT / "install_project_agents.py")

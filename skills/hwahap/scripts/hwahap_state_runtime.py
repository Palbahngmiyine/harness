"""Shared imports and link registry for verified state modules."""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import hmac
import importlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_records = []
_owners = {}


def register(space: dict) -> None:
    """Remember names imported before a responsibility module defines exports."""
    _records.append((space, frozenset(space)))


def compose() -> tuple[dict, dict]:
    """Link unique responsibility exports after every whole module is imported."""
    exports = {}
    for space, initial in _records:
        for name in space.keys() - initial:
            if name.startswith("__"):
                continue
            if name in exports:
                raise ImportError("duplicate state export")
            exports[name] = space[name]
            _owners[name] = space
    for space, _ in _records:
        space.update(exports)
    return exports, _owners


def publish(name: str, value: object) -> None:
    """Update one linked runtime value in every responsibility module."""
    if name not in _owners:
        raise AttributeError(name)
    for space, _ in _records:
        space[name] = value
    _owners[name][name] = value

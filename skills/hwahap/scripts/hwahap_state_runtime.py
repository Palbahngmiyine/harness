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
_consumers = {}


def register(space: dict) -> None:
    """Remember names imported before a responsibility module defines exports."""
    _records.append((space, frozenset(space)))


def _code_references(code: types.CodeType) -> set[str]:
    names = set(code.co_names)
    for item in code.co_consts:
        if isinstance(item, types.CodeType):
            names.update(_code_references(item))
    return names


def _references(value: object) -> set[str]:
    names = set()
    code = getattr(value, "__code__", None)
    if code is None:
        code = getattr(getattr(value, "__func__", None), "__code__", None)
    if isinstance(code, types.CodeType):
        names.update(_code_references(code))
    if isinstance(value, type):
        for item in vars(value).values():
            names.update(_references(item))
    return names


def compose() -> tuple[dict, dict]:
    """Link only the cross-module names referenced by each responsibility."""
    exports = {}
    for space, initial in _records:
        for name in space.keys() - initial:
            if name.startswith("__"):
                continue
            if name in exports:
                raise ImportError("duplicate state export")
            exports[name] = space[name]
            _owners[name] = space
    for space, initial in _records:
        references = set()
        for name in space.keys() - initial:
            references.update(_references(space[name]))
        for name in references & exports.keys():
            if name in space:
                continue
            space[name] = exports[name]
            _consumers.setdefault(name, []).append(space)
    return exports, _owners


def publish(name: str, value: object) -> None:
    """Update one owner and its narrow set of linked consumers."""
    if name not in _owners:
        raise AttributeError(name)
    for space in _consumers.get(name, ()):
        space[name] = value
    _owners[name][name] = value

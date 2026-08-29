#!/usr/bin/env python3
"""Initialize and validate compact Hwahap orchestration state."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import hmac
import importlib.util
import json
import os
import re
import selectors
import shlex
import shutil
import stat
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

_PIN_REDACTION_ENGINE_SHA256 = "aa2d19d5b4f6af13cc2a53c6d91bda453713d3526a02efe561b6fd939691e687"
_PIN_INSTALLER = "bf42ef51b90725cb76249f595aab7836e708e69b4b9869b69dea30e120139658"
_PIN_REPORT = "696425f380fb0e04b5ec231eecdda3aa97f5fada730e7e5a1c8fdca4d9f3ea5e"
REPORT_SCHEMA_VERSION = 4
REPORT_GENERATOR = {"name": "hwahap-report", "version": 5, "design_system": "material-design-3",
                    "theme_source": "m3-foundations@2026-08-29"}
REPORT_REDACTION_POLICY = "hwahap-report-v4"
_dependency_modules = None

def _sealed_module(filename: str, digest: str, exports: tuple[str, ...], error: str):
    directory = Path(__file__).parent
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    fd = dfd = None
    try:
        dfd = os.open(str(directory), flags)
        d_before = os.fstat(dfd)
        fd = os.open(filename, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=dfd)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid not in (0, os.geteuid())
                or not before.st_mode & 0o444 or before.st_mode & 0o022 or before.st_size > 2 * 1024 * 1024):
            raise ValueError
        data = bytearray()
        while len(data) <= before.st_size:
            chunk = os.read(fd, min(65536, before.st_size + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        d_after = os.fstat(dfd)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        if (bytes(data) and len(data) != before.st_size) or identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or (d_before.st_dev, d_before.st_ino) != (d_after.st_dev, d_after.st_ino):
            raise ValueError
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest):
            raise ValueError
        module = types.ModuleType("_hwahap_sealed_" + filename.replace(".py", ""))
        module.__file__ = str(directory / filename)
        sys.modules[module.__name__] = module
        try:
            exec(compile(bytes(data), "<hwahap-sealed>", "exec"), module.__dict__)
        finally:
            sys.modules.pop(module.__name__, None)
        if any(not hasattr(module, name) for name in exports):
            raise ValueError
        return module
    except Exception:
        raise ImportError(error) from None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        if dfd is not None:
            try:
                os.close(dfd)
            except Exception:
                pass

def _ensure_dependencies() -> None:
    global _dependency_modules, InstallError, is_hwahap_profile_name, source_profiles
    global _shared_contains_sensitive_data
    if _dependency_modules is not None:
        return
    try:
        agent = _sealed_module("install_project_agents.py", _PIN_INSTALLER, ("InstallError", "is_hwahap_profile_name", "source_profiles"), "agent dependency unavailable")
    except ImportError:
        raise HwahapError("HW_AGENT_CONFIG_INVALID", "agent dependency unavailable") from None
    try:
        redaction = _sealed_module("hwahap_redaction.py", _PIN_REDACTION_ENGINE_SHA256, ("contains_sensitive_data",), "redaction dependency unavailable")
    except ImportError:
        raise HwahapError("HW_STATE_INVALID", "redaction dependency unavailable") from None
    InstallError, is_hwahap_profile_name, source_profiles = agent.InstallError, agent.is_hwahap_profile_name, agent.source_profiles
    _shared_contains_sensitive_data = redaction.contains_sensitive_data
    _dependency_modules = (agent, redaction)


SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RUN_STATES = {
    "initialized", "contract_locked", "implementing", "reviewing", "recovering",
    "replanning", "final_review", "completed", "blocked", "failed",
    "awaiting_user", "cancelled",
}
UNIT_STATES = {
    "planned", "implementing", "reviewing", "recovery", "replan_required",
    "passed", "blocked", "failed", "awaiting_user",
}
FAILURE_STATES = {"replan_required", "blocked", "failed", "awaiting_user"}
RUN_FAILURE_STATES = {"blocked", "failed", "awaiting_user"}
FAILURE_CODES = {
    "HW_AGENT_CONFIG_INVALID",
    "HW_SPEC_UNCONFIRMED", "HW_SCOPE_DRIFT", "HW_IMPLEMENTATION_BLOCKED",
    "HW_IMPLEMENTATION_FAILED", "HW_VERIFICATION_FAILED", "HW_REPLAN_REQUIRED",
    "HW_FINAL_REVIEW_FAILED", "HW_MODEL_UNAVAILABLE", "HW_USER_DECISION_REQUIRED",
    "HW_STATE_INVALID", "HW_REPORT_GENERATION_FAILED", "HW_TEST_EXECUTION_DISABLED",
}
PUBLIC_ERROR_MESSAGES = {
    code: message for code, message in {
        "HW_AGENT_CONFIG_INVALID": "installed agent configuration is invalid",
        "HW_SPEC_UNCONFIRMED": "approved specification is unavailable or invalid",
        "HW_SCOPE_DRIFT": "requested change is outside the locked scope",
        "HW_IMPLEMENTATION_BLOCKED": "implementation is blocked",
        "HW_IMPLEMENTATION_FAILED": "implementation failed",
        "HW_VERIFICATION_FAILED": "verification failed",
        "HW_REPLAN_REQUIRED": "replanning is required",
        "HW_FINAL_REVIEW_FAILED": "final review failed",
        "HW_MODEL_UNAVAILABLE": "required model is unavailable",
        "HW_USER_DECISION_REQUIRED": "user decision is required",
        "HW_STATE_INVALID": "state is invalid",
        "HW_REPORT_GENERATION_FAILED": "report generation failed",
        "HW_TEST_EXECUTION_DISABLED": "test execution is disabled",
        "HW_RUN_EXISTS": "run already exists",
    }.items() if code in FAILURE_CODES or code == "HW_RUN_EXISTS"
}
ROLE_MAP = {
    "orchestrator": {"agent": "hwahap-sol-orchestrator", "model": "gpt-5.6-sol", "effort": "xhigh", "fast": "best_effort"},
    "implementer": {"agent": "hwahap-luna-implementer", "model": "gpt-5.6-luna", "effort": "high"},
    "verifier": {"agent": "hwahap-luna-verifier", "model": "gpt-5.6-luna", "effort": "xhigh"},
    "scope_reviewer": {"agent": "hwahap-terra-scope-reviewer", "model": "gpt-5.6-terra", "effort": "xhigh"},
    "final_reviewer": {"agent": "hwahap-sol-final-reviewer", "model": "gpt-5.6-sol", "effort": "ultra", "fallback_effort": "xhigh"},
}
CONTRACT_LISTS = (
    "goals", "non_goals", "allowed_paths", "forbidden_changes",
    "acceptance_criteria", "test_commands",
)
CANDIDATE_FIELDS = frozenset(("status", "summary", "evidence", "expected_effect", "next_action"))
EVENT_FIELDS = (
    "timestamp", "type", "sequence", "entity", "from", "to", "actor", "role",
    "reason", "input_digest", "evidence_refs", "review_round",
)
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIFF_SNAPSHOT_FIELDS = frozenset(("base_commit", "target_commit", "base_tree", "target_tree", "diff_digest", "changed_paths"))
FINAL_REVIEW_ATTEMPT_FIELDS = frozenset(("model", "effort", "status", "thread_id", "evidence", "diff_digest", "diff_snapshot"))
COMMAND_SENSITIVE_PATTERN = re.compile(r"(?ix)(?:\b(?:token|aws_session_token|aws_secret_access_key|aws_access_key_id|github_token|openai_api_key)\s*[:=]\s*\S+|--(?:token|session-token|password|secret|api[_-]?key|private[_-]?key)(?:=|\s+)\S+|\b(?:cookie|set-cookie|authorization|bearer|password|secret|api[_ -]?key|private[_ -]?key)\b\s*[:=]?\s*\S+|https?://[^/\s:@]+:[^/\s@]+@[^\s]+|-----BEGIN [^-]+-----)")
ASSIGNMENT_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELL_CONTROL = re.compile(r"[;|&<>`\x00\r\n]")
_shared_contains_sensitive_data = None
SHELL_WRAPPERS = frozenset(("sh", "bash", "zsh", "dash", "ksh", "fish"))
DIRECT_TEST_TOOLS = frozenset(("pytest", "py.test", "test", "rspec", "shellcheck", "mypy"))
TEST_SUBCOMMANDS = {
    "go": {"test"}, "cargo": {"test", "check", "clippy"}, "swift": {"test"},
    "dotnet": {"test"}, "mix": {"test"}, "npm": {"test", "lint"},
    "pnpm": {"test", "lint"}, "yarn": {"test", "lint"},
}
MAKE_TEST_TARGET = re.compile(r"^(?:test|check|lint|verify|validate)(?:[-_:][A-Za-z0-9_.-]+)?$")
GOAL_MODES = {"unobserved", "bound", "no_active_goal", "unavailable"}
RUN_TERMINAL_STATES = {"completed", "blocked", "failed", "awaiting_user", "cancelled"}
RUN_UNIT_MUTATION_BLOCKED_STATES = RUN_TERMINAL_STATES | {"final_review"}
UNIT_TERMINAL_STATES = {"passed", "blocked", "failed", "awaiting_user"}
RUN_TRANSITIONS = {
    "initialized": {"contract_locked", "blocked", "failed", "awaiting_user", "cancelled"},
    "contract_locked": {"implementing", "blocked", "failed", "awaiting_user", "cancelled"},
    "implementing": {"reviewing", "recovering", "replanning", "blocked", "failed", "awaiting_user"},
    "reviewing": {"implementing", "recovering", "final_review", "replanning", "blocked", "failed", "awaiting_user"},
    "recovering": {"implementing", "reviewing", "replanning", "blocked", "failed", "awaiting_user"},
    "replanning": {"implementing", "blocked", "failed", "awaiting_user"},
    "final_review": {"completed", "awaiting_user"},
}
UNIT_TRANSITIONS = {
    "planned": {"implementing", "blocked", "failed", "awaiting_user"},
    "implementing": {"reviewing", "recovery", "failed", "blocked", "awaiting_user"},
    "reviewing": {"passed", "recovery", "replan_required", "failed", "blocked", "awaiting_user"},
    "recovery": {"implementing", "reviewing", "replan_required", "failed", "blocked", "awaiting_user"},
    "replan_required": {"implementing", "awaiting_user"},
}
AGENT_PROFILE_DIR = Path(__file__).resolve().parents[1] / "assets" / "agents"
SCOPE_DRIFT_ACTOR = "hwahap-sol-orchestrator"
SCOPE_DRIFT_REASON = "requested unit input is not an exact member of the locked contract; waiting for user decision"
SCOPE_DRIFT_RECOVERY = "ask the user to approve a new Goal/contract or provide a corrected in-scope unit"
SCOPE_DRIFT_EVIDENCE_LIMIT = 3
SCOPE_DRIFT_TEXT_LIMIT = 256


class HwahapError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise HwahapError("HW_STATE_INVALID", "invalid command arguments")


_GIT_TIMEOUT_SECONDS = 30
_GIT_METADATA_LIMIT = 1024 * 1024
_GIT_PATH_LIMIT = 4 * 1024 * 1024
_GIT_DIFF_LIMIT = 32 * 1024 * 1024


def _bounded_process_output(command: list[str], cwd: Path, env: dict[str, str],
                            limit: int, timeout: float) -> bytes:
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    if process.stdout is None:
        process.kill()
        raise OSError("process output unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            events = selector.select(min(remaining, 0.1))
            if not events:
                if process.poll() is not None:
                    continue
                continue
            chunk = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > limit:
                raise ValueError("process output limit exceeded")
        if process.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
            raise subprocess.CalledProcessError(process.returncode, command)
        return bytes(output)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        process.stdout.close()


def git_diff_snapshot(workspace: Path, base_commit: object, target_commit: object) -> dict:
    if (not isinstance(base_commit, str) or not GIT_COMMIT.fullmatch(base_commit)
            or not isinstance(target_commit, str) or not GIT_COMMIT.fullmatch(target_commit)):
        raise HwahapError("HW_STATE_INVALID", "invalid Git diff snapshot commits")

    git_executable = shutil.which("git", path=os.defpath)
    if (not git_executable or Path(git_executable).is_symlink()
            or not Path(git_executable).is_file()):
        raise HwahapError("HW_STATE_INVALID", "trusted Git executable is unavailable")
    env = {"PATH": os.defpath}
    env.update({"GIT_NO_REPLACE_OBJECTS": "1", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_ATTR_NOSYSTEM": "1", "LC_ALL": "C", "LANG": "C"})

    def git(args: list[str], limit: int = _GIT_METADATA_LIMIT) -> bytes:
        try:
            return _bounded_process_output([git_executable, *args], workspace, env, limit,
                                           _GIT_TIMEOUT_SECONDS)
        except Exception as exc:
            raise HwahapError("HW_STATE_INVALID", "could not resolve Git diff snapshot") from exc

    try:
        top = git(["rev-parse", "--show-toplevel"]).decode("utf-8").strip()
        git_dir = git(["rev-parse", "--absolute-git-dir"]).decode("utf-8").strip()
        if Path(top).resolve() != workspace.resolve() or not Path(git_dir).is_dir():
            raise ValueError
        base = git(["rev-parse", "--verify", f"{base_commit}^{{commit}}"]).decode("ascii").strip()
        target = git(["rev-parse", "--verify", f"{target_commit}^{{commit}}"]).decode("ascii").strip()
        if base != base_commit or target != target_commit:
            raise ValueError
        base_tree = git(["rev-parse", "--verify", f"{base_commit}^{{tree}}"]).decode("ascii").strip()
        target_tree = git(["rev-parse", "--verify", f"{target_commit}^{{tree}}"]).decode("ascii").strip()
        diff = git(["diff", "--full-index", "--binary", "--no-ext-diff", "--no-textconv", "--no-color",
                    "--diff-algorithm=myers", "--no-indent-heuristic", "--unified=3", "--src-prefix=a/",
                    "--dst-prefix=b/", "--no-renames", base_commit, target_commit, "--"], _GIT_DIFF_LIMIT)
        raw_paths = git(["diff", "--name-only", "-z", "--no-renames", base_commit, target_commit, "--"],
                        _GIT_PATH_LIMIT)
        paths = raw_paths.decode("utf-8").split("\0")
        if paths and paths[-1] == "":
            paths.pop()
        if (not GIT_COMMIT.fullmatch(base_tree) or not GIT_COMMIT.fullmatch(target_tree)
                or not paths or any(not safe_relative_path(path) for path in paths)):
            raise ValueError
    except HwahapError:
        raise
    except Exception as exc:
        raise HwahapError("HW_STATE_INVALID", "invalid Git diff snapshot") from exc
    return {"base_commit": base_commit, "target_commit": target_commit,
            "base_tree": base_tree, "target_tree": target_tree,
            "diff_digest": "sha256:" + hashlib.sha256(diff).hexdigest(),
            "changed_paths": paths}


def validate_diff_snapshot(value: object, workspace: Path | None, label: str, errors: list[str]) -> dict | None:
    if not isinstance(value, dict) or set(value) != DIFF_SNAPSHOT_FIELDS:
        errors.append(f"{label} is incomplete")
        return None
    if (not isinstance(value.get("base_commit"), str) or not GIT_COMMIT.fullmatch(value["base_commit"])
            or not isinstance(value.get("target_commit"), str) or not GIT_COMMIT.fullmatch(value["target_commit"])
            or not isinstance(value.get("base_tree"), str) or not GIT_COMMIT.fullmatch(value["base_tree"])
            or not isinstance(value.get("target_tree"), str) or not GIT_COMMIT.fullmatch(value["target_tree"])
            or not isinstance(value.get("diff_digest"), str) or not SHA256.fullmatch(value["diff_digest"])
            or not isinstance(value.get("changed_paths"), list) or not value["changed_paths"]
            or any(not isinstance(path, str) or not safe_relative_path(path) for path in value["changed_paths"])):
        errors.append(f"{label} is invalid")
        return None
    if workspace is None:
        return value
    try:
        actual = git_diff_snapshot(workspace, value["base_commit"], value["target_commit"])
    except HwahapError:
        errors.append(f"{label} cannot be resolved")
        return None
    if actual != value:
        errors.append(f"{label} does not match the current Git diff")
        return None
    return actual


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HwahapError("HW_STATE_INVALID", "could not read state JSON") from exc
    if not isinstance(value, dict):
        raise HwahapError("HW_STATE_INVALID", "state JSON must contain an object")
    return value


def write_json(path: Path, value: dict) -> None:
    _atomic_replace_bytes(path, _json_bytes(value))


def restore_state_files(originals: tuple[tuple[Path, bytes], ...]) -> None:
    for path, data in originals:
        try:
            _atomic_replace_bytes(path, data)
        except Exception:
            pass


_REPORT_RECOVERY_NAME = ".report-recovery.json"
_REPORT_RECOVERY_FILES = ("run.json", "report-data.json", "report.html", "events.jsonl")
_REPORT_RECOVERY_LIMIT = 128 * 1024 * 1024
_REPORT_TEMP_COUNTER = 0
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600


def _report_recovery_path(run_dir: Path) -> Path:
    return run_dir / _REPORT_RECOVERY_NAME


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_replace_bytes(path: Path, data: bytes) -> None:
    global _REPORT_TEMP_COUNTER
    _REPORT_TEMP_COUNTER += 1
    temp = path.parent / (f".{path.name}.tmp-{os.getpid()}-{_REPORT_TEMP_COUNTER}")
    fd, created = None, False
    try:
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     _PRIVATE_FILE_MODE)
        created = True
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise OSError
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(str(temp), str(path))
        os.chmod(path, _PRIVATE_FILE_MODE, follow_symlinks=False)
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        try:
            if created and (temp.is_file() or temp.is_symlink()):
                temp.unlink()
        except Exception:
            pass
        raise


def _recovery_record(exists: bool, data: bytes) -> dict:
    return {"exists": exists, "length": len(data),
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest() if exists else None,
            "data": base64.b64encode(data).decode("ascii") if exists else None}


def _recovery_setup(operation: str, originals: dict[str, tuple[bool, bytes]], target: dict[str, bytes]) -> tuple[bytes, bytes]:
    if operation not in {"complete", "goal_complete_sync"} or set(originals) != set(_REPORT_RECOVERY_FILES) or set(target) != set(_REPORT_RECOVERY_FILES):
        raise HwahapError("HW_STATE_INVALID", "report recovery journal is invalid")
    identity = operation.encode() + b"".join(originals[name][1] for name in _REPORT_RECOVERY_FILES) + b"".join(target[name] for name in _REPORT_RECOVERY_FILES)
    transaction_id = "sha256:" + hashlib.sha256(identity).hexdigest()
    value = {"schema_version": 2, "transaction_id": transaction_id, "operation": operation,
             "originals": {name: _recovery_record(*originals[name]) for name in _REPORT_RECOVERY_FILES},
             "target": {name: _recovery_record(True, target[name]) for name in _REPORT_RECOVERY_FILES}}
    journal_bytes = _json_bytes(value)
    journal_sha = "sha256:" + hashlib.sha256(journal_bytes).hexdigest()
    marker = {"transaction_id": transaction_id, "operation": operation, "journal_sha256": journal_sha}
    marker_run = json.loads(target["run.json"].decode("utf-8"))
    marker_run["report_transaction"] = marker
    return journal_bytes, _json_bytes(marker_run)


def _write_report_recovery_journal(run_dir: Path, journal_bytes: bytes) -> None:
    path = _report_recovery_path(run_dir)
    if path.is_symlink() or path.exists():
        raise HwahapError("HW_STATE_INVALID", "report recovery journal is invalid")
    fd = None
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        if os.fstat(fd).st_nlink != 1:
            raise OSError
        offset = 0
        while offset < len(journal_bytes):
            offset += os.write(fd, journal_bytes[offset:])
        os.close(fd)
        fd = None
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        try:
            if path.is_file() and not path.is_symlink():
                path.unlink()
        except Exception:
            pass
        raise HwahapError("HW_STATE_INVALID", "could not write report recovery journal") from None


def _read_report_recovery_journal(run_dir: Path) -> dict[str, tuple[bool, bytes]] | None:
    path = _report_recovery_path(run_dir)
    try:
        if path.is_symlink():
            raise ValueError
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > _REPORT_RECOVERY_LIMIT:
            raise ValueError
        journal_bytes = path.read_bytes()
        if len(journal_bytes) > _REPORT_RECOVERY_LIMIT:
            raise ValueError
        journal_digest = "sha256:" + hashlib.sha256(journal_bytes).hexdigest()
        value = json.loads(journal_bytes.decode("utf-8"))
        if not isinstance(value, dict) or set(value) != {"schema_version", "transaction_id", "operation", "originals", "target"} or value.get("schema_version") != 2:
            raise ValueError
        if not isinstance(value.get("transaction_id"), str) or not SHA256.fullmatch(value["transaction_id"]):
            raise ValueError
        if value.get("operation") not in {"complete", "goal_complete_sync"}:
            raise ValueError
        files = value.get("originals")
        target = value.get("target")
        if not isinstance(files, dict) or not isinstance(target, dict) or set(files) != set(_REPORT_RECOVERY_FILES) or set(target) != set(_REPORT_RECOVERY_FILES):
            raise ValueError
        result: dict[str, tuple[bool, bytes]] = {}
        for name in _REPORT_RECOVERY_FILES:
            for item in (files[name], target[name]):
                if not isinstance(item, dict) or set(item) != {"exists", "length", "sha256", "data"} or not isinstance(item.get("exists"), bool):
                    raise ValueError
                data = base64.b64decode(item["data"], validate=True) if item["exists"] and isinstance(item.get("data"), str) else b""
                if item["exists"] != (item.get("data") is not None) or item.get("length") != len(data) or item.get("sha256") != ("sha256:" + hashlib.sha256(data).hexdigest() if item["exists"] else None):
                    raise ValueError
            result[name] = (bool(files[name]["exists"]), base64.b64decode(files[name]["data"], validate=True) if files[name]["exists"] else b"")
        result["__target__"] = {name: base64.b64decode(target[name]["data"], validate=True) for name in _REPORT_RECOVERY_FILES}  # type: ignore[assignment]
        result["__meta__"] = {"transaction_id": value["transaction_id"], "operation": value["operation"], "journal_sha256": journal_digest}  # type: ignore[assignment]
        if (not result["run.json"][0] or not result["events.jsonl"][0]
                or value["operation"] == "complete" and (result["report-data.json"][0] or result["report.html"][0])
                or value["operation"] == "goal_complete_sync" and (not result["report-data.json"][0] or not result["report.html"][0])):
            raise ValueError
        return result
    except Exception:
        raise HwahapError("HW_STATE_INVALID", "report recovery journal is invalid") from None


def _restore_report_recovery(run_dir: Path, originals: dict[str, tuple[bool, bytes]], marker_run: bytes | None = None) -> bool:
    complete = True
    for name in _REPORT_RECOVERY_FILES:
        exists, data = originals[name]
        path = run_dir / name
        try:
            if path.is_symlink() or path.is_dir() or (path.exists() and path.stat().st_nlink != 1):
                complete = False
                continue
            if exists:
                if path.exists() and not path.is_file():
                    complete = False
                    continue
                _atomic_replace_bytes(path, data)
            elif path.exists():
                path.unlink()
        except Exception:
            complete = False
    journal = _report_recovery_path(run_dir)
    if not complete and marker_run is not None:
        try:
            _atomic_replace_bytes(run_dir / "run.json", marker_run)
        except Exception:
            pass
    if complete:
        try:
            if journal.is_symlink() or (journal.exists() and (not journal.is_file() or journal.stat().st_nlink != 1)):
                complete = False
            elif journal.exists():
                journal.unlink()
        except Exception:
            complete = False
    return complete


def _clear_report_recovery_journal(run_dir: Path) -> bool:
    journal = _report_recovery_path(run_dir)
    try:
        if journal.is_symlink() or (journal.exists() and (not journal.is_file() or journal.stat().st_nlink != 1)):
            return False
        if journal.exists():
            journal.unlink()
        return True
    except Exception:
        return False


def _recover_report_transaction(run_dir: Path) -> None:
    journal = _read_report_recovery_journal(run_dir)
    if journal is None:
        run_path = run_dir / "run.json"
        try:
            if run_path.is_file() and not run_path.is_symlink():
                try:
                    marker = json.loads(run_path.read_bytes().decode("utf-8")).get("report_transaction")
                except (UnicodeError, json.JSONDecodeError):
                    return
                if marker is not None:
                    raise HwahapError("HW_STATE_INVALID", "orphan report recovery marker")
        except HwahapError:
            raise
        except Exception:
            raise HwahapError("HW_STATE_INVALID", "could not inspect report recovery marker") from None
        return
    originals = {name: journal[name] for name in _REPORT_RECOVERY_FILES}
    target = journal["__target__"]
    meta = journal["__meta__"]
    current: dict[str, bytes | None] = {}
    for name in _REPORT_RECOVERY_FILES:
        path = run_dir / name
        try:
            if path.is_symlink() or path.is_dir() or (path.exists() and path.stat().st_nlink != 1):
                raise ValueError
            if path.exists() and not path.is_file():
                raise ValueError
            current[name] = path.read_bytes() if path.exists() else None
        except HwahapError:
            raise
        except Exception:
            raise HwahapError("HW_STATE_INVALID", "could not inspect report recovery targets") from None
    original_set = {name: data if exists else None for name, (exists, data) in originals.items()}
    target_set = {name: target[name] for name in _REPORT_RECOVERY_FILES}
    marker = None
    try:
        run_value = json.loads((run_dir / "run.json").read_bytes().decode("utf-8"))
        marker = run_value.get("report_transaction") if isinstance(run_value, dict) else None
    except Exception:
        raise HwahapError("HW_STATE_INVALID", "report recovery marker is invalid") from None
    if marker is not None and (not isinstance(marker, dict) or set(marker) != {"transaction_id", "operation", "journal_sha256"}
                               or marker.get("transaction_id") != meta["transaction_id"]
                               or marker.get("operation") != meta["operation"]
                               or marker.get("journal_sha256") != meta["journal_sha256"]):
        raise HwahapError("HW_STATE_INVALID", "report recovery marker is invalid")
    if marker is None:
        if current in (original_set, target_set):
            if not _clear_report_recovery_journal(run_dir):
                raise HwahapError("HW_STATE_INVALID", "report recovery is incomplete")
            return
        raise HwahapError("HW_STATE_INVALID", "report recovery journal is unbound")
    marker_run = json.loads(target["run.json"].decode("utf-8"))
    marker_run["report_transaction"] = marker
    marker_set = dict(target_set, **{"run.json": _json_bytes(marker_run)})
    if current == marker_set:
        _atomic_replace_bytes(run_dir / "run.json", target["run.json"])
        if not _clear_report_recovery_journal(run_dir):
            raise HwahapError("HW_STATE_INVALID", "report recovery is incomplete")
        return
    marker_run = _json_bytes(dict(json.loads(target["run.json"].decode("utf-8")), report_transaction=marker))
    if not _restore_report_recovery(run_dir, originals, marker_run):
        raise HwahapError("HW_STATE_INVALID", "report recovery is incomplete")


def remove_path_best_effort(path: Path) -> None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    except Exception:
        pass


def verify_installed_agents(workspace: Path) -> dict[str, str]:
    _ensure_dependencies()
    codex_dir = workspace / ".codex"
    target_dir = codex_dir / "agents"
    try:
        for path in (codex_dir, target_dir):
            if lexical_path_has_symlink(path) or path.is_symlink() or not path.is_dir():
                raise HwahapError("HW_AGENT_CONFIG_INVALID", "project agent directory is missing or unsafe")
    except HwahapError:
        raise
    except (OSError, UnicodeError) as exc:
        raise HwahapError("HW_AGENT_CONFIG_INVALID", "cannot inspect project agent directories") from exc
    try:
        profiles = source_profiles(AGENT_PROFILE_DIR)
    except InstallError as exc:
        raise HwahapError("HW_AGENT_CONFIG_INVALID", "Hwahap source profiles are invalid") from exc
    required_names = {source.name for source, _ in profiles}
    try:
        target_names = {path.name for path in target_dir.iterdir() if is_hwahap_profile_name(path.name)}
    except (OSError, UnicodeError) as exc:
        raise HwahapError("HW_AGENT_CONFIG_INVALID", "cannot inspect installed Hwahap profiles") from exc
    if target_names != required_names:
        raise HwahapError("HW_AGENT_CONFIG_INVALID", "installed Hwahap profiles are not exactly the required set")
    hashes: dict[str, str] = {}
    for source, source_bytes in profiles:
        target = target_dir / source.name
        try:
            if source.is_symlink() or not source.is_file() or target.is_symlink() or not target.is_file():
                raise HwahapError("HW_AGENT_CONFIG_INVALID", "installed Hwahap profile is missing or unsafe")
            if target.read_bytes() != source_bytes:
                raise HwahapError("HW_AGENT_CONFIG_INVALID", "agent profile differs from Hwahap")
        except HwahapError:
            raise
        except (OSError, UnicodeError) as exc:
            raise HwahapError("HW_AGENT_CONFIG_INVALID", "cannot read installed Hwahap profile") from exc
        hashes[source.name] = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    return hashes


def canonical_contract_digest(contract: dict) -> str:
    payload = {key: value for key, value in contract.items() if key != "lock_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", text, re.DOTALL)
    if not match:
        raise HwahapError("HW_SPEC_UNCONFIRMED", "spec has no YAML frontmatter")
    if contains_sensitive_data(match.group(1)):
        raise HwahapError("HW_STATE_INVALID", "frontmatter contains sensitive data")
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"\'')
    if values.get("status") != "prfaq" or not values.get("confirmed_at"):
        raise HwahapError("HW_SPEC_UNCONFIRMED", "spec must have status=prfaq and confirmed_at")
    if not values.get("title"):
        raise HwahapError("HW_SPEC_UNCONFIRMED", "spec title is required")
    return values


def state_paths(workspace: Path, run_id: str) -> tuple[Path, Path]:
    if not SLUG.fullmatch(run_id):
        raise HwahapError("HW_STATE_INVALID", "unsafe run ID")
    hwahap = workspace / ".hwahap"
    runs_dir = hwahap / "runs"
    run_dir = runs_dir / run_id
    for label, path in ((".hwahap", hwahap), ("runs", runs_dir), ("run", run_dir)):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise HwahapError("HW_STATE_INVALID", f"{label} must be a real directory")
        if path.exists():
            status = path.stat()
            if status.st_uid != os.geteuid() or status.st_mode & 0o077:
                raise HwahapError("HW_STATE_INVALID", f"{label} directory permissions are unsafe")
    return hwahap, run_dir


def _single_regular_file(path: Path) -> bool:
    try:
        status = path.stat(follow_symlinks=False)
        return (stat.S_ISREG(status.st_mode) and status.st_nlink == 1
                and status.st_uid == os.geteuid() and status.st_mode & 0o077 == 0)
    except (OSError, UnicodeError):
        raise HwahapError("HW_STATE_INVALID", "state file is invalid") from None


def _require_hwahap_ignored(workspace: Path) -> None:
    git_executable = shutil.which("git", path=os.defpath)
    if not git_executable or Path(git_executable).is_symlink() or not Path(git_executable).is_file():
        return
    env = {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull, "LC_ALL": "C", "LANG": "C"}
    try:
        inside = subprocess.run(
            [git_executable, "rev-parse", "--is-inside-work-tree"], cwd=workspace, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=False)
        if inside.returncode != 0:
            return
        ignored = subprocess.run(
            [git_executable, "check-ignore", "-q", "--no-index", "--", ".hwahap/probe"],
            cwd=workspace, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HwahapError("HW_STATE_INVALID", "could not verify .hwahap ignore policy") from exc
    if ignored.returncode != 0:
        raise HwahapError("HW_STATE_INVALID", ".hwahap must be excluded by Git ignore policy")


def lexical_path_has_symlink(path: Path) -> bool:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    for part in path.parts:
        if part in (path.anchor, ""):
            continue
        current /= part
        if current.is_symlink():
            return True
    return False


def init_run(args: argparse.Namespace) -> None:
    workspace_arg = Path(args.workspace).expanduser()
    if lexical_path_has_symlink(workspace_arg):
        raise HwahapError("HW_STATE_INVALID", "workspace must not use symlink components")
    workspace = workspace_arg.resolve()
    spec_arg = Path(args.spec).expanduser()
    if lexical_path_has_symlink(spec_arg):
        raise HwahapError("HW_SPEC_UNCONFIRMED", "spec must not use symlink components")
    spec = spec_arg.resolve()
    if not workspace.is_dir():
        raise HwahapError("HW_STATE_INVALID", "workspace must be a real directory")
    _require_hwahap_ignored(workspace)
    if not spec.is_file():
        raise HwahapError("HW_SPEC_UNCONFIRMED", "spec must be a regular file")
    try:
        meta = frontmatter(spec)
        spec_bytes = spec.read_bytes()
    except (OSError, UnicodeError):
        raise HwahapError("HW_SPEC_UNCONFIRMED", "spec cannot be read as approved UTF-8")
    agent_profiles = verify_installed_agents(workspace)
    digest = hashlib.sha256(spec_bytes).hexdigest()
    _, run_dir = state_paths(workspace, args.goal_id)
    contract_path = run_dir / "contract.json"
    if run_dir.exists():
        units_dir = run_dir / "units"
        for path in (contract_path, run_dir / "run.json", run_dir / "events.jsonl"):
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise HwahapError("HW_STATE_INVALID", f"{path.name} must be a real file")
        if units_dir.is_symlink() or (units_dir.exists() and not units_dir.is_dir()):
            raise HwahapError("HW_STATE_INVALID", "units must be a real directory")
        if units_dir.is_dir():
            read_unit_files(units_dir)
        if contract_path.is_file():
            existing = read_json(contract_path)
            existing_spec = existing.get("spec")
            if not isinstance(existing_spec, dict):
                raise HwahapError("HW_STATE_INVALID", "spec must be an object")
            if existing_spec.get("sha256") == digest:
                validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.goal_id, quiet=True))
                print(f"HW_OK: run={args.goal_id} already initialized")
                return
        raise HwahapError("HW_RUN_EXISTS", f"run {args.goal_id} already exists with different state")
    now = utc_now()
    source = str(spec.relative_to(workspace)) if spec.is_relative_to(workspace) else str(spec)
    contract = {
        "schema_version": 1, "goal_id": args.goal_id, "goal": meta["title"],
        "spec": {"source": source, "sha256": digest, "confirmed_at": meta["confirmed_at"]},
        "locked": False, "lock_sha256": None,
        **{field: [] for field in CONTRACT_LISTS},
    }
    run = {
        "schema_version": 1, "goal_id": args.goal_id, "status": "initialized",
        "started_at": now, "completed_at": None, "roles": ROLE_MAP,
        "agent_profiles": agent_profiles,
        "metrics": {
            "token_usage": {"availability": "unavailable", "reason": "platform aggregate not exposed", "source": None, "total": None},
            "unit_count": 0, "agent_runs": {"availability": "unavailable", "reason": "platform aggregate not exposed", "source": None, "total": None}, "review_rounds": 0, "recoveries": 0,
            "replans": 0, "scope_deviations": 0, "test_runs": 0, "elapsed_seconds": 0,
        },
        "fast_status": "unknown", "deviations": [], "deferred_security": [],
        "improvement_candidates": [],
        "final_review": {"status": "pending", "attempts": []},
        "report": {
            "schema_version": REPORT_SCHEMA_VERSION, "status": "pending",
            "generator": REPORT_GENERATOR.copy(),
            "source_payload_sha256": None,
            "data": {"path": "report-data.json", "file_sha256": None},
            "html": {"path": "report.html", "file_sha256": None},
            "generated_at": None, "redaction_policy": REPORT_REDACTION_POLICY,
        },
        "goal_link": {
            "current": {
                "mode": "unobserved", "source": None, "thread_id": None,
                "external_status": "unknown", "objective_sha256": None,
                "receipt_sha256": None, "reason": "Goal not observed",
                "evidence": ["init"], "observed_at": now, "sync_result": None, "token_total": None,
                "completion_sync": "pending",
            },
            "history": [],
        },
    }
    initial_errors: list[str] = []
    validate_state_strings(contract, "contract", initial_errors)
    validate_state_strings(run, "run", initial_errors)
    if initial_errors:
        raise HwahapError("HW_STATE_INVALID", "initial state contains sensitive data")
    run_path = run_dir / "run.json"
    events_path = run_dir / "events.jsonl"
    units_dir = run_dir / "units"
    parent_dirs = (workspace / ".hwahap", workspace / ".hwahap" / "runs")
    parent_existed = {path: path.exists() for path in parent_dirs}
    new_files = (contract_path, run_path, events_path)
    try:
        units_dir.mkdir(parents=True, mode=_PRIVATE_DIRECTORY_MODE)
        for directory in (*parent_dirs, run_dir, units_dir):
            os.chmod(directory, _PRIVATE_DIRECTORY_MODE, follow_symlinks=False)
        write_json(contract_path, contract)
        write_json(run_path, run)
        _atomic_replace_bytes(events_path, b"")
    except Exception as exc:
        for path in new_files:
            remove_path_best_effort(path)
        for path in (units_dir, run_dir, *reversed(parent_dirs)):
            if path not in parent_existed or not parent_existed[path]:
                remove_path_best_effort(path)
        raise HwahapError("HW_STATE_INVALID", "could not initialize run state") from exc
    print(f"HW_OK: run={args.goal_id} initialized path={run_dir}")


def command_paths(workspace_arg: str, run_id: str) -> tuple[Path, Path, Path, Path]:
    workspace_arg_path = Path(workspace_arg).expanduser()
    if lexical_path_has_symlink(workspace_arg_path):
        raise HwahapError("HW_STATE_INVALID", "workspace must not use symlink components")
    workspace = workspace_arg_path.resolve()
    _, run_dir = state_paths(workspace, run_id)
    _recover_report_transaction(run_dir)
    return workspace, run_dir, run_dir / "contract.json", run_dir / "run.json"


def report_module():
    try:
        return _sealed_module("hwahap_report.py", _PIN_REPORT,
                              ("build_payload", "canonical_payload_bytes", "canonical_payload_digest",
                               "validate_report_data_bytes", "render_report", "validate_report_bytes"),
                              "report dependency unavailable")
    except Exception:
        raise HwahapError("HW_REPORT_GENERATION_FAILED", "report dependency unavailable") from None


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def report_state_digests(contract_path: Path, events_path: Path, units_dir: Path) -> dict[str, str]:
    unit_files = read_unit_files(units_dir)
    unit_bytes = b"".join(path.name.encode() + b"\0" + raw for path, raw, _ in unit_files)
    return {
        "contract": sha256_file(contract_path),
        "events": sha256_file(events_path),
        "units": "sha256:" + hashlib.sha256(unit_bytes).hexdigest(),
    }


def prepare_report_artifacts(workspace: Path | str, contract: dict, run: dict,
                             units: list[dict], events: list[dict], digests: dict[str, str]) -> dict[str, Any]:
    try:
        module = report_module()
        payload = module.build_payload(workspace, contract, run, units, events, digests,
                                       build_scope_audit(run, contract, units))
        data_bytes = module.canonical_payload_bytes(payload)
        source_digest = module.canonical_payload_digest(payload)
        module.validate_report_data_bytes(data_bytes, payload, source_digest)
        data_digest = "sha256:" + hashlib.sha256(data_bytes).hexdigest()
        if source_digest != data_digest:
            raise ValueError
        html_bytes = module.render_report(payload, source_digest)
        module.validate_report_bytes(html_bytes, source_digest, payload)
        return {"payload": payload, "data_bytes": data_bytes, "html_bytes": html_bytes,
                "source_payload_sha256": source_digest, "data_file_sha256": data_digest,
                "html_file_sha256": "sha256:" + hashlib.sha256(html_bytes).hexdigest()}
    except Exception:
        raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not prepare report artifacts") from None


def unit_paths_for_read(units_dir: Path) -> list[Path]:
    try:
        paths = sorted(units_dir.iterdir())
        for path in paths:
            if (not _single_regular_file(path) or path.suffix != ".json"
                    or not SLUG.fullmatch(path.stem)):
                raise HwahapError("HW_STATE_INVALID", "units contains an unexpected entry")
        return paths
    except HwahapError:
        raise
    except (OSError, UnicodeError) as exc:
        raise HwahapError("HW_STATE_INVALID", "cannot inspect units directory") from exc


def read_unit_files(units_dir: Path) -> list[tuple[Path, bytes, dict]]:
    try:
        files = []
        for path in unit_paths_for_read(units_dir):
            raw = path.read_bytes()
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise HwahapError("HW_STATE_INVALID", "unit JSON must contain an object")
            files.append((path, raw, value))
        return files
    except HwahapError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HwahapError("HW_STATE_INVALID", "could not read state JSON") from exc


def parse_events(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
    return events


def validate_report_schema(run: dict, run_dir: Path, contract: dict, units: list[dict], errors: list[str]) -> None:
    report = run.get("report")
    required = {"schema_version", "status", "generator", "source_payload_sha256", "data", "html", "generated_at", "redaction_policy"}
    if not isinstance(report, dict) or not required.issubset(report):
        errors.append("report receipt is incomplete")
        return
    generator = report.get("generator")
    data_meta = report.get("data") if isinstance(report.get("data"), dict) else None
    html_meta = report.get("html") if isinstance(report.get("html"), dict) else None
    if (report.get("schema_version") != REPORT_SCHEMA_VERSION or report.get("redaction_policy") != REPORT_REDACTION_POLICY
            or generator != REPORT_GENERATOR
            or report.get("data") != {"path": "report-data.json", "file_sha256": data_meta.get("file_sha256") if data_meta else None}
            or report.get("html") != {"path": "report.html", "file_sha256": html_meta.get("file_sha256") if html_meta else None}):
        errors.append("report receipt metadata is invalid")
        return
    data_path, report_path = run_dir / "report-data.json", run_dir / "report.html"
    if report.get("status") == "pending":
        if (run.get("status") == "completed" or report.get("source_payload_sha256") is not None
                or report.get("generated_at") is not None
                or (data_meta and data_meta.get("file_sha256") is not None)
                or (html_meta and html_meta.get("file_sha256") is not None)):
            errors.append("pending report is invalid for completed run")
        if any(path.exists() or path.is_symlink() for path in (data_path, report_path)):
            errors.append("pending report must not have report artifacts")
        return
    if report.get("status") != "completed":
        errors.append("report status is invalid")
        return
    if run.get("status") != "completed" or not required_text(report.get("generated_at")):
        errors.append("completed report requires completed run and generated_at")
    if any(not _single_regular_file(path) for path in (data_path, report_path)):
        errors.append("completed report artifacts must be regular files")
        return
    if not isinstance(report.get("source_payload_sha256"), str) or not SHA256.fullmatch(report["source_payload_sha256"]):
        errors.append("report source digest is invalid")
    for artifact in (report.get("data"), report.get("html")):
        if not isinstance(artifact, dict) or not isinstance(artifact.get("file_sha256"), str) or not SHA256.fullmatch(artifact["file_sha256"]):
            errors.append("report artifact digest is invalid")
    try:
        events = parse_events(run_dir / "events.jsonl")
        digests = report_state_digests(run_dir / "contract.json", run_dir / "events.jsonl", run_dir / "units")
        artifacts = prepare_report_artifacts(run_dir.parents[2], contract, run, units, events, digests)
        current_goal = run.get("goal_link", {}).get("current", {}) if isinstance(run.get("goal_link"), dict) else {}
        if isinstance(current_goal, dict) and current_goal.get("source") == "codex.update_goal":
            expected_generated_at = current_goal.get("observed_at")
        else:
            completed = [event.get("timestamp") for event in events
                         if event.get("entity") == "run" and event.get("from") == "final_review" and event.get("to") == "completed"]
            expected_generated_at = completed[-1] if completed else None
        if report.get("generated_at") != expected_generated_at:
            errors.append("report generated_at does not match authoritative state event")
        if artifacts["source_payload_sha256"] != report.get("source_payload_sha256"):
            errors.append("report source digest does not match state")
        data = data_path.read_bytes()
        report_bytes = report_path.read_bytes()
        data_digest = "sha256:" + hashlib.sha256(data).hexdigest()
        if data_digest != report.get("source_payload_sha256") or data_digest != report.get("data", {}).get("file_sha256"):
            errors.append("report data digest does not match contents")
        html_digest = "sha256:" + hashlib.sha256(report_bytes).hexdigest()
        if html_digest != report.get("html", {}).get("file_sha256"):
            errors.append("report file digest does not match contents")
        if report.get("html", {}).get("file_sha256") != artifacts["html_file_sha256"]:
            errors.append("report file digest does not match regenerated artifact")
        if report_bytes != artifacts["html_bytes"]:
            errors.append("report HTML does not match canonical renderer")
        module = report_module()
        if json.loads(data.decode("utf-8")) != artifacts["payload"]:
            errors.append("report data does not match state")
        module.validate_report_data_bytes(data, artifacts["payload"], artifacts["source_payload_sha256"])
        module.validate_report_bytes(report_bytes, artifacts["source_payload_sha256"], artifacts["payload"])
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, HwahapError):
        errors.append("report validation failed")


def complete_run(args: argparse.Namespace) -> None:
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    events_path = run_dir / "events.jsonl"
    data_path = run_dir / "report-data.json"
    report_path = run_dir / "report.html"
    if any(path.exists() or path.is_symlink() for path in (data_path, report_path)):
        raise HwahapError("HW_STATE_INVALID", "report artifacts already exist; complete will not overwrite them")
    contract, run = read_json(contract_path), read_json(run_path)
    unit_files = read_unit_files(run_dir / "units")
    unit_paths = [path for path, _, _ in unit_files]
    units = [unit for _, _, unit in unit_files]
    final_errors: list[str] = []
    validate_final_review(run.get("final_review"), True, final_errors, workspace)
    final_status = run.get("final_review", {}).get("status") if isinstance(run.get("final_review"), dict) else None
    goal = run.get("goal_link", {}).get("current", {}) if isinstance(run.get("goal_link"), dict) else {}
    report = run.get("report")
    if (run.get("status") != "final_review" or final_status != "pass"
            or final_errors or not contract.get("locked") or not units or any(unit.get("status") != "passed" for unit in units)):
        raise HwahapError("HW_STATE_INVALID", "complete requires a valid final_review, locked contract, and passed units")
    final_digest = final_review_passing_digest(run.get("final_review"), workspace)
    if (not isinstance(args.input_digest, str) or not SHA256.fullmatch(args.input_digest)
            or not isinstance(final_digest, str) or args.input_digest != final_digest):
        raise HwahapError("HW_STATE_INVALID", "complete input digest must match the final passing review digest")
    if not isinstance(goal, dict) or goal.get("mode") == "unobserved":
        raise HwahapError("HW_STATE_INVALID", "complete requires an observed Goal link")
    if not isinstance(report, dict) or report.get("status") != "pending":
        raise HwahapError("HW_STATE_INVALID", "complete requires a pending report receipt")
    original_run, original_events = run_path.read_bytes(), events_path.read_bytes()
    originals = {
        "run.json": (True, original_run), "report-data.json": (False, b""),
        "report.html": (False, b""), "events.jsonl": (True, original_events),
    }
    marker_run_bytes = None
    try:
        events = parse_events(events_path)
        event = transition_event(len(events) + 1, "run", "final_review", "completed", argparse.Namespace(
            actor=args.actor, role="orchestrator", reason=args.reason,
            input_digest=args.input_digest, evidence_ref=args.evidence_ref, review_round=0,
        ))
        completed_at = utc_now()
        started = datetime.fromisoformat(str(run.get("started_at")).replace("Z", "+00:00"))
        elapsed = max(0, int((datetime.fromisoformat(completed_at) - started).total_seconds()))
        histories = [unit.get("review_history", []) for unit in units]
        metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        metrics.update({
            "unit_count": len(units), "review_rounds": sum(len(history) for history in histories if isinstance(history, list)),
            "recoveries": sum(bool(history and history[0].get("outcome") == "fail") for history in histories if isinstance(history, list)),
            "replans": sum(sum(record.get("kind") in {"sol_replan", "recursive_improvement"} for record in unit.get("improvement_history", []) if isinstance(record, dict)) for unit in units),
            "scope_deviations": len(run.get("deviations", [])) if isinstance(run.get("deviations"), list) else 0,
            "test_runs": sum(len(unit.get("test_receipts", [])) for unit in units if isinstance(unit.get("test_receipts"), list)),
            "elapsed_seconds": elapsed,
        })
        working_run = json.loads(json.dumps(run))
        working_run.update({"status": "completed", "completed_at": completed_at, "metrics": metrics})
        completed_events = events + [event]
        separator = b"\n" if original_events and not original_events.endswith(b"\n") else b""
        event_bytes = original_events + separator + (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        unit_bytes = b"".join(path.name.encode() + b"\0" + raw for path, raw, _ in unit_files)
        digests = {
            "contract": sha256_file(contract_path), "events": "sha256:" + hashlib.sha256(event_bytes).hexdigest(),
            "units": "sha256:" + hashlib.sha256(unit_bytes).hexdigest(),
        }
        artifacts = prepare_report_artifacts(workspace, contract, working_run, units, completed_events, digests)
        source_digest = artifacts["source_payload_sha256"]
        report_bytes = artifacts["html_bytes"]
        working_run["report"] = {**report, "schema_version": REPORT_SCHEMA_VERSION, "status": "completed",
                                  "generator": REPORT_GENERATOR.copy(),
                                  "source_payload_sha256": source_digest,
                                  "data": {"path": "report-data.json", "file_sha256": artifacts["data_file_sha256"]},
                                  "html": {"path": "report.html", "file_sha256": artifacts["html_file_sha256"]},
                                  "redaction_policy": REPORT_REDACTION_POLICY, "generated_at": event["timestamp"]}
        target = {"run.json": _json_bytes(working_run), "report-data.json": artifacts["data_bytes"],
                  "report.html": report_bytes, "events.jsonl": event_bytes}
        journal_bytes, marker_run_bytes = _recovery_setup("complete", originals, target)
        _write_report_recovery_journal(run_dir, journal_bytes)
        _atomic_replace_bytes(run_path, marker_run_bytes)
        _atomic_replace_bytes(data_path, artifacts["data_bytes"])
        _atomic_replace_bytes(report_path, report_bytes)
        _atomic_replace_bytes(run_path, target["run.json"])
        _atomic_replace_bytes(events_path, event_bytes)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True, _skip_recovery=True))
        if not _clear_report_recovery_journal(run_dir):
            raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not finalize completed report")
    except Exception:
        _restore_report_recovery(run_dir, originals, marker_run_bytes)
        raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not generate completed report") from None
    print(f"HW_OK: run={args.run_id} completed report={report_path}")


def transition_event(sequence: int, entity: str, source: str, target: str,
                     args: argparse.Namespace) -> dict:
    return {
        "timestamp": utc_now(), "type": "state_transition", "sequence": sequence,
        "entity": entity, "from": source, "to": target, "actor": args.actor,
        "role": args.role, "reason": args.reason, "input_digest": args.input_digest,
        "evidence_refs": args.evidence_ref, "review_round": args.review_round,
    }


def lock_contract(args: argparse.Namespace) -> None:
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    contract, run = read_json(contract_path), read_json(run_path)
    events_path = run_dir / "events.jsonl"
    if contract.get("locked") or run.get("status") != "initialized" or events_path.read_text(encoding="utf-8").strip():
        raise HwahapError("HW_STATE_INVALID", "contract lock requires a fresh initialized run")
    if any(not isinstance(contract.get(field), list) or not contract[field] for field in CONTRACT_LISTS):
        raise HwahapError("HW_STATE_INVALID", "fill every contract list before locking")
    if any(not safe_test_command(command) for command in contract["test_commands"]):
        raise HwahapError("HW_STATE_INVALID", "test command contains sensitive data")
    original = (
        (contract_path, contract_path.read_bytes()),
        (run_path, run_path.read_bytes()),
        (events_path, events_path.read_bytes()),
    )
    contract["locked"] = True
    contract["lock_sha256"] = canonical_contract_digest(contract)
    run["status"] = "contract_locked"
    event = transition_event(1, "run", "initialized", "contract_locked", argparse.Namespace(
        actor=args.actor, role="orchestrator", reason=args.reason,
        input_digest=contract["lock_sha256"], evidence_ref=args.evidence_ref, review_round=0,
    ))
    try:
        write_json(contract_path, contract)
        write_json(run_path, run)
        _atomic_replace_bytes(events_path, (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(original)
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_STATE_INVALID", "could not update contract state") from exc
    print(f"HW_OK: run={args.run_id} contract_locked digest={contract['lock_sha256']}")


def require_run_unit_mutation_allowed(run_path: Path) -> dict:
    run = read_json(run_path)
    if run.get("status") in RUN_UNIT_MUTATION_BLOCKED_STATES:
        raise HwahapError("HW_STATE_INVALID", "unit mutation is forbidden after final_review or run termination")
    return run


def require_safe_unit_id(unit_id: object) -> str:
    if not isinstance(unit_id, str) or not SLUG.fullmatch(unit_id):
        raise HwahapError("HW_STATE_INVALID", "unsafe unit ID")
    return unit_id


def require_single_implementing_unit(run_dir: Path, unit_id: str) -> None:
    active = []
    for path in sorted((run_dir / "units").glob("*.json")):
        unit = read_json(path)
        if unit.get("unit_id") != unit_id and unit.get("status") not in {"planned", "passed"}:
            active.append(str(unit.get("unit_id")))
    if active:
        raise HwahapError("HW_STATE_INVALID", "only one unit may be unresolved")


def validate_final_review_units(units: list[dict], contract: dict, errors: list[str], workspace: Path | None = None) -> None:
    if not units:
        errors.append("final_review requires at least one passed unit")
        return
    seen: set[str] = set()
    for unit in units:
        if unit.get("status") != "passed":
            errors.append(f"{unit.get('unit_id')}: final_review requires a passed unit")
        validate_unit(unit, contract, seen, errors, workspace)


def validate_final_review_snapshot_chain(final: object, units: list[dict], events: list[dict],
                                         errors: list[str]) -> None:
    """Validate the passed-unit chain and bind every final snapshot to it."""
    attempts = final.get("attempts", []) \
        if isinstance(final, dict) and isinstance(final.get("attempts"), list) else []
    passed_units = [unit for unit in units if isinstance(unit, dict) and unit.get("status") == "passed"]
    pass_events = [event for event in events
                   if isinstance(event, dict) and event.get("entity") != "run"
                   and event.get("to") == "passed"]
    event_ids = [event.get("entity") for event in pass_events]
    unit_ids = [unit.get("unit_id") for unit in passed_units]
    if (not pass_events or any(not isinstance(item, str) for item in event_ids)
            or len(event_ids) != len(set(event_ids))
            or len(pass_events) != len(passed_units) or set(event_ids) != set(unit_ids)
            or any(not isinstance(event.get("sequence"), int) for event in pass_events)):
        errors.append("final_review passed-unit event order or mapping is invalid")
        return

    by_id = {unit.get("unit_id"): unit for unit in passed_units}
    snapshots: list[dict] = []
    for unit_id in event_ids:
        unit = by_id.get(unit_id)
        history = unit.get("review_history") if isinstance(unit, dict) else None
        review = history[-1] if isinstance(history, list) and history else None
        snapshot = review.get("diff_snapshot") if isinstance(review, dict) else None
        if not isinstance(snapshot, dict):
            errors.append("final_review passed unit is missing its latest passing snapshot")
            return
        snapshots.append(snapshot)
    for previous, current in zip(snapshots, snapshots[1:]):
        if (previous.get("target_commit"), previous.get("target_tree")) != (
                current.get("base_commit"), current.get("base_tree")):
            errors.append("final_review passed-unit snapshots are not an adjacent chain")
            return

    first, last = snapshots[0], snapshots[-1]
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        snapshot = attempt.get("diff_snapshot")
        if not isinstance(snapshot, dict) or (
                snapshot.get("base_commit"), snapshot.get("base_tree")) != (
                first.get("base_commit"), first.get("base_tree")) or (
                snapshot.get("target_commit"), snapshot.get("target_tree")) != (
                last.get("target_commit"), last.get("target_tree")):
            errors.append("final_review passing snapshot does not span the passed-unit chain")


def _bounded_scope_text(value: str) -> str:
    if len(value) <= SCOPE_DRIFT_TEXT_LIMIT:
        return value
    return value[:SCOPE_DRIFT_TEXT_LIMIT - 3] + "..."


def _scope_drift_digest(paths: list[str], command_digests: list[str]) -> str:
    payload = json.dumps({"allowed_paths": paths, "acceptance_commands": command_digests},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_add_unit_scope_drift(run_dir: Path, run_path: Path, args: argparse.Namespace,
                               paths: list[str], commands: list[str]) -> None:
    """Gate safe but out-of-contract unit inputs without creating a unit."""
    events_path = run_dir / "events.jsonl"
    original_run, original_events = run_path.read_bytes(), events_path.read_bytes()
    command_digests = ["sha256:" + hashlib.sha256(command.encode("utf-8")).hexdigest()
                       for command in commands]
    path_limit = SCOPE_DRIFT_EVIDENCE_LIMIT - 1 if command_digests else SCOPE_DRIFT_EVIDENCE_LIMIT
    evidence = [f"safe path outside locked contract: {_bounded_scope_text(path)}"
                for path in paths[:path_limit]]
    evidence.extend(
        f"acceptance command outside locked contract; digest={digest}"
        for digest in command_digests[:SCOPE_DRIFT_EVIDENCE_LIMIT]
    )
    # The caller has already established that at least one safe drift exists.
    evidence = evidence[:SCOPE_DRIFT_EVIDENCE_LIMIT]
    input_digest = (command_digests[0] if len(command_digests) == 1 and not paths
                    else _scope_drift_digest(paths, command_digests))
    failure = {
        "code": "HW_SCOPE_DRIFT", "reason": SCOPE_DRIFT_REASON,
        "evidence": evidence, "recovery": SCOPE_DRIFT_RECOVERY,
    }
    run = read_json(run_path)
    event_lines = [line for line in original_events.decode("utf-8").splitlines() if line.strip()]
    event = transition_event(len(event_lines) + 1, "run", "contract_locked", "awaiting_user",
                             argparse.Namespace(
                                 actor=SCOPE_DRIFT_ACTOR, role="orchestrator",
                                 reason=SCOPE_DRIFT_REASON, input_digest=input_digest,
                                 evidence_ref=evidence, review_round=0,
                             ))
    run["status"] = "awaiting_user"
    run["failure"] = failure
    try:
        write_json(run_path, run)
        separator = b"\n" if original_events and not original_events.endswith(b"\n") else b""
        _atomic_replace_bytes(events_path, original_events + separator +
                              (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
        validate_run(argparse.Namespace(workspace=str(run_dir.parents[2]), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(((run_path, original_run), (events_path, original_events)))
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_SCOPE_DRIFT", "could not record scope drift; user decision is still required") from exc
    raise HwahapError("HW_SCOPE_DRIFT", SCOPE_DRIFT_REASON)


def add_unit(args: argparse.Namespace) -> None:
    unit_id = require_safe_unit_id(args.unit_id)
    title = getattr(args, "title", None)
    if not required_text(title) or contains_sensitive_data(title):
        raise HwahapError("HW_STATE_INVALID", "unit title is invalid")
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    require_run_unit_mutation_allowed(run_path)
    contract, run = read_json(contract_path), read_json(run_path)
    if not contract.get("locked") or run.get("status") != "contract_locked":
        raise HwahapError("HW_STATE_INVALID", "unit creation requires a locked contract and safe unit ID")
    if (not isinstance(args.allowed_path, list) or not args.allowed_path
            or any(not safe_relative_path(path) or contains_sensitive_data(path)
                   for path in args.allowed_path)):
        raise HwahapError("HW_STATE_INVALID", "unsafe unit allowed path")
    if (not isinstance(args.acceptance_command, list) or not args.acceptance_command
            or any(not safe_test_command(command) for command in args.acceptance_command)):
        raise HwahapError("HW_STATE_INVALID", "acceptance command contains sensitive data")
    drift_paths = [path for path in args.allowed_path if path not in contract["allowed_paths"]]
    drift_commands = [command for command in args.acceptance_command if command not in contract["test_commands"]]
    if drift_paths or drift_commands:
        record_add_unit_scope_drift(run_dir, run_path, args, drift_paths, drift_commands)
    unit_path = run_dir / "units" / f"{unit_id}.json"
    if unit_path.exists() or unit_path.is_symlink():
        raise HwahapError("HW_STATE_INVALID", f"unit already exists: {args.unit_id}")
    unit = {
        "unit_id": unit_id, "title": title, "status": "planned",
        "writer": "hwahap-luna-implementer", "allowed_paths": args.allowed_path,
        "acceptance_commands": args.acceptance_command, "replan_count": 0,
        "review_history": [], "improvement_history": [], "recovery": None, "failure": None,
        "test_receipts": [],
    }
    try:
        original_run = run_path.read_bytes()
    except Exception as exc:
        raise HwahapError("HW_STATE_INVALID", "could not snapshot unit state") from exc
    try:
        write_json(unit_path, unit)
        run["metrics"]["unit_count"] = len(list((run_dir / "units").glob("*.json")))
        write_json(run_path, run)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(((run_path, original_run),))
        remove_path_best_effort(unit_path)
        raise HwahapError("HW_STATE_INVALID", "could not create unit") from exc
    print(f"HW_OK: run={args.run_id} unit={args.unit_id} planned")


def run_test(args: argparse.Namespace) -> None:
    raise HwahapError("HW_TEST_EXECUTION_DISABLED", "test execution is disabled; use an authorized Luna verifier and record-test-receipt")


def record_test_receipt(args: argparse.Namespace) -> None:
    unit_id = require_safe_unit_id(args.unit_id)
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    require_run_unit_mutation_allowed(run_path)
    contract, run = read_json(contract_path), read_json(run_path)
    if not contract.get("locked") or run.get("status") != "reviewing":
        raise HwahapError("HW_STATE_INVALID", "record-test-receipt requires a locked reviewing run")
    unit_path = run_dir / "units" / f"{unit_id}.json"
    if unit_path.is_symlink() or not unit_path.is_file():
        raise HwahapError("HW_STATE_INVALID", "unit must be a regular file")
    unit = read_json(unit_path)
    if unit.get("status") != "reviewing":
        raise HwahapError("HW_STATE_INVALID", "record-test-receipt requires a reviewing unit")
    index = args.command_index
    commands = unit.get("acceptance_commands")
    if (not isinstance(index, int) or isinstance(index, bool) or not isinstance(commands, list)
            or not 1 <= index <= len(commands) or not isinstance(commands[index - 1], str)):
        raise HwahapError("HW_STATE_INVALID", "command_index is outside acceptance_commands")
    if (not isinstance(args.execution_receipt_sha256, str) or not SHA256.fullmatch(args.execution_receipt_sha256)
            or not required_text(args.observer_thread_id) or not isinstance(args.diff_digest, str)
            or not SHA256.fullmatch(args.diff_digest) or not required_text(args.started_at)
            or not required_text(args.ended_at) or not isinstance(args.output_sha256, str)
            or not SHA256.fullmatch(args.output_sha256)):
        raise HwahapError("HW_STATE_INVALID", "external test receipt fields are invalid")
    snapshot = git_diff_snapshot(workspace, getattr(args, "base_commit", None), getattr(args, "target_commit", None))
    if args.diff_digest != snapshot["diff_digest"]:
        raise HwahapError("HW_STATE_INVALID", "test receipt diff digest does not match Git snapshot")
    timed_out = bool(getattr(args, "timed_out", False))
    exit_code = getattr(args, "exit_code", None)
    if timed_out == (exit_code is not None) or (exit_code is not None and (
            not isinstance(exit_code, int) or isinstance(exit_code, bool))):
        raise HwahapError("HW_STATE_INVALID", "provide exactly one of exit-code or timed-out")
    status = "timeout" if timed_out else "pass" if exit_code == 0 else "fail"
    receipts = unit.get("test_receipts")
    if not isinstance(receipts, list) or any(
            isinstance(receipt, dict) and receipt.get("execution_receipt_sha256") == args.execution_receipt_sha256
            for receipt in receipts):
        raise HwahapError("HW_STATE_INVALID", "duplicate execution receipt")
    for other_path in sorted((run_dir / "units").glob("*.json")):
        if other_path == unit_path:
            continue
        other = read_json(other_path)
        other_receipts = other.get("test_receipts")
        if isinstance(other_receipts, list) and any(
                isinstance(receipt, dict) and receipt.get("execution_receipt_sha256") == args.execution_receipt_sha256
                for receipt in other_receipts):
            raise HwahapError("HW_STATE_INVALID", "duplicate execution receipt")
    occurrence = sum(isinstance(receipt, dict) and receipt.get("command_index") == index for receipt in receipts) + 1
    receipt = {
        "test_id": f"test-{index}-{occurrence}", "command_index": index,
        "command_sha256": "sha256:" + hashlib.sha256(commands[index - 1].encode("utf-8")).hexdigest(),
        "source": "codex.exec_command", "execution_receipt_sha256": args.execution_receipt_sha256,
        "observer_role": "verifier", "observer_thread_id": args.observer_thread_id,
        "diff_snapshot": snapshot, "diff_digest": snapshot["diff_digest"],
        "started_at": args.started_at, "ended_at": args.ended_at,
        "exit_code": None if timed_out else exit_code, "output_sha256": args.output_sha256, "status": status,
    }
    try:
        original = ((unit_path, unit_path.read_bytes()), (run_path, run_path.read_bytes()))
    except Exception as exc:
        raise HwahapError("HW_STATE_INVALID", "could not snapshot receipt state") from exc
    receipts.append(receipt)
    run["metrics"]["test_runs"] = sum(
        len(item.get("test_receipts", [])) for item in
        [read_json(path) for path in sorted((run_dir / "units").glob("*.json"))]
        if isinstance(item.get("test_receipts"), list)
    ) + 1
    try:
        write_json(unit_path, unit)
        write_json(run_path, run)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(original)
        raise HwahapError("HW_STATE_INVALID", "could not record test receipt") from exc
    print(f"HW_OK: run={args.run_id} unit={args.unit_id} test={receipt['test_id']} status={status}")


def transition(args: argparse.Namespace) -> None:
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    if args.entity == "run" and args.to == "completed":
        raise HwahapError("HW_STATE_INVALID", "use complete command to finish a run")
    events_path = run_dir / "events.jsonl"
    if args.entity == "run":
        state_path = run_path
        graph = RUN_TRANSITIONS
    else:
        require_run_unit_mutation_allowed(run_path)
        entity = require_safe_unit_id(args.entity)
        state_path = run_dir / "units" / f"{entity}.json"
        graph = UNIT_TRANSITIONS
    state = read_json(state_path)
    source = state.get("status")
    if not isinstance(source, str) or args.to not in graph.get(source, set()):
        raise HwahapError("HW_STATE_INVALID", f"illegal transition: {source} -> {args.to}")
    if args.entity != "run" and args.to == "implementing":
        require_single_implementing_unit(run_dir, args.entity)
    if args.entity == "run" and args.to == "final_review":
        contract = read_json(contract_path)
        units = [unit for _, _, unit in read_unit_files(run_dir / "units")]
        final_errors: list[str] = []
        validate_final_review_units(units, contract, final_errors, workspace)
        if final_errors:
            raise HwahapError("HW_STATE_INVALID", "; ".join(final_errors))
    if args.entity == "run" and source == "final_review" and args.to == "awaiting_user":
        final = state.get("final_review")
        final_errors: list[str] = []
        validate_final_review(final, False, final_errors, workspace)
        expected_code = final_review_failure_code(final)
        if (not isinstance(final, dict) or final.get("status") != "fail" or final_errors
                or expected_code is None or args.failure_code != expected_code):
            raise HwahapError("HW_STATE_INVALID", "final_review awaiting_user requires matching failure evidence")
    if args.to in RUN_FAILURE_STATES | FAILURE_STATES:
        if not all((args.failure_code, args.failure_reason, args.failure_recovery, args.failure_evidence)):
            raise HwahapError("HW_STATE_INVALID", "failure transition requires code, reason, evidence, and recovery")
        state["failure"] = {
            "code": args.failure_code, "reason": args.failure_reason,
            "evidence": args.failure_evidence, "recovery": args.failure_recovery,
        }
    if args.entity == "run" and args.to == "completed":
        state["completed_at"] = utc_now()
    event_lines = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    event = transition_event(len(event_lines) + 1, args.entity, source, args.to, args)
    original = ((state_path, state_path.read_bytes()), (events_path, events_path.read_bytes()))
    state["status"] = args.to
    try:
        write_json(state_path, state)
        _atomic_replace_bytes(events_path, original[1][1] +
                              (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(original)
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_STATE_INVALID", "could not update state") from exc
    print(f"HW_OK: run={args.run_id} entity={args.entity} state={args.to}")


def record_improvement(args: argparse.Namespace) -> None:
    unit_id = require_safe_unit_id(args.unit_id)
    workspace, run_dir, _, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    unit_path = run_dir / "units" / f"{unit_id}.json"
    events_path = run_dir / "events.jsonl"
    for label, path in (("unit", unit_path), ("events.jsonl", events_path)):
        if path.is_symlink() or not path.is_file():
            raise HwahapError("HW_STATE_INVALID", f"{label} must be a regular file")
    require_run_unit_mutation_allowed(run_path)
    unit = read_json(unit_path)
    run = read_json(run_path)
    history = unit.get("improvement_history")
    if not isinstance(history, list):
        raise HwahapError("HW_STATE_INVALID", "improvement_history must be a list")
    if unit.get("status") != "reviewing" or not required_text(args.actor):
        raise HwahapError("HW_STATE_INVALID", "record-improvement requires a reviewing unit and actor")
    target = "recovery" if args.kind == "terra_recovery" else "replan_required"
    if args.kind not in {"terra_recovery", "sol_replan", "recursive_improvement"}:
        raise HwahapError("HW_STATE_INVALID", "invalid improvement kind")
    record = {
        "after_round": args.after_round, "kind": args.kind,
        "failure_signature": args.failure_signature, "root_cause": args.root_cause,
        "hypothesis": args.hypothesis, "action": args.action,
        "strategy_digest": args.strategy_digest, "scope_status": args.scope_status,
        "evidence": args.evidence_ref,
    }
    try:
        original_unit, original_run, original_events = (
            unit_path.read_bytes(), run_path.read_bytes(), events_path.read_bytes())
        event_lines = [line for line in original_events.decode("utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError) as exc:
        raise HwahapError("HW_STATE_INVALID", "cannot read state files") from exc
    history.append(record)
    unit["replan_count"] = sum(
        item.get("kind") in {"sol_replan", "recursive_improvement"}
        for item in history if isinstance(item, dict)
    )
    unit["status"] = target
    if target == "replan_required":
        unit["failure"] = {
            "code": "HW_REPLAN_REQUIRED", "reason": args.root_cause,
            "evidence": args.evidence_ref, "recovery": args.action,
        }
    run_target = "recovering" if target == "recovery" else "replanning"
    event = {
        "timestamp": utc_now(), "type": "state_transition", "sequence": len(event_lines) + 1,
        "entity": unit_id, "from": "reviewing", "to": target,
        "actor": args.actor, "role": "orchestrator", "reason": args.action,
        "input_digest": args.strategy_digest, "evidence_refs": args.evidence_ref,
        "review_round": args.after_round,
    }
    run_event = dict(event, entity="run", from_=run.get("status", ""), to=run_target)
    run_event["from"] = run_event.pop("from_")
    run_event["sequence"] = len(event_lines) + 1
    event["sequence"] += 1
    try:
        write_json(unit_path, unit)
        run["status"] = run_target
        write_json(run_path, run)
        _atomic_replace_bytes(events_path, original_events +
                              (json.dumps(run_event, ensure_ascii=False) + "\n").encode("utf-8") +
                              (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(((unit_path, original_unit), (run_path, original_run), (events_path, original_events)))
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_STATE_INVALID", "could not update improvement state") from exc
    print(f"HW_OK: run={args.run_id} unit={unit_id} improvement={args.after_round}")


def validate_improvement_candidate(record: object, label: str, errors: list[str]) -> None:
    if not isinstance(record, dict):
        errors.append(f"{label} must be an object")
        return
    if set(record) != CANDIDATE_FIELDS:
        errors.append(f"{label} has invalid fields")
    if record.get("status") != "proposed":
        errors.append(f"{label}.status must be proposed")
    if any(not required_text(record.get(field)) for field in ("summary", "expected_effect", "next_action")):
        errors.append(f"{label} requires summary, expected_effect, and next_action")
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence):
        errors.append(f"{label}.evidence must be nonempty")


def validate_improvement_candidates(value: object, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("improvement_candidates must be a list")
        return
    for index, record in enumerate(value, 1):
        validate_improvement_candidate(record, f"improvement_candidates[{index}]", errors)


def record_improvement_candidate(args: argparse.Namespace) -> None:
    workspace, _, _, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    run = read_json(run_path)
    if run.get("status") != "final_review":
        raise HwahapError("HW_STATE_INVALID", "record-improvement-candidate requires a final_review run")
    final = run.get("final_review")
    final_errors: list[str] = []
    validate_final_review(final, False, final_errors, workspace)
    if not isinstance(final, dict) or final.get("status") != "pass" or final_errors:
        raise HwahapError("HW_STATE_INVALID", "record-improvement-candidate requires a valid passing final_review")
    record = {
        "status": "proposed", "summary": args.summary, "evidence": args.evidence_ref,
        "expected_effect": args.expected_effect, "next_action": args.next_action,
    }
    candidate_errors: list[str] = []
    validate_improvement_candidate(record, "improvement_candidate", candidate_errors)
    sensitive_errors: list[str] = []
    validate_state_strings(record, "improvement_candidate", sensitive_errors)
    if sensitive_errors:
        raise HwahapError("HW_STATE_INVALID", "state value contains sensitive data")
    if candidate_errors:
        raise HwahapError("HW_STATE_INVALID", "; ".join(candidate_errors))
    candidates = run.get("improvement_candidates")
    if not isinstance(candidates, list):
        raise HwahapError("HW_STATE_INVALID", "improvement_candidates must be a list")
    original = run_path.read_bytes()
    try:
        candidates.append(record)
        write_json(run_path, run)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(((run_path, original),))
        raise HwahapError("HW_STATE_INVALID", "could not record improvement candidate") from exc
    print(f"HW_OK: run={args.run_id} improvement_candidate=proposed")


def goal_sync(args: argparse.Namespace) -> None:
    workspace, _, _, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    run = read_json(run_path)
    goal_link = run.get("goal_link")
    if not isinstance(goal_link, dict) or not isinstance(goal_link.get("history"), list):
        raise HwahapError("HW_STATE_INVALID", "goal_link must contain current and history")
    mode = args.mode
    token_total = getattr(args, "token_total", None)
    if token_total is not None and (mode != "bound" or not isinstance(token_total, int) or isinstance(token_total, bool) or token_total < 0):
        raise HwahapError("HW_STATE_INVALID", "token-total is only a nonnegative integer for bound Goal receipts")
    if mode not in GOAL_MODES - {"unobserved"}:
        raise HwahapError("HW_STATE_INVALID", "goal-sync mode is invalid")
    if not required_text(args.reason) or not isinstance(args.evidence_ref, list) or not args.evidence_ref:
        raise HwahapError("HW_STATE_INVALID", "goal-sync reason and evidence are required")
    if any(not required_text(ref) for ref in args.evidence_ref):
        raise HwahapError("HW_STATE_INVALID", "goal-sync evidence must be nonempty text")
    if mode == "bound":
        if (not required_text(args.thread_id) or not isinstance(args.objective_sha256, str)
                or not SHA256.fullmatch(args.objective_sha256)
                or not isinstance(args.receipt_sha256, str) or not SHA256.fullmatch(args.receipt_sha256)):
            raise HwahapError("HW_STATE_INVALID", "bound Goal receipt is incomplete")
        bound_pairs = {
            (entry.get("thread_id"), entry.get("objective_sha256"))
            for entry in goal_link["history"] if isinstance(entry, dict) and entry.get("mode") == "bound"
        }
        if bound_pairs and (args.thread_id, args.objective_sha256) not in bound_pairs:
            raise HwahapError("HW_STATE_INVALID", "Goal binding cannot change thread or objective")
        external_status = "active"
        source = "codex.get_goal"
        completion_sync = "pending"
    else:
        if args.thread_id is not None or args.objective_sha256 is not None:
            raise HwahapError("HW_STATE_INVALID", "unbound Goal receipt must clear thread and objective")
        if mode == "unavailable" and args.receipt_sha256 is not None:
            raise HwahapError("HW_STATE_INVALID", "unavailable Goal receipt must not include a receipt hash")
        if mode == "no_active_goal" and (
                not isinstance(args.receipt_sha256, str) or not SHA256.fullmatch(args.receipt_sha256)):
            raise HwahapError("HW_STATE_INVALID", "no-active Goal receipt hash is invalid")
        if any(isinstance(entry, dict) and entry.get("mode") == "bound" for entry in goal_link["history"]):
            raise HwahapError("HW_STATE_INVALID", "bound Goal link cannot downgrade to an unbound receipt")
        external_status = "unknown"
        source = "codex.get_goal"
        completion_sync = "not_applicable"
    record = {
        "mode": mode, "source": source, "thread_id": args.thread_id if mode == "bound" else None,
        "external_status": external_status,
        "objective_sha256": args.objective_sha256 if mode == "bound" else None,
        "receipt_sha256": args.receipt_sha256 if mode != "unavailable" else None,
        "reason": args.reason, "evidence": args.evidence_ref,
        "observed_at": utc_now(), "completion_sync": completion_sync, "sync_result": None,
        "token_total": token_total if mode == "bound" else None,
    }
    run["metrics"]["token_usage"] = (
        {"availability": "available", "source": "codex.get_goal", "total": token_total, "reason": None}
        if mode == "bound" and token_total is not None else
        {"availability": "unavailable", "source": None, "total": None, "reason": "platform aggregate not exposed"}
    )
    try:
        original = ((run_path, run_path.read_bytes()),)
    except Exception as exc:
        raise HwahapError("HW_STATE_INVALID", "could not snapshot Goal state") from exc
    goal_link["current"] = record
    goal_link["history"].append(record.copy())
    try:
        write_json(run_path, run)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(original)
        raise HwahapError("HW_STATE_INVALID", "could not synchronize Goal state") from exc
    print(f"HW_OK: run={args.run_id} goal_mode={mode}")


def goal_complete_sync(args: argparse.Namespace) -> None:
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    data_path = run_dir / "report-data.json"
    report_path = run_dir / "report.html"
    if not _single_regular_file(data_path) or not _single_regular_file(report_path):
        raise HwahapError("HW_STATE_INVALID", "goal completion sync requires completed report artifacts")
    contract, run = read_json(contract_path), read_json(run_path)
    goal_link = run.get("goal_link")
    current = goal_link.get("current") if isinstance(goal_link, dict) else None
    if (run.get("status") != "completed" or not isinstance(current, dict) or current.get("mode") != "bound"
            or current.get("source") == "codex.update_goal" and current.get("completion_sync") == "completed"):
        raise HwahapError("HW_STATE_INVALID", "goal completion sync requires a bound completed run")
    if (not isinstance(args.receipt_sha256, str) or not SHA256.fullmatch(args.receipt_sha256)
            or args.sync_result not in {"completed", "already_completed", "failed"}
            or not required_text(args.reason) or not args.evidence_ref or any(not required_text(ref) for ref in args.evidence_ref)):
        raise HwahapError("HW_STATE_INVALID", "goal completion sync receipt is incomplete")
    token_total = getattr(args, "token_total", None)
    if args.sync_result in {"completed", "already_completed"}:
        if not isinstance(token_total, int) or isinstance(token_total, bool) or token_total < 0:
            raise HwahapError("HW_STATE_INVALID", "successful Goal completion sync requires token-total")
    elif token_total is not None:
        raise HwahapError("HW_STATE_INVALID", "failed Goal completion sync must not include token-total")
    original_run, original_data, original_report = run_path.read_bytes(), data_path.read_bytes(), report_path.read_bytes()
    originals = {
        "run.json": (True, original_run), "report-data.json": (True, original_data),
        "report.html": (True, original_report), "events.jsonl": (True, (run_dir / "events.jsonl").read_bytes()),
    }
    marker_run_bytes = None
    try:
        units = [read_json(path) for path in sorted((run_dir / "units").glob("*.json"))]
        events = parse_events(run_dir / "events.jsonl")
        record = {
            "mode": "bound", "source": "codex.update_goal", "thread_id": current.get("thread_id"),
            "external_status": "completed" if args.sync_result in {"completed", "already_completed"} else "active",
            "objective_sha256": current.get("objective_sha256"), "receipt_sha256": args.receipt_sha256,
            "reason": args.reason, "evidence": args.evidence_ref, "observed_at": utc_now(),
            "completion_sync": "completed" if args.sync_result in {"completed", "already_completed"} else "failed",
            "sync_result": args.sync_result, "token_total": token_total if args.sync_result in {"completed", "already_completed"} else None,
        }
        working_run = json.loads(json.dumps(run))
        working_run["goal_link"]["current"] = record
        working_run["goal_link"]["history"].append(record.copy())
        if args.sync_result in {"completed", "already_completed"}:
            working_run["metrics"]["token_usage"] = {
                "availability": "available", "source": "codex.update_goal", "total": token_total, "reason": None,
            }
        artifacts = prepare_report_artifacts(workspace, contract, working_run, units, events,
                                              report_state_digests(contract_path, run_dir / "events.jsonl", run_dir / "units"))
        source_digest = artifacts["source_payload_sha256"]
        report_bytes = artifacts["html_bytes"]
        working_run["report"] = {**run["report"], "schema_version": REPORT_SCHEMA_VERSION, "status": "completed",
                                  "generator": REPORT_GENERATOR.copy(), "source_payload_sha256": source_digest,
                                  "data": {"path": "report-data.json", "file_sha256": artifacts["data_file_sha256"]},
                                  "html": {"path": "report.html", "file_sha256": artifacts["html_file_sha256"]},
                                  "redaction_policy": REPORT_REDACTION_POLICY, "generated_at": record["observed_at"]}
        target = {"run.json": _json_bytes(working_run), "report-data.json": artifacts["data_bytes"],
                  "report.html": report_bytes, "events.jsonl": (run_dir / "events.jsonl").read_bytes()}
        journal_bytes, marker_run_bytes = _recovery_setup("goal_complete_sync", originals, target)
        _write_report_recovery_journal(run_dir, journal_bytes)
        _atomic_replace_bytes(run_path, marker_run_bytes)
        _atomic_replace_bytes(data_path, artifacts["data_bytes"])
        _atomic_replace_bytes(report_path, report_bytes)
        _atomic_replace_bytes(run_path, target["run.json"])
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True, _skip_recovery=True))
        if not _clear_report_recovery_journal(run_dir):
            raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not finalize Goal completion report")
    except Exception:
        _restore_report_recovery(run_dir, originals, marker_run_bytes)
        raise HwahapError("HW_REPORT_GENERATION_FAILED", "Goal completion report generation failed") from None
    print(f"HW_OK: run={args.run_id} goal_completion_sync={args.sync_result}")


def required_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def contains_sensitive_data(value: object) -> bool:
    """Return whether state text contains sensitive data, without exposing it."""
    _ensure_dependencies()
    if not isinstance(value, str):
        return False
    return _shared_contains_sensitive_data(value)


def contains_sensitive_pair(key: object, value: object) -> bool:
    """Return whether a dictionary key/value pair forms sensitive data."""
    if not isinstance(key, str):
        return False
    # A structured object can split the assignment across its key and value,
    # so run the same origin-aware detector against both common separators. A
    # container has no text to inspect, but a sensitive key must still not be
    # allowed to bypass the detector; use a safe placeholder in that case.
    pair_value = value if isinstance(value, str) else "value"
    return contains_sensitive_data(f"{key}={pair_value}") or contains_sensitive_data(f"{key}:{pair_value}")


def validate_state_strings(value: object, label: str, errors: list[str], *, skip_command_fields: bool = False) -> None:
    """Check every nested JSON string while keeping invalid values out of errors."""
    if isinstance(value, str):
        # Command fields retain their established, command-specific error. They
        # are still checked by safe_test_command below.
        is_contract_command = label.startswith("contract.test_commands[")
        is_unit_command = label.startswith("unit ") and label.count(".") == 1 and ".acceptance_commands[" in label
        if skip_command_fields and (is_contract_command or is_unit_command):
            return
        if contains_sensitive_data(value):
            errors.append("state contains sensitive data")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_state_strings(item, f"{label}[{index}]", errors, skip_command_fields=skip_command_fields)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and contains_sensitive_data(key):
                errors.append("state contains sensitive data")
            if contains_sensitive_pair(key, item):
                errors.append("state contains sensitive data")
            validate_state_strings(item, f"{label}.{key}", errors, skip_command_fields=skip_command_fields)


def safe_test_command(value: object) -> bool:
    if (not required_text(value) or SHELL_CONTROL.search(value)
            or "$" in value or "\\" in value):
        return False
    if COMMAND_SENSITIVE_PATTERN.search(value) or contains_sensitive_data(value):
        return False
    try:
        argv = shlex.split(value, posix=True)
    except ValueError:
        return False
    if not argv or any(ASSIGNMENT_TOKEN.match(token) for token in argv):
        return False
    if any(Path(token).name in SHELL_WRAPPERS or Path(token).name == "env"
           or token == "-lc" for token in argv):
        return False
    if "/" in argv[0] or any("://" in token or token.startswith("/")
                              or ".." in Path(token.replace("=", "/")).parts
                              for token in argv[1:]):
        return False
    tool = argv[0]
    if tool in DIRECT_TEST_TOOLS:
        return True
    if tool in {"python", "python3"}:
        return len(argv) >= 3 and argv[1] == "-m" and argv[2] in {"pytest", "unittest"}
    if tool == "make":
        targets = [token for token in argv[1:] if not token.startswith("-")]
        return bool(targets) and all(MAKE_TEST_TARGET.fullmatch(target) for target in targets)
    if tool in TEST_SUBCOMMANDS:
        return len(argv) >= 2 and argv[1] in TEST_SUBCOMMANDS[tool]
    return False


def validate_goal_observation(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return
    mode = value.get("mode")
    if mode not in GOAL_MODES:
        errors.append(f"{label}.mode is invalid")
        return
    sync_result = value.get("sync_result")
    if "sync_result" not in value:
        errors.append(f"{label}.sync_result is required")
    if "token_total" not in value:
        errors.append(f"{label}.token_total is required")
    if mode != "bound" and sync_result is not None:
        errors.append(f"{label}.sync_result must be null for non-bound receipts")
    if not required_text(value.get("observed_at")) or not required_text(value.get("reason")):
        errors.append(f"{label} requires observed_at and reason")
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(not required_text(ref) for ref in evidence):
        errors.append(f"{label}.evidence must be nonempty")
    if mode == "bound":
        if value.get("source") not in {"codex.get_goal", "codex.update_goal"} or not required_text(value.get("thread_id")):
            errors.append(f"{label} bound source or thread_id is invalid")
        source = value.get("source")
        if source == "codex.get_goal":
            if value.get("external_status") != "active" or value.get("completion_sync") != "pending":
                errors.append(f"{label} active Goal receipt is invalid")
            if sync_result is not None:
                errors.append(f"{label}.sync_result must be null for get_goal receipts")
            if value.get("token_total") is not None and (not isinstance(value.get("token_total"), int) or isinstance(value.get("token_total"), bool) or value.get("token_total") < 0):
                errors.append(f"{label}.token_total is invalid")
        elif source == "codex.update_goal":
            if sync_result not in {"completed", "already_completed", "failed"}:
                errors.append(f"{label}.sync_result is invalid")
            expected = (("completed", "completed") if sync_result in {"completed", "already_completed"}
                        else ("active", "failed") if sync_result == "failed" else (None, None))
            if (value.get("external_status"), value.get("completion_sync")) != expected:
                errors.append(f"{label} completion Goal receipt is invalid")
            if sync_result in {"completed", "already_completed"} and (not isinstance(value.get("token_total"), int) or isinstance(value.get("token_total"), bool) or value.get("token_total") < 0):
                errors.append(f"{label}.token_total is required for successful completion")
            if sync_result == "failed" and value.get("token_total") is not None:
                errors.append(f"{label}.token_total must be null for failed completion")
        else:
            errors.append(f"{label} bound source is invalid")
        for field in ("objective_sha256", "receipt_sha256"):
            if not isinstance(value.get(field), str) or not SHA256.fullmatch(value[field]):
                errors.append(f"{label}.{field} is invalid")
    elif mode == "unobserved":
        if any(value.get(field) is not None for field in ("source", "thread_id", "objective_sha256", "receipt_sha256")):
            errors.append(f"{label} unobserved receipt fields must be null")
        if value.get("external_status") != "unknown" or value.get("completion_sync") != "pending" or value.get("token_total") is not None:
            errors.append(f"{label} unobserved status or completion_sync is invalid")
    else:
        if value.get("source") != "codex.get_goal" or value.get("thread_id") is not None:
            errors.append(f"{label} unbound source or thread_id is invalid")
        if value.get("external_status") != "unknown" or value.get("objective_sha256") is not None:
            errors.append(f"{label} unbound status or objective is invalid")
        receipt = value.get("receipt_sha256")
        if mode == "unavailable":
            if receipt is not None:
                errors.append(f"{label} unavailable receipt must be null")
        elif not isinstance(receipt, str) or not SHA256.fullmatch(receipt):
            errors.append(f"{label}.receipt_sha256 is invalid")
        if value.get("completion_sync") != "not_applicable" or value.get("token_total") is not None:
            errors.append(f"{label} unbound completion_sync must be not_applicable")


def validate_goal_link(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("goal_link must be an object")
        return
    current = value.get("current")
    history = value.get("history")
    validate_goal_observation(current, "goal_link.current", errors)
    if not isinstance(history, list):
        errors.append("goal_link.history must be a list")
        return
    bound_pair = None
    saw_get_goal = False
    saw_bound = False
    for index, entry in enumerate(history, 1):
        validate_goal_observation(entry, f"goal_link.history[{index}]", errors)
        if not isinstance(entry, dict):
            continue
        if entry.get("mode") != "bound":
            if saw_bound:
                errors.append("goal_link cannot downgrade after a bound receipt")
            continue
        saw_bound = True
        pair = (entry.get("thread_id"), entry.get("objective_sha256"))
        if bound_pair is None and entry.get("source") == "codex.get_goal":
            bound_pair = pair
            saw_get_goal = True
        elif bound_pair is None and entry.get("source") == "codex.update_goal":
            errors.append("goal_link update_goal receipt requires a prior get_goal binding")
        elif pair != bound_pair:
            errors.append("goal_link bound thread/objective must remain unchanged")
        if entry.get("source") == "codex.get_goal":
            saw_get_goal = True
        elif entry.get("source") == "codex.update_goal" and not saw_get_goal:
            errors.append("goal_link update_goal receipt requires a prior get_goal binding")
    if not history and isinstance(current, dict) and current.get("mode") != "unobserved":
        errors.append("goal_link.current must be unobserved when history is empty")
    if history and current != history[-1]:
        errors.append("goal_link.current must equal the last history entry")


def safe_relative_path(value: object) -> bool:
    if not required_text(value):
        return False
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return False
    text = value.strip()
    if "\\" in text or Path(text).is_absolute() or text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", text):
        return False
    return all(part not in ("", ".", "..") for part in re.split(r"[/\\]", text))


def paths_overlap(left: str, right: str) -> bool:
    left_prefix = left.rstrip("/") + "/"
    right_prefix = right.rstrip("/") + "/"
    return (left == right or left.startswith(right_prefix) or right.startswith(left_prefix)
            or fnmatch.fnmatch(left, right) or fnmatch.fnmatch(right, left))


def validate_failure(value: object, label: str, errors: list[str]) -> None:
    failure = value if isinstance(value, dict) else {}
    code = failure.get("code")
    if not isinstance(code, str) or code not in FAILURE_CODES or not required_text(failure.get("reason")):
        errors.append(f"{label}: invalid failure code or reason")
    evidence = failure.get("evidence")
    if (not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence)
            or not required_text(failure.get("recovery"))):
        errors.append(f"{label}: failure evidence and recovery are required")


def path_matches(path: str, allowed: object) -> bool:
    if not isinstance(allowed, list):
        return False
    for rule in allowed:
        if not isinstance(rule, str):
            continue
        prefix = rule.rstrip("/") + "/"
        if path == rule or path.startswith(prefix) or fnmatch.fnmatch(path, rule):
            return True
    return False


def validate_improvement(record: object, after_round: int, kind: str, label: str, errors: list[str]) -> bool:
    if not isinstance(record, dict):
        errors.append(f"{label}: improvement record must be an object")
        return False
    if record.get("after_round") != after_round or record.get("kind") != kind:
        errors.append(f"{label}: improvement record round or kind is invalid")
    for field in ("failure_signature", "strategy_digest"):
        if not isinstance(record.get(field), str) or not SHA256.fullmatch(record[field]):
            errors.append(f"{label}: improvement {field} is invalid")
    if any(not required_text(record.get(field)) for field in ("root_cause", "hypothesis", "action")):
        errors.append(f"{label}: improvement explanation is incomplete")
    if record.get("scope_status") != "within_contract":
        errors.append(f"{label}: improvement scope is invalid")
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence):
        errors.append(f"{label}: improvement evidence is required")
    return True


def validate_review_history(unit: dict, contract: dict, errors: list[str], workspace: Path | None = None) -> list[str]:
    history = unit.get("review_history")
    label = str(unit.get("unit_id"))
    if not isinstance(history, list):
        errors.append(f"{label}: review_history must be a list")
        return []
    outcomes: list[str] = []
    for index, review in enumerate(history, 1):
        if not isinstance(review, dict):
            errors.append(f"{label}: review round {index} must be an object")
            continue
        if review.get("round") != index:
            errors.append(f"{label}: review rounds must be contiguous")
        digest = review.get("diff_digest")
        snapshot = validate_diff_snapshot(review.get("diff_snapshot"), workspace,
                                          f"{label}: review round {index} diff_snapshot", errors)
        if snapshot is not None and (digest != snapshot["diff_digest"] or review.get("changed_paths") != snapshot["changed_paths"]):
            errors.append(f"{label}: review round {index} diff fields do not match snapshot")
        changed_paths = snapshot["changed_paths"] if snapshot is not None else review.get("changed_paths")
        if isinstance(changed_paths, list) and changed_paths:
            for path in changed_paths:
                if not path_matches(path, unit.get("allowed_paths", [])):
                    errors.append(f"{label}: changed path is outside unit scope: {path}")
                forbidden = contract.get("forbidden_changes")
                if isinstance(forbidden, list) and any(
                        isinstance(item, str) and paths_overlap(path, item) for item in forbidden):
                    errors.append(f"{label}: changed path overlaps forbidden_changes: {path}")
        else:
            errors.append(f"{label}: changed_paths is invalid")
        statuses = []
        thread_ids = []
        for key, model in (("verifier", "gpt-5.6-luna"), ("scope_reviewer", "gpt-5.6-terra")):
            reviewer = review.get(key)
            if not isinstance(reviewer, dict):
                errors.append(f"{label}: {key} review must be an object")
                reviewer = {}
            if reviewer.get("model") != model or reviewer.get("effort") != "xhigh":
                errors.append(f"{label}: {key} model or effort is invalid")
            status = reviewer.get("status")
            if not isinstance(status, str) or status not in {"pass", "fail"}:
                errors.append(f"{label}: {key} status is invalid")
            statuses.append(status)
            thread_id = reviewer.get("thread_id")
            if not required_text(thread_id):
                errors.append(f"{label}: {key} thread_id is required")
            thread_ids.append(thread_id)
            if reviewer.get("diff_digest") != digest or not isinstance(reviewer.get("diff_digest"), str):
                errors.append(f"{label}: {key} diff digest does not match")
            evidence = reviewer.get("evidence")
            if not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence):
                errors.append(f"{label}: {key} evidence is required")
        if len(thread_ids) == 2 and required_text(thread_ids[0]) and thread_ids[0] == thread_ids[1]:
            errors.append(f"{label}: review thread IDs must be distinct")
        outcome = review.get("outcome")
        expected = "pass" if statuses == ["pass", "pass"] else "fail"
        if outcome != expected:
            errors.append(f"{label}: review outcome does not match reviewer statuses")
        outcomes.append(outcome if isinstance(outcome, str) and outcome in {"pass", "fail"} else expected)
    improvements = unit.get("improvement_history")
    if not isinstance(improvements, list):
        errors.append(f"{label}: improvement_history must be a list")
        improvements = []
    failures = [index for index, outcome in enumerate(outcomes, 1) if outcome == "fail"]
    failure_records: dict[int, dict] = {}
    pairs: set[tuple[object, object]] = set()
    for record in improvements:
        if not isinstance(record, dict):
            errors.append(f"{label}: improvement record must be an object")
            continue
        after_round = record.get("after_round")
        if not isinstance(after_round, int) or isinstance(after_round, bool) or after_round not in failures:
            errors.append(f"{label}: improvement record must follow a failed round")
            continue
        ordinal = failures.index(after_round) + 1
        kind = "terra_recovery" if ordinal == 1 else "sol_replan" if ordinal == 2 else "recursive_improvement"
        validate_improvement(record, after_round, kind, label, errors)
        if after_round in failure_records:
            errors.append(f"{label}: duplicate improvement round")
        failure_records[after_round] = record
        pair = (record.get("failure_signature"), record.get("strategy_digest"))
        if pair in pairs:
            errors.append(f"{label}: failure signature and strategy digest were reused")
        pairs.add(pair)
    status = unit.get("status")
    for after_round in failures:
        optional_terminal = status in {"blocked", "failed", "awaiting_user"} and after_round == failures[-1]
        pending_improvement = status == "reviewing" and after_round == failures[-1]
        if not optional_terminal and not pending_improvement and after_round not in failure_records:
            errors.append(f"{label}: failed round {after_round} requires improvement")
    replan_count = unit.get("replan_count", 0)
    if not isinstance(replan_count, int) or isinstance(replan_count, bool) or replan_count < 0:
        errors.append(f"{label}: replan_count must be a nonnegative integer")
        replan_count = 0
    expected_replans = sum(record.get("kind") in {"sol_replan", "recursive_improvement"} for record in failure_records.values())
    if replan_count != expected_replans:
        errors.append(f"{label}: replan_count does not match improvement history")
    if "pass" in outcomes:
        first_pass = outcomes.index("pass")
        if any(outcome == "fail" for outcome in outcomes[first_pass + 1:]):
            errors.append(f"{label}: failed review cannot follow a passing round")
    pending_improvement = (status == "reviewing" and outcomes and outcomes[-1] == "fail"
                           and failures[-1] not in failure_records)
    if status == "reviewing" and outcomes and outcomes[-1] == "fail" and not pending_improvement:
        errors.append(f"{label}: reviewing cannot end on a failed review")
    if status == "recovery" and (outcomes != ["fail"] or not failures or failures[0] != 1
                                  or 1 not in failure_records or failure_records[1].get("kind") != "terra_recovery"):
        errors.append(f"{label}: recovery requires first failed round terra_recovery")
    if status == "replan_required" and (len(failures) < 2 or not outcomes or outcomes[-1] != "fail"
                                         or failures[-1] not in failure_records):
        errors.append(f"{label}: replan_required requires two failed rounds and a corresponding later improvement")
    if status == "passed":
        if not outcomes or outcomes[-1] != "pass":
            errors.append(f"{label}: passed unit must end in a passing review")
        if any(failure not in failure_records for failure in failures):
            errors.append(f"{label}: passed unit requires improvement for every failed round")
    return outcomes


def has_pending_improvement(unit: dict) -> bool:
    if unit.get("status") != "reviewing":
        return False
    reviews = unit.get("review_history")
    improvements = unit.get("improvement_history")
    if not isinstance(reviews, list) or not isinstance(improvements, list) or not reviews:
        return False
    failures = [index for index, review in enumerate(reviews, 1)
                if isinstance(review, dict) and review.get("outcome") == "fail"]
    if not failures or not isinstance(reviews[-1], dict) or reviews[-1].get("outcome") != "fail":
        return False
    return not any(isinstance(record, dict) and record.get("after_round") == failures[-1]
                   for record in improvements)


def validate_test_receipts(unit: dict, errors: list[str], workspace: Path | None = None) -> dict[int, dict]:
    label = str(unit.get("unit_id"))
    commands = unit.get("acceptance_commands")
    receipts = unit.get("test_receipts")
    if not isinstance(receipts, list):
        errors.append(f"{label}: test_receipts must be a list")
        return {}
    latest: dict[int, dict] = {}
    occurrences: dict[int, int] = {}
    required = {"test_id", "command_index", "command_sha256", "source", "execution_receipt_sha256", "diff_snapshot",
                "observer_role", "observer_thread_id", "diff_digest", "started_at", "ended_at",
                "exit_code", "output_sha256", "status"}
    execution_receipts: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, dict) or not required.issubset(receipt):
            errors.append(f"{label}: test receipt is incomplete")
            continue
        index = receipt.get("command_index")
        if not isinstance(index, int) or isinstance(index, bool) or not isinstance(commands, list) or not 1 <= index <= len(commands):
            errors.append(f"{label}: test receipt command_index is invalid")
            continue
        occurrences[index] = occurrences.get(index, 0) + 1
        if receipt.get("test_id") != f"test-{index}-{occurrences[index]}":
            errors.append(f"{label}: test receipt ID/order is invalid")
        command = commands[index - 1]
        expected_digest = "sha256:" + hashlib.sha256(command.encode("utf-8")).hexdigest() if isinstance(command, str) else None
        if receipt.get("command_sha256") != expected_digest or not isinstance(expected_digest, str):
            errors.append(f"{label}: test receipt command digest does not match")
        execution_digest = receipt.get("execution_receipt_sha256")
        if not isinstance(execution_digest, str) or not SHA256.fullmatch(execution_digest):
            errors.append(f"{label}: execution receipt digest is invalid")
        elif execution_digest in execution_receipts:
            errors.append(f"{label}: duplicate execution receipt")
        else:
            execution_receipts.add(execution_digest)
        if receipt.get("source") != "codex.exec_command" or receipt.get("observer_role") != "verifier":
            errors.append(f"{label}: test receipt source or observer role is invalid")
        if not required_text(receipt.get("observer_thread_id")):
            errors.append(f"{label}: observer thread ID is invalid")
        snapshot = validate_diff_snapshot(receipt.get("diff_snapshot"), workspace,
                                          f"{label}: test receipt diff_snapshot", errors)
        if snapshot is not None and receipt.get("diff_digest") != snapshot["diff_digest"]:
            errors.append(f"{label}: test receipt diff does not match snapshot")
        if not required_text(receipt.get("started_at")) or not required_text(receipt.get("ended_at")):
            errors.append(f"{label}: test receipt timestamps are invalid")
        if not isinstance(receipt.get("output_sha256"), str) or not SHA256.fullmatch(receipt["output_sha256"]):
            errors.append(f"{label}: test receipt output digest is invalid")
        status, exit_code = receipt.get("status"), receipt.get("exit_code")
        if status not in {"pass", "fail", "timeout"}:
            errors.append(f"{label}: test receipt status is invalid")
        elif (status == "pass" and exit_code != 0) or (status == "fail" and (not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code == 0)) or (status == "timeout" and exit_code is not None):
            errors.append(f"{label}: test receipt status and exit_code disagree")
        latest[index] = receipt
    if unit.get("status") == "passed" and isinstance(commands, list) and any(latest.get(index, {}).get("status") != "pass" for index in range(1, len(commands) + 1)):
        errors.append(f"{label}: passed unit requires a passing latest receipt for every command")
    return latest


def validate_unit(unit: dict, contract: dict, seen: set[str], errors: list[str], workspace: Path | None = None) -> list[str]:
    unit_id = unit.get("unit_id")
    if not isinstance(unit_id, str) or not SLUG.fullmatch(unit_id):
        errors.append("unit_id must be a safe nonempty slug and unique")
    elif unit_id in seen:
        errors.append("unit_id must be nonempty and unique")
    else:
        seen.add(unit_id)
    status = unit.get("status")
    if not isinstance(status, str) or status not in UNIT_STATES:
        errors.append(f"{unit_id}: invalid status")
    if unit.get("writer") != "hwahap-luna-implementer":
        errors.append(f"{unit_id}: invalid writer")
    if not required_text(unit.get("title")):
        errors.append(f"{unit_id}: title must be a nonempty observable-change description")
    for field in ("allowed_paths", "acceptance_commands"):
        if not isinstance(unit.get(field), list) or not unit[field]:
            errors.append(f"{unit_id}: {field} must be nonempty")
    commands = unit.get("acceptance_commands")
    if isinstance(commands, list) and any(not safe_test_command(command) for command in commands):
        errors.append("test command contains sensitive data")
    if "reviews" in unit and not isinstance(unit.get("reviews"), dict):
        errors.append(f"{unit_id}: reviews must be an object")
    if contract.get("locked") and isinstance(contract.get("allowed_paths"), list) and isinstance(unit.get("allowed_paths"), list):
        if any(not isinstance(path, str) or path not in contract["allowed_paths"] for path in unit["allowed_paths"]):
            errors.append(f"{unit_id}: allowed_paths must be exact locked-contract members")
    if contract.get("locked") and isinstance(contract.get("test_commands"), list) and isinstance(unit.get("acceptance_commands"), list):
        if any(not isinstance(command, str) or command not in contract["test_commands"] for command in unit["acceptance_commands"]):
            errors.append(f"{unit_id}: acceptance_commands must be exact locked-contract members")
    latest_receipts = validate_test_receipts(unit, errors, workspace)
    if isinstance(status, str) and status in FAILURE_STATES:
        validate_failure(unit.get("failure"), str(unit_id), errors)
    outcomes = validate_review_history(unit, contract, errors, workspace) if isinstance(status, str) else []
    history = unit.get("review_history")
    if status == "planned" and history != []:
        errors.append(f"{unit_id}: planned unit must have empty review_history")
    elif status == "implementing" and isinstance(history, list) and history:
        if not outcomes or outcomes[-1] != "fail":
            errors.append(f"{unit_id}: implementing unit history must end in a failed review")
    if status == "passed" and isinstance(history, list) and history and outcomes and outcomes[-1] == "pass":
        review = history[-1]
        verifier = review.get("verifier") if isinstance(review, dict) else None
        if isinstance(verifier, dict):
            for receipt in latest_receipts.values():
                if receipt.get("observer_thread_id") != verifier.get("thread_id"):
                    errors.append(f"{unit_id}: passing test receipt observer does not match review verifier")
                if receipt.get("diff_digest") != review.get("diff_digest"):
                    errors.append(f"{unit_id}: passing test receipt diff does not match review")
                if receipt.get("diff_snapshot") != review.get("diff_snapshot"):
                    errors.append(f"{unit_id}: passing test receipt snapshot does not match review")
    return outcomes


def validate_records(value: object, fields: tuple[str, ...], label: str, errors: list[str]) -> int:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return 0
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        if any(not required_text(item.get(field)) for field in fields):
            errors.append(f"{label}[{index}] is incomplete")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(not required_text(ref) for ref in evidence):
            errors.append(f"{label}[{index}].evidence must be nonempty")
    return len(value)


def validate_approved_spec(workspace: Path, spec: dict, contract: dict, errors: list[str]) -> None:
    source = spec.get("source")
    source_path = Path(source) if isinstance(source, str) else workspace / "<invalid-spec-source>"
    if not source_path.is_absolute():
        source_path = workspace / source_path
    if lexical_path_has_symlink(source_path) or source_path.is_symlink() or not source_path.is_file():
        errors.append("approved spec source is missing or unsafe")
        return
    try:
        actual_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        metadata = frontmatter(source_path)
    except (OSError, UnicodeError, HwahapError):
        errors.append("approved spec source is invalid or unreadable")
        return
    if actual_digest != spec.get("sha256"):
        errors.append("approved spec source hash does not match")
    if metadata.get("confirmed_at") != spec.get("confirmed_at") or metadata.get("title") != contract.get("goal"):
        errors.append("approved spec frontmatter does not match contract")


def validate_metrics(run: dict, units: list[dict], histories: list[list[str]], deviations: list[object], errors: list[str]) -> None:
    metrics = run.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("metrics must be an object")
        return
    counters = ("unit_count", "review_rounds", "recoveries", "replans", "scope_deviations", "test_runs", "elapsed_seconds")
    for field in counters:
        value = metrics.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"metrics.{field} must be a nonnegative integer")
    agent_runs = metrics.get("agent_runs")
    expected_agent_receipt = {"availability": "unavailable", "reason": "platform aggregate not exposed", "source": None, "total": None}
    if agent_runs != expected_agent_receipt:
        errors.append("metrics.agent_runs must be an unavailable platform receipt")
    token_usage = metrics.get("token_usage")
    if not isinstance(token_usage, dict):
        errors.append("metrics.token_usage must be an object")
    else:
        availability = token_usage.get("availability")
        total = token_usage.get("total")
        if not isinstance(availability, str) or availability not in {"available", "unavailable"}:
            errors.append("token_usage availability is invalid")
        elif availability == "available":
            source = token_usage.get("source")
            if (not isinstance(total, int) or isinstance(total, bool) or total < 0
                    or source not in {"codex.get_goal", "codex.update_goal"} or token_usage.get("reason") is not None):
                errors.append("available token_usage requires validated Goal receipt, total, and source")
            else:
                goal_link = run.get("goal_link") if isinstance(run.get("goal_link"), dict) else {}
                history = goal_link.get("history") if isinstance(goal_link.get("history"), list) else []
                receipts = [entry for entry in history if isinstance(entry, dict)
                            and entry.get("source") == source and isinstance(entry.get("receipt_sha256"), str)
                            and SHA256.fullmatch(entry["receipt_sha256"])
                            and entry.get("token_total") == total]
                if not receipts:
                    errors.append("available token_usage requires a matching Goal receipt")
        elif availability == "unavailable" and (token_usage.get("source") is not None or total is not None
                                                 or not required_text(token_usage.get("reason"))):
            errors.append("unavailable token_usage requires null source, null total, and reason")
    fast_status = run.get("fast_status")
    if fast_status != "unknown":
        errors.append("fast_status is invalid")
    if run.get("status") == "completed":
        expected = {
            "unit_count": len(units),
            "review_rounds": sum(len(history) for history in histories),
            "recoveries": sum(bool(history and history[0] == "fail") for history in histories),
            "replans": sum(sum(record.get("kind") in {"sol_replan", "recursive_improvement"}
                                for record in unit.get("improvement_history", []) if isinstance(record, dict))
                            for unit in units if isinstance(unit.get("improvement_history"), list)),
            "scope_deviations": len(deviations),
            "test_runs": sum(len(unit.get("test_receipts", [])) for unit in units if isinstance(unit.get("test_receipts"), list)),
        }
        for field, value in expected.items():
            if metrics.get(field) != value:
                errors.append(f"metrics.{field} is inconsistent")


def validate_events(path: Path, run: dict, units: list[dict], errors: list[str]) -> list[dict]:
    events: list[dict] = []
    try:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                errors.append(f"events.jsonl line {number} must be an object")
            else:
                events.append(event)
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append("invalid events.jsonl")
        return []
    if not events:
        if run.get("status") == "initialized" and not units:
            return events
        errors.append("events.jsonl is required for non-initial state")
        return events
    unit_ids = {unit.get("unit_id") for unit in units if required_text(unit.get("unit_id"))}
    current: dict[str, str] = {"run": "initialized"}
    current.update({unit_id: "planned" for unit_id in unit_ids})
    for expected_sequence, event in enumerate(events, 1):
        if any(field not in event for field in EVENT_FIELDS):
            errors.append(f"events.jsonl sequence {expected_sequence} is incomplete")
            continue
        if event.get("type") != "state_transition":
            errors.append(f"events.jsonl sequence {expected_sequence} has invalid type")
        if event.get("sequence") != expected_sequence or not isinstance(event.get("sequence"), int) or isinstance(event.get("sequence"), bool):
            errors.append("event sequence must be contiguous starting at 1")
        if any(not required_text(event.get(field)) for field in ("timestamp", "type", "entity", "from", "to", "actor", "role", "reason", "input_digest")):
            errors.append(f"events.jsonl sequence {expected_sequence} has invalid text fields")
        review_round = event.get("review_round")
        if not isinstance(review_round, int) or isinstance(review_round, bool) or review_round < 0:
            errors.append(f"events.jsonl sequence {expected_sequence} has invalid review_round")
        refs = event.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(not required_text(ref) for ref in refs):
            errors.append(f"events.jsonl sequence {expected_sequence} has invalid evidence_refs")
        entity = event.get("entity")
        if not isinstance(entity, str) or entity not in current:
            errors.append(f"events.jsonl entity is unknown: {entity}")
            continue
        if entity != "run" and current.get("run") in RUN_UNIT_MUTATION_BLOCKED_STATES:
            if current.get("run") in RUN_TERMINAL_STATES:
                errors.append(f"terminal run cannot have unit successors: {entity}")
            else:
                errors.append(f"final_review run cannot have unit successors: {entity}")
        source, target = event.get("from"), event.get("to")
        if not isinstance(source, str) or source != current[entity]:
            errors.append(f"events.jsonl current state mismatch for {entity}")
        graph = RUN_TRANSITIONS if entity == "run" else UNIT_TRANSITIONS
        if isinstance(source, str) and source in (RUN_TERMINAL_STATES if entity == "run" else UNIT_TERMINAL_STATES):
            errors.append(f"terminal state cannot have successors: {entity}")
        elif (not isinstance(source, str) or not isinstance(target, str)
              or target not in graph.get(source, set())):
            errors.append(f"illegal transition for {entity}: {source} -> {target}")
        if entity != "run" and isinstance(target, str):
            required_run = {"implementing": "implementing", "reviewing": "reviewing",
                            "passed": "reviewing", "recovery": "recovering",
                            "replan_required": "replanning"}.get(target)
            if required_run and current.get("run") != required_run:
                errors.append(f"unit transition requires run status {required_run}")
            elif target in {"blocked", "failed", "awaiting_user"} and current.get("run") not in {
                    "implementing", "reviewing", "recovering", "replanning"}:
                errors.append("unit terminal transition requires an active run phase")
        if isinstance(target, str):
            current[entity] = target
            if entity != "run":
                unit_states = [value for key, value in current.items() if key != "run"]
                if sum(value not in {"planned", "passed"} for value in unit_states) > 1:
                    errors.append("only one unit may be unresolved")
    if current.get("run") != run.get("status"):
        errors.append("last run transition does not match current status")
    for unit in units:
        unit_id = unit.get("unit_id")
        if required_text(unit_id) and current.get(unit_id, "planned") != unit.get("status"):
            errors.append(f"last unit transition does not match current status: {unit_id}")
    return events


def validate_final_review(final: object, completed: bool, errors: list[str], workspace: Path) -> None:
    if not isinstance(final, dict):
        errors.append("final_review must be an object")
        return
    attempts = final.get("attempts")
    if not isinstance(attempts, list):
        errors.append("final_review.attempts must be a list")
        return
    status = final.get("status")
    if status not in {"pending", "pass", "fail"}:
        errors.append("final_review.status is invalid")
    if len(attempts) > 2:
        errors.append("final_review.attempts cannot contain more than two attempts")
    for index, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict):
            errors.append(f"final_review.attempts[{index}] must be an object")
            continue
        if (set(attempt) != FINAL_REVIEW_ATTEMPT_FIELDS
                or attempt.get("model") != "gpt-5.6-sol" or attempt.get("effort") not in {"ultra", "xhigh"}
                or attempt.get("status") not in {"pass", "fail", "unavailable", "unsupported"}
                or not required_text(attempt.get("thread_id"))):
            errors.append(f"final_review.attempts[{index}] is incomplete")
        snapshot = validate_diff_snapshot(attempt.get("diff_snapshot"), workspace,
                                          f"final_review.attempts[{index}].diff_snapshot", errors)
        if snapshot is not None and attempt.get("diff_digest") != snapshot["diff_digest"]:
            errors.append(f"final_review.attempts[{index}].diff_digest does not match snapshot")
        evidence = attempt.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence):
            errors.append(f"final_review.attempts[{index}].evidence must be nonempty")
    valid = False
    if status == "pending":
        valid = len(attempts) == 0 or (
            len(attempts) == 1 and isinstance(attempts[0], dict)
            and attempts[0].get("effort") == "ultra"
            and attempts[0].get("status") in {"unavailable", "unsupported"}
        )
    elif status == "pass":
        valid = (
            len(attempts) == 1 and isinstance(attempts[0], dict)
            and attempts[0].get("effort") == "ultra" and attempts[0].get("status") == "pass"
        ) or (
            len(attempts) == 2 and all(isinstance(attempt, dict) for attempt in attempts)
            and attempts[0].get("effort") == "ultra"
            and attempts[0].get("status") in {"unavailable", "unsupported"}
            and attempts[1].get("effort") == "xhigh" and attempts[1].get("status") == "pass"
        )
    elif status == "fail":
        valid = (
            len(attempts) == 1 and isinstance(attempts[0], dict)
            and attempts[0].get("effort") == "ultra" and attempts[0].get("status") == "fail"
        ) or (
            len(attempts) == 2 and all(isinstance(attempt, dict) for attempt in attempts)
            and attempts[0].get("effort") == "ultra"
            and attempts[0].get("status") in {"unavailable", "unsupported"}
            and attempts[1].get("effort") == "xhigh"
            and attempts[1].get("status") in {"fail", "unavailable", "unsupported"}
        )
    if not valid:
        errors.append("final_review status and attempts do not match the allowed aggregate matrix")
        if completed:
            errors.append("completed final review attempts are invalid")
    if len(attempts) == 2 and all(isinstance(attempt, dict) for attempt in attempts):
        if attempts[0].get("diff_digest") != attempts[1].get("diff_digest"):
            errors.append("final review attempts must share diff digest")
        if attempts[0].get("diff_snapshot") != attempts[1].get("diff_snapshot"):
            errors.append("final review attempts must share diff snapshot")
    if completed and status != "pass":
        errors.append("completed final review must have aggregate pass")


def validate_final_review_snapshot_scope(final: object, contract: dict,
                                         units: list[dict], errors: list[str]) -> None:
    """Close final-review snapshots against both locked and passed-unit scope."""
    if not isinstance(final, dict) or not isinstance(final.get("attempts"), list):
        return
    for attempt in final["attempts"]:
        if not isinstance(attempt, dict):
            continue
        snapshot = attempt.get("diff_snapshot")
        changed_paths = snapshot.get("changed_paths") if isinstance(snapshot, dict) else None
        if not isinstance(changed_paths, list) or not changed_paths:
            continue
        for path in changed_paths:
            if not isinstance(path, str):
                continue
            audit = evaluate_final_review_snapshot_path(path, contract, units)
            if not audit["contract_allowed"]:
                errors.append("final review snapshot path is outside locked contract scope")
            if not audit["passed_unit_covered"]:
                errors.append("final review snapshot path is outside passed-unit scope")
            if audit["forbidden_overlap"]:
                errors.append("final review snapshot path overlaps forbidden_changes")


def evaluate_final_review_snapshot_path(path: str, contract: dict, units: list[dict]) -> dict:
    contract_rules = contract.get("allowed_paths") if isinstance(contract, dict) else []
    contract_rules = [rule for rule in contract_rules if isinstance(rule, str)] if isinstance(contract_rules, list) else []
    matched_contract = [rule for rule in contract_rules if path_matches(path, [rule])]
    covering = []
    for unit in units:
        if not isinstance(unit, dict) or unit.get("status") != "passed":
            continue
        rules = unit.get("allowed_paths")
        rules = [rule for rule in rules if isinstance(rule, str) and safe_relative_path(rule)] if isinstance(rules, list) else []
        matched = [rule for rule in rules if path_matches(path, [rule])]
        if matched:
            covering.append({"unit_id": unit.get("unit_id"), "matched_rules": matched})
    forbidden = contract.get("forbidden_changes") if isinstance(contract, dict) else []
    matched_forbidden = [rule for rule in forbidden if isinstance(rule, str) and paths_overlap(path, rule)] if isinstance(forbidden, list) else []
    return {"contract_allowed": bool(matched_contract), "passed_unit_covered": bool(covering),
            "forbidden_overlap": bool(matched_forbidden), "matched_contract_rules": matched_contract,
            "covering_passed_units": covering, "matched_forbidden_rules": matched_forbidden,
            "verdict": "pass" if matched_contract and covering and not matched_forbidden else "fail"}


def build_scope_audit(run: dict, contract: dict, units: list[dict]) -> dict:
    audit = {"authority": "derived-report-only", "affects_gate": False,
             "source_diff_digest": None, "contract_lock_sha256": contract.get("lock_sha256"), "paths": []}
    final = run.get("final_review") if isinstance(run, dict) else None
    attempts = final.get("attempts") if isinstance(final, dict) else None
    passing = [item for item in attempts if isinstance(item, dict) and item.get("status") == "pass"] if isinstance(attempts, list) else []
    if len(passing) != 1 or not isinstance(passing[0].get("diff_snapshot"), dict):
        return audit
    snapshot = passing[0]["diff_snapshot"]
    paths = snapshot.get("changed_paths")
    if not isinstance(paths, list):
        return audit
    audit["source_diff_digest"] = snapshot.get("diff_digest")
    seen: set[str] = set()
    for path in paths:
        if not isinstance(path, str) or path in seen:
            continue
        seen.add(path)
        result = evaluate_final_review_snapshot_path(path, contract, units)
        result["path"] = path
        result["evidence"] = {"diff_digest": snapshot.get("diff_digest"),
                               "contract_lock_sha256": contract.get("lock_sha256"),
                               "passed_unit_ids": [item.get("unit_id") for item in result["covering_passed_units"]]}
        audit["paths"].append(result)
    return audit


def final_review_failure_code(final: object) -> str | None:
    if (not isinstance(final, dict) or final.get("status") != "fail"
            or not isinstance(final.get("attempts"), list)):
        return None
    attempts = final["attempts"]
    if not attempts or not isinstance(attempts[-1], dict):
        return None
    return {"fail": "HW_FINAL_REVIEW_FAILED", "unavailable": "HW_MODEL_UNAVAILABLE",
            "unsupported": "HW_MODEL_UNAVAILABLE"}.get(attempts[-1].get("status"))


def validate_final_review_lifecycle(run: dict, units: list[dict], contract: dict,
                                   events: list[dict], errors: list[str], workspace: Path) -> None:
    status = run.get("status")
    final = run.get("final_review")
    initial_final = isinstance(final, dict) and final.get("status") == "pending" and final.get("attempts") == []
    run_events = [(index, event) for index, event in enumerate(events)
                  if event.get("entity") == "run"]
    entries = [(index, event) for index, event in run_events if event.get("to") == "final_review"]
    exits = [(index, event) for index, event in run_events if event.get("from") == "final_review"]
    final_failure_claim = isinstance(run.get("failure"), dict) and run["failure"].get("code") == "HW_FINAL_REVIEW_FAILED"
    claim = ((isinstance(status, str) and status in {"final_review", "completed"})
             or bool(entries) or bool(exits) or not initial_final or final_failure_claim)
    if not claim:
        return
    validate_final_review_snapshot_scope(final, contract, units, errors)
    if (not isinstance(status, str) or status not in {"final_review", "completed", "awaiting_user"}) and not entries and not exits:
        errors.append("final_review claim is invalid before final review")
        validate_final_review_units(units, contract, errors, workspace)
        return
    if len(entries) != 1:
        errors.append("final_review requires exactly one entry event")
    if entries and exits and entries[0][0] > exits[0][0]:
        errors.append("final_review entry must precede its exit")
    if status == "final_review":
        if exits:
            errors.append("final_review status cannot have an exit event")
        if final_failure_claim:
            errors.append("final review failure requires awaiting_user")
        valid_errors: list[str] = []
        validate_final_review(final, False, valid_errors, workspace)
        if valid_errors:
            errors.append("final_review aggregate is invalid")
    elif status == "completed":
        if len(exits) != 1 or exits[0][1].get("to") != "completed":
            errors.append("completed run requires one final_review completion exit")
        if final_failure_claim:
            errors.append("completed run cannot claim final review failure")
        valid_errors = []
        validate_final_review(final, True, valid_errors, workspace)
        if valid_errors:
            errors.append("completed run requires a passing final_review aggregate")
    elif status == "awaiting_user" and entries:
        if len(exits) != 1 or exits[0][1].get("to") != "awaiting_user":
            errors.append("awaiting_user after final_review requires one failure exit")
        valid_errors = []
        validate_final_review(final, False, valid_errors, workspace)
        expected = final_review_failure_code(final)
        failure = run.get("failure")
        if valid_errors or expected is None or not isinstance(failure, dict) or failure.get("code") != expected:
            errors.append("awaiting_user final_review failure evidence is invalid")
    elif entries or exits:
        errors.append("final_review events do not match the current run status")
    if entries or exits or status in {"final_review", "completed"}:
        validate_final_review_units(units, contract, errors, workspace)
        validate_final_review_snapshot_chain(final, units, events, errors)


def final_review_passing_digest(final: object, workspace: Path) -> str | None:
    if not isinstance(final, dict) or not isinstance(final.get("attempts"), list):
        return None
    passing = [attempt for attempt in final["attempts"]
               if isinstance(attempt, dict) and attempt.get("status") == "pass"]
    if len(passing) != 1:
        return None
    errors: list[str] = []
    snapshot = validate_diff_snapshot(passing[0].get("diff_snapshot"), workspace, "final review snapshot", errors)
    return snapshot["diff_digest"] if snapshot is not None else None


def validate_run(args: argparse.Namespace) -> None:
    workspace_arg = Path(args.workspace).expanduser()
    if lexical_path_has_symlink(workspace_arg):
        raise HwahapError("HW_STATE_INVALID", "workspace must not use symlink components")
    workspace = workspace_arg.resolve()
    hwahap, run_dir = state_paths(workspace, args.run_id)
    if not getattr(args, "_skip_recovery", False):
        _recover_report_transaction(run_dir)
    units_dir = run_dir / "units"
    required = [run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl"]
    for label, path in ((".hwahap", hwahap), ("runs", hwahap / "runs"), ("run", run_dir), ("units", units_dir)):
        if path.is_symlink() or not path.is_dir():
            raise HwahapError("HW_STATE_INVALID", f"{label} must be a real directory")
    for path in required:
        if not _single_regular_file(path):
            raise HwahapError("HW_STATE_INVALID", f"{path.name} must be a real file")
    contract, run = read_json(required[0]), read_json(required[1])
    errors: list[str] = []
    validate_state_strings(contract, "contract", errors, skip_command_fields=True)
    validate_state_strings(run, "run", errors)
    unit_files = read_unit_files(units_dir)
    for path, _, unit in unit_files:
        if unit.get("unit_id") != path.stem:
            errors.append("unit filename does not match internal unit_id")
        validate_state_strings(unit, f"unit {path.stem}", errors, skip_command_fields=True)
    try:
        for index, event in enumerate(parse_events(required[2]), 1):
            validate_state_strings(event, f"events.jsonl line {index}", errors)
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    if errors:
        raise HwahapError("HW_STATE_INVALID", "state value contains sensitive data")
    try:
        installed_profiles = verify_installed_agents(workspace)
    except HwahapError as exc:
        if exc.code == "HW_AGENT_CONFIG_INVALID":
            raise
        errors.append("installed Hwahap profiles are invalid")
        installed_profiles = {}
    if contract.get("schema_version") != 1 or run.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if contract.get("goal_id") != args.run_id or run.get("goal_id") != args.run_id:
        errors.append("goal_id mismatch")
    spec = contract.get("spec")
    if not isinstance(spec, dict):
        errors.append("spec must be an object")
        spec = {}
    if not required_text(spec.get("source")) or not re.fullmatch(r"[0-9a-f]{64}", str(spec.get("sha256", ""))) or not required_text(spec.get("confirmed_at")):
        errors.append("approved spec evidence is incomplete")
    else:
        validate_approved_spec(workspace, spec, contract, errors)
    status = run.get("status")
    if (not isinstance(status, str) or status not in RUN_STATES or run.get("roles") != ROLE_MAP
            or run.get("agent_profiles") != installed_profiles):
        errors.append("run status, role map, or agent profiles are invalid")
    if isinstance(status, str) and status in RUN_FAILURE_STATES:
        validate_failure(run.get("failure"), "run", errors)
    elif run.get("failure") is not None:
        errors.append("non-failure run must not contain failure")
    validate_goal_link(run.get("goal_link"), errors)
    validate_improvement_candidates(run.get("improvement_candidates"), errors)
    locked = contract.get("locked")
    if not isinstance(locked, bool):
        errors.append("locked must be a boolean")
    if locked and any(not isinstance(contract.get(field), list) or not contract[field] for field in CONTRACT_LISTS):
        errors.append("locked contract fields must be nonempty")
    forbidden = contract.get("forbidden_changes")
    commands = contract.get("test_commands")
    if isinstance(commands, list):
        if any(not safe_test_command(command) for command in commands):
            errors.append("test command contains sensitive data")
    for field in ("allowed_paths", "forbidden_changes"):
        values = contract.get(field)
        if isinstance(values, list):
            for value in values:
                if not safe_relative_path(value):
                    errors.append(f"contract.{field} contains an unsafe path")
        elif field in ("allowed_paths", "forbidden_changes"):
            errors.append(f"contract.{field} must be a list")
    lock_digest = contract.get("lock_sha256")
    if locked:
        if not isinstance(lock_digest, str) or not SHA256.fullmatch(lock_digest):
            errors.append("locked contract requires lock_sha256")
        elif lock_digest != canonical_contract_digest(contract):
            errors.append("lock_sha256 does not match contract")
    elif lock_digest is not None:
        errors.append("unlocked contract lock_sha256 must be null")
    units, seen, histories = [], set(), []
    execution_receipts: set[str] = set()
    for path, _, unit in unit_files:
        units.append(unit)
        histories.append(validate_unit(unit, contract, seen, errors, workspace))
        receipts = unit.get("test_receipts")
        if isinstance(receipts, list):
            for receipt in receipts:
                if not isinstance(receipt, dict):
                    continue
                digest = receipt.get("execution_receipt_sha256")
                if isinstance(digest, str) and digest in execution_receipts:
                    errors.append("duplicate execution receipt across units")
                elif isinstance(digest, str):
                    execution_receipts.add(digest)
        unit_paths = unit.get("allowed_paths")
        if isinstance(unit_paths, list):
            for unit_path in unit_paths:
                if not safe_relative_path(unit_path):
                    errors.append(f"{unit.get('unit_id')}: unsafe allowed path")
                if isinstance(forbidden, list) and isinstance(unit_path, str) and any(
                        isinstance(item, str) and paths_overlap(unit_path, item) for item in forbidden):
                    errors.append(f"{unit.get('unit_id')}: allowed path overlaps forbidden_changes")
    unresolved_units = [unit for unit in units if unit.get("status") not in {"planned", "passed"}]
    if len(unresolved_units) > 1:
        errors.append("only one unit may be unresolved")
    if any(has_pending_improvement(unit) for unit in units) and status not in ({"reviewing"} | RUN_FAILURE_STATES):
        errors.append("pending improvement requires run status reviewing or a terminal failure state")
    events = validate_events(required[2], run, units, errors)
    validate_final_review_lifecycle(run, units, contract, events, errors, workspace)
    last_event = events[-1] if events else {}
    if (status == "awaiting_user" and last_event.get("entity") == "run"
            and last_event.get("from") == "final_review" and last_event.get("to") == "awaiting_user"):
        expected_code = final_review_failure_code(run.get("final_review"))
        failure = run.get("failure")
        if expected_code is None or not isinstance(failure, dict) or failure.get("code") != expected_code:
            errors.append("final_review awaiting_user has invalid failure code")
    deviations = run.get("deviations")
    deferred = run.get("deferred_security")
    validate_records(deviations, ("summary", "root_cause", "impact", "prevention"), "deviations", errors)
    validate_records(deferred, ("summary", "reason", "next_action"), "deferred_security", errors)
    validate_metrics(run, units, histories, deviations if isinstance(deviations, list) else [], errors)
    final_review_errors: list[str] = []
    final = run.get("final_review")
    validate_final_review(final, status == "completed", final_review_errors, workspace)
    errors.extend(final_review_errors)
    candidates = run.get("improvement_candidates")
    if isinstance(candidates, list) and candidates and (
            not isinstance(final, dict) or final.get("status") != "pass" or final_review_errors):
        errors.append("improvement_candidates require a valid passing final_review")
    validate_report_schema(run, run_dir, contract, units, errors)
    if status == "completed":
        if not locked or not units or any(unit.get("status") != "passed" for unit in units):
            errors.append("completed run requires a locked contract and all units passed")
        goal_link = run.get("goal_link")
        current_goal = goal_link.get("current") if isinstance(goal_link, dict) else None
        if isinstance(current_goal, dict) and current_goal.get("mode") == "unobserved":
            errors.append("completed run requires an observed Goal link")
        final_status = run["final_review"].get("status") if isinstance(run.get("final_review"), dict) else None
        if not required_text(run.get("completed_at")) or final_status != "pass":
            errors.append("completed run requires final review pass and completed_at")
        final_digest = final_review_passing_digest(run.get("final_review"), workspace)
        if final_digest is None:
            errors.append("completed run requires a valid final passing review digest")
        else:
            try:
                events = parse_events(required[2])
            except (OSError, UnicodeError, json.JSONDecodeError):
                events = []
            if not events or events[-1].get("input_digest") != final_digest:
                errors.append("completed run input digest does not match final review digest")
    if errors:
        raise HwahapError("HW_STATE_INVALID", "; ".join(errors))
    if not getattr(args, "quiet", False):
        print(f"HW_OK: run={args.run_id} status={run['status']} units={len(units)}")


def parser() -> argparse.ArgumentParser:
    root = SafeArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="initialize a run from an approved PR/FAQ")
    init.add_argument("--workspace", required=True)
    init.add_argument("--goal-id", required=True)
    init.add_argument("--spec", required=True)
    init.set_defaults(handler=init_run)
    lock = commands.add_parser("lock", help="lock a filled contract and record its first transition")
    lock.add_argument("--workspace", required=True)
    lock.add_argument("--run-id", required=True)
    lock.add_argument("--actor", required=True)
    lock.add_argument("--reason", required=True)
    lock.add_argument("--evidence-ref", action="append", required=True)
    lock.set_defaults(handler=lock_contract)
    unit = commands.add_parser("add-unit", help="add one planned atomic unit")
    unit.add_argument("--workspace", required=True)
    unit.add_argument("--run-id", required=True)
    unit.add_argument("--unit-id", required=True)
    unit.add_argument("--title", required=True)
    unit.add_argument("--allowed-path", action="append", required=True)
    unit.add_argument("--acceptance-command", action="append", required=True)
    unit.set_defaults(handler=add_unit)
    test = commands.add_parser("run-test", help="compatibility command; test execution is disabled",
                               description="Compatibility command only; execution is disabled and no process is created.")
    test.add_argument("--workspace", required=True)
    test.add_argument("--run-id", required=True)
    test.add_argument("--unit-id", required=True)
    test.add_argument("--command-index", type=int, required=True)
    test.add_argument("--timeout-seconds", type=int, required=True)
    test.set_defaults(handler=run_test)
    receipt = commands.add_parser("record-test-receipt", help="record an external acceptance test receipt")
    receipt.add_argument("--workspace", required=True)
    receipt.add_argument("--run-id", required=True)
    receipt.add_argument("--unit-id", required=True)
    receipt.add_argument("--command-index", type=int, required=True)
    receipt.add_argument("--execution-receipt-sha256", required=True)
    receipt.add_argument("--observer-thread-id", required=True)
    receipt.add_argument("--diff-digest", required=True)
    receipt.add_argument("--base-commit", required=True)
    receipt.add_argument("--target-commit", required=True)
    receipt.add_argument("--started-at", required=True)
    receipt.add_argument("--ended-at", required=True)
    receipt.add_argument("--output-sha256", required=True)
    outcome = receipt.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--exit-code", type=int)
    outcome.add_argument("--timed-out", action="store_true")
    receipt.set_defaults(handler=record_test_receipt)
    move = commands.add_parser("transition", help="record one evidence-backed state transition")
    move.add_argument("--workspace", required=True)
    move.add_argument("--run-id", required=True)
    move.add_argument("--entity", required=True)
    move.add_argument("--to", required=True)
    move.add_argument("--actor", required=True)
    move.add_argument("--role", required=True)
    move.add_argument("--reason", required=True)
    move.add_argument("--input-digest", required=True)
    move.add_argument("--evidence-ref", action="append", required=True)
    move.add_argument("--review-round", type=int, default=0)
    move.add_argument("--failure-code")
    move.add_argument("--failure-reason")
    move.add_argument("--failure-evidence", action="append")
    move.add_argument("--failure-recovery")
    move.set_defaults(handler=transition)
    improvement = commands.add_parser("record-improvement", help="append one validated review improvement record")
    improvement.add_argument("--workspace", required=True)
    improvement.add_argument("--run-id", required=True)
    improvement.add_argument("--unit-id", required=True)
    improvement.add_argument("--actor", required=True)
    improvement.add_argument("--after-round", type=int, required=True)
    improvement.add_argument("--kind", required=True)
    improvement.add_argument("--failure-signature", required=True)
    improvement.add_argument("--root-cause", required=True)
    improvement.add_argument("--hypothesis", required=True)
    improvement.add_argument("--action", required=True)
    improvement.add_argument("--strategy-digest", required=True)
    improvement.add_argument("--scope-status", default="within_contract")
    improvement.add_argument("--evidence-ref", action="append", required=True)
    improvement.set_defaults(handler=record_improvement)
    candidate = commands.add_parser("record-improvement-candidate", help="record one report-only improvement candidate")
    candidate.add_argument("--workspace", required=True)
    candidate.add_argument("--run-id", required=True)
    candidate.add_argument("--summary", required=True)
    candidate.add_argument("--expected-effect", required=True)
    candidate.add_argument("--next-action", required=True)
    candidate.add_argument("--evidence-ref", action="append", required=True)
    candidate.set_defaults(handler=record_improvement_candidate)
    goal = commands.add_parser("goal-sync", help="record one Goal observation receipt")
    goal.add_argument("--workspace", required=True)
    goal.add_argument("--run-id", required=True)
    goal.add_argument("--mode", required=True, choices=("bound", "no_active_goal", "unavailable"))
    goal.add_argument("--thread-id")
    goal.add_argument("--objective-sha256")
    goal.add_argument("--receipt-sha256")
    goal.add_argument("--token-total", type=int)
    goal.add_argument("--reason", required=True)
    goal.add_argument("--evidence-ref", action="append", required=True)
    goal.set_defaults(handler=goal_sync)
    goal_complete = commands.add_parser("goal-complete-sync", help="record an external Goal completion receipt")
    goal_complete.add_argument("--workspace", required=True)
    goal_complete.add_argument("--run-id", required=True)
    goal_complete.add_argument("--receipt-sha256", required=True)
    goal_complete.add_argument("--sync-result", required=True, choices=("completed", "already_completed", "failed"))
    goal_complete.add_argument("--reason", required=True)
    goal_complete.add_argument("--evidence-ref", action="append", required=True)
    goal_complete.add_argument("--token-total", type=int)
    goal_complete.set_defaults(handler=goal_complete_sync)
    complete = commands.add_parser("complete", help="generate and validate the final report atomically")
    complete.add_argument("--workspace", required=True)
    complete.add_argument("--run-id", required=True)
    complete.add_argument("--actor", required=True)
    complete.add_argument("--reason", required=True)
    complete.add_argument("--input-digest", required=True)
    complete.add_argument("--evidence-ref", action="append", required=True)
    complete.set_defaults(handler=complete_run)
    validate = commands.add_parser("validate", help="validate one run")
    validate.add_argument("--workspace", required=True)
    validate.add_argument("--run-id", required=True)
    validate.set_defaults(handler=validate_run)
    return root


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        args.handler(args)
        return 0
    except HwahapError as exc:
        code = exc.code if exc.code in PUBLIC_ERROR_MESSAGES else "HW_STATE_INVALID"
        print(f"{code}: {PUBLIC_ERROR_MESSAGES[code]}", file=sys.stderr)
        return 1
    except Exception:
        print("HW_STATE_INVALID: command failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

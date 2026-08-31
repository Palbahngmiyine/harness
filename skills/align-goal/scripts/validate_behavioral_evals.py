#!/usr/bin/env python3
"""Validate align-goal forward-evaluation cases without judging model behavior."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import PurePosixPath
from typing import Any


TOP_KEYS = {"schema", "skill_path", "cases"}
CASE_KEYS = {
    "id",
    "title",
    "capability",
    "mode",
    "domains",
    "workspace",
    "stimulus",
    "artifacts_to_collect",
    "oracle",
}
WORKSPACE_KEYS = {"files", "runtime_notes"}
FILE_KEYS = {"path", "content"}
STIMULUS_KEYS = {"initial_user_message", "follow_ups"}
FOLLOW_UP_KEYS = {"trigger", "user_message", "repeat"}
ORACLE_KEYS = {"must_observe", "must_not_observe", "mechanical_checks"}
MODES = {"interactive", "cold_handoff"}
DOMAINS = {"general", "cli", "api", "ui", "stateful_workflow", "data_migration"}
REPEATS = {"once", "until_not_triggered"}
SINGLE_CAPABILITIES = {
    "naming_choice",
    "vague_reask",
    "cold_timeout_resolution",
    "question_batching",
    "policy_grouping_valid",
    "policy_grouping_invalid",
    "choice_change_invalidation",
    "private_local_coding",
    "pause_resume",
}
COLD_DOMAINS = {"cli", "api", "ui", "stateful_workflow", "data_migration"}


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(
            handle,
            object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {value}")
            ),
        )


def _exact_keys(value: Any, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label}: expected object")
        return False
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{label}: exact keys required; missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )
        return False
    return True


def _strings(value: Any, label: str, errors: list[str], *, nonempty: bool = True) -> bool:
    if not isinstance(value, list) or (nonempty and not value):
        errors.append(f"{label}: expected {'nonempty ' if nonempty else ''}array of strings")
        return False
    ok = True
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}]: expected nonempty string")
            ok = False
    if len(value) != len(set(item for item in value if isinstance(item, str))):
        errors.append(f"{label}: duplicate strings are not allowed")
        ok = False
    return ok


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def validate(document: Any) -> list[str]:
    errors: list[str] = []
    if not _exact_keys(document, TOP_KEYS, "document", errors):
        return errors
    if document["schema"] != "align-goal-behavioral-evals/v1":
        errors.append("document.schema: expected align-goal-behavioral-evals/v1")
    if not isinstance(document["skill_path"], str) or not document["skill_path"].strip():
        errors.append("document.skill_path: expected nonempty string")
    cases = document["cases"]
    if not isinstance(cases, list) or not cases:
        errors.append("document.cases: expected nonempty array")
        return errors

    ids: list[str] = []
    capability_counts: dict[str, int] = {}
    cold_domains: list[str] = []
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not _exact_keys(case, CASE_KEYS, label, errors):
            continue
        case_id = case["id"]
        if not isinstance(case_id, str) or not re.fullmatch(r"E0*[1-9][0-9]*", case_id):
            errors.append(f"{label}.id: expected E followed by a positive integer")
            case_id = f"index-{index}"
        ids.append(case_id)
        if not isinstance(case["title"], str) or not case["title"].strip():
            errors.append(f"{label}.title: expected nonempty string")
        capability = case["capability"]
        allowed_capabilities = SINGLE_CAPABILITIES | {"cold_domain_plan"}
        if capability not in allowed_capabilities:
            errors.append(f"{label}.capability: unknown capability {capability!r}")
        else:
            capability_counts[capability] = capability_counts.get(capability, 0) + 1
        if case["mode"] not in MODES:
            errors.append(f"{label}.mode: expected one of {sorted(MODES)}")
        if _strings(case["domains"], f"{label}.domains", errors):
            unknown_domains = set(case["domains"]) - DOMAINS
            if unknown_domains:
                errors.append(f"{label}.domains: unknown values {sorted(unknown_domains)}")
        if capability == "cold_domain_plan":
            if case["mode"] != "cold_handoff":
                errors.append(f"{label}: cold_domain_plan requires cold_handoff mode")
            if not isinstance(case["domains"], list) or len(case["domains"]) != 1:
                errors.append(f"{label}: cold_domain_plan requires exactly one domain")
            elif case["domains"][0] in COLD_DOMAINS:
                cold_domains.append(case["domains"][0])
            else:
                errors.append(f"{label}: cold_domain_plan domain must be one of {sorted(COLD_DOMAINS)}")

        workspace = case["workspace"]
        if _exact_keys(workspace, WORKSPACE_KEYS, f"{label}.workspace", errors):
            files = workspace["files"]
            if not isinstance(files, list) or not files:
                errors.append(f"{label}.workspace.files: expected nonempty array")
            else:
                paths: list[str] = []
                for file_index, file_entry in enumerate(files):
                    file_label = f"{label}.workspace.files[{file_index}]"
                    if not _exact_keys(file_entry, FILE_KEYS, file_label, errors):
                        continue
                    if not _safe_relative_path(file_entry["path"]):
                        errors.append(f"{file_label}.path: expected safe relative POSIX path")
                    else:
                        paths.append(file_entry["path"])
                    if not isinstance(file_entry["content"], str):
                        errors.append(f"{file_label}.content: expected string")
                if len(paths) != len(set(paths)):
                    errors.append(f"{label}.workspace.files: duplicate paths are not allowed")
            _strings(workspace["runtime_notes"], f"{label}.workspace.runtime_notes", errors)

        stimulus = case["stimulus"]
        if _exact_keys(stimulus, STIMULUS_KEYS, f"{label}.stimulus", errors):
            if not isinstance(stimulus["initial_user_message"], str) or not stimulus[
                "initial_user_message"
            ].strip():
                errors.append(f"{label}.stimulus.initial_user_message: expected nonempty string")
            follow_ups = stimulus["follow_ups"]
            if not isinstance(follow_ups, list):
                errors.append(f"{label}.stimulus.follow_ups: expected array")
            else:
                for follow_index, follow_up in enumerate(follow_ups):
                    follow_label = f"{label}.stimulus.follow_ups[{follow_index}]"
                    if not _exact_keys(follow_up, FOLLOW_UP_KEYS, follow_label, errors):
                        continue
                    for key in ("trigger", "user_message"):
                        if not isinstance(follow_up[key], str) or not follow_up[key].strip():
                            errors.append(f"{follow_label}.{key}: expected nonempty string")
                    if follow_up["repeat"] not in REPEATS:
                        errors.append(f"{follow_label}.repeat: expected one of {sorted(REPEATS)}")

        _strings(case["artifacts_to_collect"], f"{label}.artifacts_to_collect", errors)
        oracle = case["oracle"]
        if _exact_keys(oracle, ORACLE_KEYS, f"{label}.oracle", errors):
            for key in sorted(ORACLE_KEYS):
                _strings(oracle[key], f"{label}.oracle.{key}", errors)

    if len(ids) != len(set(ids)):
        errors.append("document.cases: duplicate case IDs are not allowed")
    numeric_ids = [
        int(case_id[1:]) for case_id in ids if re.fullmatch(r"E0*[1-9][0-9]*", case_id)
    ]
    if numeric_ids != list(range(1, len(cases) + 1)):
        errors.append("document.cases: case IDs must be ordered and contiguous from E1")
    for capability in sorted(SINGLE_CAPABILITIES):
        if capability_counts.get(capability) != 1:
            errors.append(f"coverage: {capability} requires exactly one case")
    if capability_counts.get("cold_domain_plan") != len(COLD_DOMAINS):
        errors.append(f"coverage: cold_domain_plan requires exactly {len(COLD_DOMAINS)} cases")
    if set(cold_domains) != COLD_DOMAINS or len(cold_domains) != len(set(cold_domains)):
        errors.append(
            "coverage: cold_domain_plan must cover cli, api, ui, stateful_workflow, "
            "and data_migration exactly once"
        )
    return errors


def _target_projection(document: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case["id"],
        "skill_path": document["skill_path"],
        "workspace": case["workspace"],
        "initial_user_message": case["stimulus"]["initial_user_message"],
        "artifacts_to_collect": case["artifacts_to_collect"],
    }


def _find_case(document: dict[str, Any], case_id: str) -> dict[str, Any] | None:
    return next((case for case in document["cases"] if case["id"] == case_id), None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate align-goal behavioral eval fixtures; this does not run or score an LLM."
    )
    parser.add_argument("path")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="print validation result as JSON")
    output.add_argument("--emit-target", metavar="CASE_ID", help="emit target-safe initial case input")
    output.add_argument("--emit-oracle", metavar="CASE_ID", help="emit assessor-only oracle")
    args = parser.parse_args(argv)
    try:
        document = _load(args.path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    errors = validate(document)
    if errors:
        if args.json or args.emit_target or args.emit_oracle:
            print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
        else:
            for error in errors:
                print(error, file=sys.stderr)
        return 1
    if args.emit_target or args.emit_oracle:
        case_id = args.emit_target or args.emit_oracle
        case = _find_case(document, case_id)
        if case is None:
            print(json.dumps({"valid": False, "errors": [f"unknown case ID: {case_id}"]}))
            return 2
        payload = _target_projection(document, case) if args.emit_target else {
            "case_id": case["id"],
            "follow_ups": case["stimulus"]["follow_ups"],
            "oracle": case["oracle"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.json:
        print(json.dumps({"valid": True, "case_count": len(document["cases"]), "errors": []}))
    else:
        print(f"PASS: {len(document['cases'])} behavioral eval cases are structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

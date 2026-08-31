#!/usr/bin/env python3
"""Deterministic contract/receipt tests for align-goal's structural validator.

Fixtures use the production ``spec_projection`` and digest implementation.  The
dialogue and recursive-discovery evaluations remain in the reference document.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "validate_goal_spec.py"
sys.path.insert(0, str(HERE))
import validate_goal_spec as validator  # noqa: E402

NOW = "2026-08-31T09:00:00+09:00"
LATER = "2026-08-31T09:30:00+09:00"
SURFACES = list(validator.SURFACES)
OUTPUT_KEYS = {
    "valid", "require", "next_action", "errors", "unresolved_choice_ids",
    "uncovered_surfaces", "untraced_spec_ids", "unverified_spec_ids",
    "graph_cycles", "graph_orphans", "stale_receipts", "spec_digest",
    "repository_context_digest",
}
FENCE = "`" * 3


def digest(value):
    """Use the validator's canonical JSON/digest implementation."""

    return validator.dg(value)


def fact(fid="F1", *, immutable=False):
    return {
        "id": fid,
        "observation": "The repository contains the align-goal contract surface.",
        "sources": [{
            "kind": "path", "value": "skills/align-goal/SKILL.md:1",
            "digest": "sha256:" + "1" * 64,
        }],
        "observed_at": NOW,
        "stability": "immutable_for_scope" if immutable else "snapshot",
        "stability_basis": "The target snapshot is fixed for this goal." if immutable else None,
        "limits": "This observation does not choose an implementation alternative.",
    }


def choice(cid="C1", *, status="confirmed", depends=None,
           affected_specs=None, affected_acceptance=None, affected_units=None):
    selected = status in {"confirmed", "superseded"}
    return {
        "id": cid,
        "question": "Which exact public contract value should be implemented?",
        "alternatives": [
            {"id": "ALT1", "value": "keep the canonical contract", "outcome_delta": "Keeps the documented contract value."},
            {"id": "ALT2", "value": "change the contract value", "outcome_delta": "Changes the observable contract."},
        ],
        "recommendation": {
            "alternative_id": "ALT1",
            "rationale": "The existing fact is evidence for this recommendation.",
            "evidence_fact_ids": ["F1"],
        },
        "depends_on_choice_ids": list(depends or []),
        "choice_kind": "discrete",
        "policy_targets": [],
        "user_response": ({
            "exact": f"{cid}=ALT1 keep the canonical contract",
            "turn_id": f"turn-{cid.lower()}", "confirmed_at": NOW,
        } if selected else None),
        "confirmed_alternative_id": "ALT1" if selected else None,
        "confirmed_value": "keep the canonical contract" if selected else None,
        "scope": ["the requested goal and its implementation handoff"],
        "consequences": ["The exact public contract remains stable."],
        "affected_spec_ids": list(affected_specs or []),
        "affected_acceptance_ids": list(affected_acceptance or []),
        "affected_unit_ids": list(affected_units or []),
        "status": status,
        "supersession": None,
    }


def specification(*, provenance_choice="C1", provenance_mode="choice"):
    return {
        "id": "S1", "kind": "behavior",
        "statement": "The implementation preserves the exact canonical contract value.",
        "provenance": {
            "mode": provenance_mode,
            "choice_ids": [provenance_choice] if provenance_mode == "choice" else [],
            "fact_ids": [],
            "derivation": None if provenance_mode == "choice" else "The immutable fact forces this result.",
        },
    }


def acceptance(*, acceptance_type="functional", measurement=None):
    return {
        "id": "A1", "spec_ids": ["S1"],
        "setup": "The repository snapshot is available.",
        "input": "A request for the canonical contract.",
        "action": "Run the implementation verification command.",
        "observable_or_inspection": "The resulting contract value is observable.",
        "pass_condition": "The exact canonical contract value is preserved.",
        "evidence": "Store the command output and inspection result.",
        "acceptance_type": acceptance_type, "measurement": measurement,
    }


def unit(*, uid="U1", specs=None, accepts=None, deps=None, order=1):
    return {
        "id": uid, "title": "Implement the canonical contract unit",
        "spec_ids": list(specs if specs is not None else ["S1"]),
        "acceptance_ids": list(accepts if accepts is not None else ["A1"]),
        "inputs": ["canonical contract and repository snapshot"],
        "outputs": ["verified implementation result"],
        "change_boundary": ["skills/align-goal/scripts"],
        "forbidden_changes": ["unrelated Hwahap files"],
        "dependency_unit_ids": list(deps or []), "execution_order": order,
        "completion_evidence": ["focused validator test output"],
    }


def base_contract(*, target="implementation", alignment="aligned",
                  handoff="ready", session="complete", with_reviews=True):
    c = {
        "contract_version": "align-goal/v1", "revision": 1, "target": target,
        "goal": {
            "statement": "Align the goal and implementation direction exactly.",
            "success": ["A cold consumer can write a choice-free implementation plan."],
            "failure": ["A material implementation choice remains implicit."],
            "non_goals": ["Proving every future implementation statement mathematically."],
        },
        "repository_context": {
            "root": "/workspace/project", "captured_at": NOW,
            "entries": [{"kind": "git_head", "locator": "HEAD", "digest": "sha256:" + "2" * 64}],
        },
        "facts": [fact()],
        "choices": [choice(affected_specs=["S1"], affected_acceptance=["A1"], affected_units=["U1"] if target == "implementation" else [])],
        "question_rounds": [{"number": 1, "choice_ids": ["C1"], "asked_at": NOW, "checkpoint": None}],
        "decision_surfaces": [
            {"id": f"DS{i + 1}", "name": surface, "classification": "applicable",
             "resolution": {"mode": "choice", "choice_ids": ["C1"], "fact_ids": [], "derivation": None},
             "reason": "The material choice governs this applicable surface."}
            for i, surface in enumerate(SURFACES)
        ],
        "specifications": [specification()], "acceptance_checks": [acceptance()],
        "implementation_units": [unit()] if target == "implementation" else [],
        "open_items": [], "reviews": {"ambiguity_auditor": None, "cold_consumer": None},
        "confirmations": {"alignment_summary": None, "handoff_document": None},
    }
    if with_reviews and alignment == "aligned":
        refresh(c, include_cold=target == "implementation", include_handoff=handoff == "ready")
    return c


def refresh(c, *, include_cold=True, include_handoff=True):
    """Create fresh receipts after all projection mutations are complete."""

    projection_keys = (
        "contract_version", "revision", "target", "goal", "facts", "choices",
        "question_rounds", "decision_surfaces", "specifications", "acceptance_checks",
        "implementation_units", "open_items",
    )
    spec_digest = digest({key: c[key] for key in projection_keys})
    repo_digest = digest(c["repository_context"])
    ambiguity = {
        "review_id": "R1", "reviewer": "ambiguity_auditor", "status": "pass",
        "spec_digest": spec_digest, "repository_context_digest": repo_digest,
        "generated_at": "2026-08-31T09:10:00+09:00",
        "output": {"new_material_choices": [], "counterexamples": [], "contradictions": [],
                   "invalid_forced_consequences": [], "invalid_local_coding": [], "unexamined_surfaces": []},
    }
    reviews = {"ambiguity_auditor": ambiguity, "cold_consumer": None}
    if include_cold:
        reviews["cold_consumer"] = {
            "review_id": "R2", "reviewer": "cold_consumer", "status": "pass",
            "spec_digest": spec_digest, "repository_context_digest": repo_digest,
            "generated_at": "2026-08-31T09:20:00+09:00",
            "output": {
                "steps": [{"step": "Implement and verify the canonical unit.", "spec_ids": ["S1"], "acceptance_ids": ["A1"], "unit_ids": ["U1"]}],
                "required_user_choices": [], "implicit_assumptions": [], "contradictions": [],
                "underspecified_clauses": [], "unmapped_spec_ids": [], "local_choices": [],
            },
        }
    c["reviews"] = reviews
    alignment = {
        "confirmation_id": "UC1", "exact_response": "The summary exactly reflects my individual answers.",
        "turn_id": "turn-summary", "confirmed_at": "2026-08-31T09:25:00+09:00",
        "spec_digest": spec_digest, "repository_context_digest": repo_digest,
        "ambiguity_review_id": "R1", "ambiguity_receipt_digest": digest(ambiguity),
    }
    handoff = None
    if include_handoff:
        cold = reviews["cold_consumer"]
        handoff = {**alignment, "confirmation_id": "UC2", "confirmed_at": "2026-08-31T09:30:00+09:00",
                   "cold_review_id": "R2", "cold_receipt_digest": digest(cold)}
    c["confirmations"] = {"alignment_summary": alignment, "handoff_document": handoff}


def rebind(c):
    """Rebind existing receipts after mutating their output or the projection."""

    projection_keys = (
        "contract_version", "revision", "target", "goal", "facts", "choices",
        "question_rounds", "decision_surfaces", "specifications", "acceptance_checks",
        "implementation_units", "open_items",
    )
    spec_digest = digest({key: c[key] for key in projection_keys})
    repo_digest = digest(c["repository_context"])
    for receipt in c["reviews"].values():
        if receipt is not None:
            receipt["spec_digest"] = spec_digest
            receipt["repository_context_digest"] = repo_digest
    alignment = c["confirmations"].get("alignment_summary")
    if alignment is not None:
        alignment["spec_digest"] = spec_digest
        alignment["repository_context_digest"] = repo_digest
        alignment["ambiguity_receipt_digest"] = digest(c["reviews"]["ambiguity_auditor"])
    handoff = c["confirmations"].get("handoff_document")
    if handoff is not None:
        handoff["spec_digest"] = spec_digest
        handoff["repository_context_digest"] = repo_digest
        handoff["ambiguity_receipt_digest"] = digest(c["reviews"]["ambiguity_auditor"])
        if c["reviews"].get("cold_consumer") is not None:
            handoff["cold_receipt_digest"] = digest(c["reviews"]["cold_consumer"])


def exploring_contract():
    c = base_contract(target="implementation", alignment="exploring", handoff="not_requested", session="active", with_reviews=False)
    c["choices"][0] = choice(status="candidate")
    c["question_rounds"] = []
    c["specifications"] = []
    c["acceptance_checks"] = []
    c["implementation_units"] = []
    return c


def superseded_contract(*, surface_uses_old=False, supersession_response="C1 is superseded by C2."):
    c = base_contract()
    c["choices"].append(choice("C2", affected_specs=["S1"], affected_acceptance=["A1"], affected_units=["U1"]))
    old = c["choices"][0]
    old["status"] = "superseded"
    old["affected_spec_ids"] = []
    old["affected_acceptance_ids"] = []
    old["affected_unit_ids"] = []
    old["supersession"] = {
        "exact_user_response": supersession_response,
        "turn_id": "turn-c2", "confirmed_at": LATER,
        "basis_choice_ids": ["C2"], "basis_fact_ids": [],
        "derivation": "C2 replaces the earlier direction.",
    }
    c["question_rounds"].append({"number": 2, "choice_ids": ["C2"], "asked_at": NOW, "checkpoint": None})
    c["specifications"][0]["provenance"]["choice_ids"] = ["C2"]
    if not surface_uses_old:
        for surface in c["decision_surfaces"]:
            surface["resolution"]["choice_ids"] = ["C2"]
    refresh(c)
    return c


def document(contract, *, alignment=None, handoff=None, target=None, session=None):
    target = target or contract["target"]
    alignment = alignment or ("aligned" if contract["choices"] and contract["choices"][0]["status"] == "confirmed" else "exploring")
    if handoff is None:
        handoff = "ready" if target == "implementation" and alignment == "aligned" and contract.get("implementation_units") else "not_requested"
    session = session or ("complete" if alignment == "aligned" else "active")
    front = {
        "schema": "align-goal/v1", "title": "Canonical fixture", "target": target,
        "session_status": session, "alignment_status": alignment, "handoff_status": handoff,
        "revision": "1", "created": NOW, "updated": NOW,
    }
    front_text = "\n".join(f"{key}: {value}" for key, value in front.items())
    return f"---\n{front_text}\n---\n\n# Projection\n\nThis prose may mention an assumption without changing canonical semantics.\n\n{FENCE}json align-goal-contract\n{json.dumps(contract, ensure_ascii=False, indent=2)}\n{FENCE}\n"


def document_with_raw_json(contract, raw_json, **kwargs):
    rendered = document(contract, **kwargs)
    marker = FENCE + "json align-goal-contract\n"
    start = rendered.index(marker) + len(marker)
    end = rendered.index("\n" + FENCE, start)
    return rendered[:start] + raw_json + rendered[end:]


class ValidatorTests(unittest.TestCase):
    maxDiff = None

    def run_doc(self, text, require="structural"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "goal.md"
            path.write_text(text, encoding="utf-8")
            return subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path), "--require", require, "--json"], capture_output=True, text=True)

    def result(self, contract, require="structural", **kwargs):
        return self.run_doc(document(contract, **kwargs), require)

    def assert_valid(self, contract, require="structural", **kwargs):
        result = self.result(contract, require, **kwargs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def assert_invalid(self, contract, needle=None, require="structural", **kwargs):
        result = self.result(contract, require, **kwargs)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        if needle:
            self.assertIn(needle, result.stdout, result.stdout)
        return json.loads(result.stdout)

    def assert_invalid_text(self, text, needle=None, require="structural"):
        result = self.run_doc(text, require)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        if needle:
            self.assertIn(needle, result.stdout, result.stdout)
        return json.loads(result.stdout)

    def test_canonical_exploring_structural_and_positive_gates(self):
        output = self.assert_valid(exploring_contract())
        self.assertEqual(output["next_action"], "map_choices")
        self.assertEqual(output["uncovered_surfaces"], sorted(SURFACES))
        self.assert_valid(base_contract(), "handoff-ready")
        decision = base_contract(target="decision", handoff="not_requested")
        decision["implementation_units"] = []
        refresh(decision, include_cold=False, include_handoff=False)
        self.assert_valid(decision, "aligned")

    def test_frontmatter_exact_keys_and_fence_cardinality(self):
        contract = base_contract()
        text = document(contract).replace("updated: " + NOW + "\n", "updated: " + NOW + "\nextra: x\n")
        self.assert_invalid_text(text, "frontmatter keys must be exactly")
        no_fence = document(contract).replace(FENCE + "json align-goal-contract\n", "").replace("\n" + FENCE + "\n", "\n")
        self.assert_invalid_text(no_fence, "exactly one")
        two_fences = document(contract) + "\n" + document(contract)[document(contract).index(FENCE + "json align-goal-contract\n"):]
        self.assert_invalid_text(two_fences, "exactly one")

    def test_duplicate_json_key_nan_alias_and_top_level_keys(self):
        contract = base_contract()
        raw = json.dumps(contract, ensure_ascii=False, indent=2)
        raw = raw.replace('"target": "implementation",', '"target": "implementation",\n  "target": "implementation",', 1)
        self.assert_invalid_text(document_with_raw_json(contract, raw), "duplicate JSON key")
        nan_raw = raw.replace('"target": "implementation",\n  "target": "implementation",', '"target": "implementation",', 1).replace('"revision": 1,', '"revision": NaN,', 1)
        self.assert_invalid_text(document_with_raw_json(contract, nan_raw), "non-standard JSON constant")
        contract = base_contract(); contract["next_action"] = "complete"
        self.assert_invalid(contract, "unexpected top-level keys")
        contract = base_contract(); contract["spec_digest"] = digest(contract)
        self.assert_invalid(contract, "unexpected top-level keys")
        contract = base_contract(); contract["acceptance"] = contract.pop("acceptance_checks")
        self.assert_invalid(contract, "missing top-level keys")

    def test_register_prefix_and_duplicate_ids(self):
        contract = base_contract(); contract["facts"][0]["id"] = "X1"
        self.assert_invalid(contract, "facts[0].id must match F")
        contract = base_contract(); contract["facts"].append(copy.deepcopy(contract["facts"][0]))
        self.assert_invalid(contract, "duplicate or reused ID")
        contract = base_contract(); contract["facts"].append({**fact("F2"), "id": "S1"})
        self.assert_invalid(contract, "facts[1].id must match F")

    def test_candidate_asked_null_positive_and_confirmation_negatives(self):
        contract = exploring_contract()
        contract["choices"].append(choice("C2", status="asked"))
        contract["question_rounds"] = [{"number": 1, "choice_ids": ["C2"], "asked_at": NOW, "checkpoint": None}]
        self.assert_valid(contract, alignment="exploring", handoff="not_requested", session="active")
        contract["choices"][1]["confirmed_value"] = "keep the canonical contract"
        self.assert_invalid(contract, "candidate/asked confirmation fields must be null")
        contract = base_contract(); del contract["choices"][0]["user_response"]
        self.assert_invalid(contract, "missing keys: user_response")
        contract = base_contract(); contract["choices"][0]["confirmed_value"] = "a different exact value"
        self.assert_invalid(contract, "confirmed_value must equal selected alternative.value")

    def test_all_vague_phrases_in_response_and_value_fail(self):
        for phrase in ("looks good", "you choose", "best judgment", "follow repo", "알아서 해줘"):
            with self.subTest(location="response", phrase=phrase):
                contract = base_contract(); contract["choices"][0]["user_response"]["exact"] = phrase
                self.assert_invalid(contract, "contains vague response/value")
        for phrase in ("looks good", "you choose", "best judgment", "follow the repository", "알아서 해주세요"):
            with self.subTest(location="value", phrase=phrase):
                contract = base_contract(); contract["choices"][0]["confirmed_value"] = phrase
                self.assert_invalid(contract, "contains vague response/value")

    def test_recommendation_only_and_policy_target_rules(self):
        contract = base_contract(); contract["choices"][0]["user_response"] = None
        self.assert_invalid(contract, "user_response required")
        contract = base_contract(); contract["choices"][0]["choice_kind"] = "policy"
        self.assert_invalid(contract, "policy_targets required")
        contract["choices"][0]["policy_targets"] = ["DS1", "DS1"]
        self.assert_invalid(contract, "policy_targets must be unique")
        contract["choices"][0]["policy_targets"] = ["DS1", "DS2"]
        rebind(contract)
        self.assert_valid(contract)

    def test_snapshot_forced_fails_immutable_forced_passes(self):
        contract = base_contract()
        contract["decision_surfaces"][0]["resolution"] = {"mode": "forced", "choice_ids": [], "fact_ids": ["F1"], "derivation": "The snapshot fact forces the result."}
        self.assert_invalid(contract, "forced fact basis must be immutable")
        contract = base_contract(); contract["facts"][0] = fact(immutable=True)
        contract["decision_surfaces"][0]["resolution"] = {"mode": "forced", "choice_ids": [], "fact_ids": ["F1"], "derivation": "The immutable fact forces the result."}
        refresh(contract)
        self.assert_valid(contract, "aligned")

    def test_exact_surface_names_ids_missing_duplicate_alias_and_uncovered(self):
        contract = base_contract(); contract["decision_surfaces"][0]["name"] = "goal_success_failure_nongoal"
        self.assert_invalid(contract, "name invalid exact surface")
        contract = base_contract(); contract["decision_surfaces"] = contract["decision_surfaces"][:-1]
        self.assert_invalid(contract, "exactly 12 entries")
        contract = base_contract(); contract["decision_surfaces"][1]["name"] = SURFACES[0]
        self.assert_invalid(contract, "duplicate decision surface name")
        contract = base_contract(); contract["decision_surfaces"][0]["id"] = "DS2"
        self.assert_invalid(contract, "id/name must be exact DS1..DS12 pair")
        output = self.assert_valid(exploring_contract())
        self.assertEqual(output["uncovered_surfaces"], sorted(SURFACES))

    def test_unconfirmed_and_superseded_choice_cannot_govern_spec(self):
        contract = base_contract(); contract["choices"][0]["status"] = "asked"
        self.assert_invalid(contract, "provenance choice must be confirmed")
        contract = base_contract(); contract["choices"].append(choice("C2"))
        c1 = contract["choices"][0]; c1["status"] = "superseded"
        c1["supersession"] = {"exact_user_response": "C1 is superseded by C2.", "turn_id": "turn-c2", "confirmed_at": LATER, "basis_choice_ids": ["C2"], "basis_fact_ids": [], "derivation": "C2 replaces the earlier direction."}
        contract["question_rounds"].append({"number": 2, "choice_ids": ["C2"], "asked_at": NOW, "checkpoint": None})
        self.assert_invalid(contract, "provenance choice must be confirmed")

    def test_missing_acceptance_unit_measurement_and_reverse_affected(self):
        contract = base_contract(); contract["acceptance_checks"] = []
        self.assert_invalid(contract, "references unknown ID A1")
        contract = base_contract(); contract["implementation_units"] = []; contract["choices"][0]["affected_unit_ids"] = []
        self.assert_invalid(contract, "handoff-ready requires nonempty S/A/U", require="handoff-ready")
        contract = base_contract(); contract["acceptance_checks"][0]["acceptance_type"] = "non_functional"; contract["acceptance_checks"][0]["measurement"] = None
        self.assert_invalid(contract, "measurement")
        contract = base_contract(); contract["choices"][0]["affected_spec_ids"] = []
        self.assert_invalid(contract, "must equal computed reverse affected IDs")

    def test_open_placeholder_assumption_and_projection_text_rules(self):
        contract = base_contract(); contract["open_items"] = [{"id": "O1", "kind": "choice", "description": "A material choice remains open.", "blocking_ids": ["S1"], "status": "open", "resolution": None}]
        refresh(contract); self.assert_invalid(contract, "open items remain", require="aligned")
        contract = base_contract(); contract["specifications"][0]["statement"] = "TODO decide the contract."
        self.assert_invalid(contract, "contains placeholder")
        contract = base_contract(); contract["goal"]["statement"] = "This assumption must be removed."
        self.assert_invalid(contract, "canonical goal contains assumption")
        self.assert_valid(base_contract())

    def test_nine_choices_split_and_round_dependencies(self):
        contract = base_contract(alignment="exploring", handoff="not_requested", session="active", with_reviews=False)
        for i in range(2, 10):
            contract["choices"].append(choice(f"C{i}"))
            contract["choices"][-1]["affected_spec_ids"] = []; contract["choices"][-1]["affected_acceptance_ids"] = []; contract["choices"][-1]["affected_unit_ids"] = []
        contract["question_rounds"] = [{"number": 1, "choice_ids": [f"C{i}" for i in range(1, 10)], "asked_at": NOW, "checkpoint": None}]
        self.assert_invalid(contract, "unique 1..8")
        contract["question_rounds"] = [{"number": 1, "choice_ids": [f"C{i}" for i in range(1, 9)], "asked_at": NOW, "checkpoint": None}, {"number": 2, "choice_ids": ["C9"], "asked_at": NOW, "checkpoint": None}]
        self.assert_valid(contract, alignment="exploring", handoff="not_requested", session="active")
        contract["question_rounds"].append({"number": 3, "choice_ids": ["C1"], "asked_at": NOW, "checkpoint": None})
        self.assert_invalid(contract, "exactly one round")
        contract = base_contract(alignment="exploring", handoff="not_requested", session="active", with_reviews=False)
        contract["choices"].append(choice("C2")); contract["choices"][1]["affected_spec_ids"] = []; contract["choices"][1]["affected_acceptance_ids"] = []; contract["choices"][1]["affected_unit_ids"] = []
        contract["choices"][0]["depends_on_choice_ids"] = ["C2"]
        contract["question_rounds"] = [{"number": 1, "choice_ids": ["C1"], "asked_at": NOW, "checkpoint": None}, {"number": 2, "choice_ids": ["C2"], "asked_at": NOW, "checkpoint": None}]
        self.assert_invalid(contract, "dependency must be earlier confirmed choice")

    def test_round_four_checkpoint_and_no_round_count_cap(self):
        contract = base_contract(alignment="exploring", handoff="not_requested", session="active", with_reviews=False)
        for i in range(2, 6):
            contract["choices"].append(choice(f"C{i}")); contract["choices"][-1]["affected_spec_ids"] = []; contract["choices"][-1]["affected_acceptance_ids"] = []; contract["choices"][-1]["affected_unit_ids"] = []
        contract["question_rounds"] = [{"number": i, "choice_ids": [f"C{i}"], "asked_at": NOW, "checkpoint": None} for i in range(1, 5)]
        self.assert_invalid(contract, "checkpoint required every 4th round")
        contract["question_rounds"][3]["checkpoint"] = {"confirmed_choice_ids": ["C1", "C2", "C3", "C4"], "unresolved_choice_ids": [], "affected_spec_ids": ["S1"], "next_question_choice_ids": [], "recorded_at": NOW}
        contract["question_rounds"].append({"number": 5, "choice_ids": ["C5"], "asked_at": NOW, "checkpoint": None})
        self.assert_valid(contract, alignment="exploring", handoff="not_requested", session="active")

    def test_cycle_order_unknown_dependency_and_orphan_graph(self):
        contract = base_contract(); contract["implementation_units"][0]["dependency_unit_ids"] = ["U1"]
        self.assert_invalid(contract, "self dependency")
        contract = base_contract(); contract["implementation_units"].append(unit(uid="U2", deps=["U1"], order=2)); contract["implementation_units"][0]["dependency_unit_ids"] = ["U2"]; contract["choices"][0]["affected_unit_ids"] = ["U1", "U2"]; refresh(contract)
        self.assert_invalid(contract, "implementation unit dependency cycle")
        contract = base_contract(); contract["implementation_units"][0]["dependency_unit_ids"] = ["U2"]
        self.assert_invalid(contract, "references unknown ID U2")
        contract = base_contract(); contract["implementation_units"][0]["spec_ids"] = []; contract["implementation_units"][0]["acceptance_ids"] = []; contract["choices"][0]["affected_spec_ids"] = []; contract["choices"][0]["affected_acceptance_ids"] = []; contract["choices"][0]["affected_unit_ids"] = []
        self.assert_invalid(contract, "graph orphan remains", require="handoff-ready")

    def test_stale_spec_repository_receipts_and_findings(self):
        contract = base_contract(); contract["goal"]["statement"] = "Changed goal invalidates receipts."
        output = self.assert_invalid(contract, require="aligned"); self.assertIn("ambiguity_auditor:spec_digest", output["stale_receipts"])
        contract = base_contract(); contract["repository_context"]["entries"][0]["locator"] = "HEAD~1"
        output = self.assert_invalid(contract, require="aligned"); self.assertIn("ambiguity_auditor:repository_context_digest", output["stale_receipts"])
        contract = base_contract(); contract["reviews"]["ambiguity_auditor"]["status"] = "findings"; contract["reviews"]["ambiguity_auditor"]["output"]["new_material_choices"] = ["timeout is unspecified"]; rebind(contract)
        self.assert_valid(contract, alignment="exploring", handoff="not_requested", session="active"); output = self.assert_invalid(contract, "fresh ambiguity auditor PASS required", require="aligned"); self.assertEqual(output["next_action"], "resolve_findings")

    def test_cold_blockers_unmapped_and_local_choice_proof(self):
        for key in ("implicit_assumptions", "required_user_choices", "contradictions", "underspecified_clauses", "unmapped_spec_ids"):
            with self.subTest(key=key):
                contract = base_contract(); contract["reviews"]["cold_consumer"]["output"][key] = ["blocker"]; rebind(contract)
                output = self.assert_invalid(contract, "cold consumer blocker", require="handoff-ready"); self.assertEqual(output["next_action"], "resolve_findings")
        local = {"id": "LC1", "description": "private helper inline or split", "unit_id": "U1"}
        for key in ("same_observable_behavior", "unchanged_named_surfaces", "no_system_impact", "private_unit_only", "reversible_without_spec_change"):
            local[key] = {"satisfied": True, "evidence": "The proof is recorded for this private unit."}
        contract = base_contract(); contract["reviews"]["cold_consumer"]["output"]["local_choices"] = [local]; rebind(contract)
        self.assert_valid(contract, "handoff-ready")
        incomplete = copy.deepcopy(contract); del incomplete["reviews"]["cold_consumer"]["output"]["local_choices"][0]["private_unit_only"]; self.assert_invalid(incomplete, "local_choices[0] missing", require="handoff-ready")

    def test_confirmation_distinct_order_and_staleness(self):
        contract = base_contract(); contract["confirmations"]["handoff_document"]["confirmation_id"] = "UC1"
        self.assert_invalid(contract, "duplicate confirmation ID", require="handoff-ready")
        contract = base_contract(); contract["confirmations"]["handoff_document"]["confirmed_at"] = "2026-08-31T09:05:00+09:00"
        self.assert_invalid(contract, "after alignment_summary", require="handoff-ready")
        contract = base_contract(); contract["reviews"]["cold_consumer"]["generated_at"] = "2026-08-31T09:35:00+09:00"; rebind(contract); contract["confirmations"]["handoff_document"]["confirmed_at"] = "2026-08-31T09:30:00+09:00"
        self.assert_invalid(contract, "follow cold_consumer receipt", require="handoff-ready")
        contract = base_contract(); contract["confirmations"]["handoff_document"] = None
        self.assert_invalid(contract, "fresh handoff confirmation required", require="handoff-ready")
        contract = base_contract(); contract["reviews"]["ambiguity_auditor"]["generated_at"] = LATER
        output = self.assert_invalid(contract, "fresh alignment summary confirmation required", require="aligned")
        self.assertNotIn("ambiguity_auditor:spec_digest", output["stale_receipts"]); self.assertIn("alignment_summary:ambiguity_receipt_digest", output["stale_receipts"])

    def test_complete_requires_relevant_gate_even_when_structurally_parseable(self):
        decision = base_contract(target="decision", handoff="not_requested")
        decision["implementation_units"] = []
        refresh(decision, include_cold=False, include_handoff=False)
        output = self.assert_valid(decision, alignment="exploring", handoff="not_requested", session="active")
        self.assertNotEqual(output["next_action"], "complete")
        broken = document(decision, alignment="aligned", handoff="not_requested", session="complete").replace("title: Canonical fixture", "title:")
        output = self.assert_invalid_text(broken)
        self.assertNotEqual(output["next_action"], "complete")

    def test_repository_context_and_fact_failures_block_gates(self):
        for mutation in ("empty_entries", "null_digest"):
            with self.subTest(mutation=mutation):
                contract = base_contract()
                if mutation == "empty_entries":
                    contract["repository_context"]["entries"] = []
                else:
                    contract["repository_context"]["entries"][0]["digest"] = None
                rebind(contract)
                output = self.assert_invalid(contract, "usable repository context", require="handoff-ready")
                self.assertEqual(output["next_action"], "research_facts")

    def test_required_goal_choice_and_policy_text_arrays_are_nonempty(self):
        for key in ("success", "failure", "non_goals"):
            with self.subTest(goal=key):
                contract = base_contract(); contract["goal"][key] = []
                self.assert_invalid(contract, "must be nonempty array")
        for key in ("scope", "consequences"):
            with self.subTest(choice=key):
                contract = base_contract(); contract["choices"][0][key] = []
                self.assert_invalid(contract, "must be nonempty array")
        contract = base_contract(); contract["choices"][0]["choice_kind"] = "policy"; contract["choices"][0]["policy_targets"] = [""]
        self.assert_invalid(contract, "policy_targets[0] must be nonempty string")

    def test_planner_placeholder_and_assumption_coverage_excludes_observations(self):
        mutations = (
            lambda c: c["decision_surfaces"][0].__setitem__("reason", "TODO classify this surface"),
            lambda c: c["choices"][0].__setitem__("question", "Assumption: choose the current format"),
            lambda c: c["choices"][0]["recommendation"].__setitem__("rationale", "TODO justify this recommendation"),
            lambda c: c["acceptance_checks"][0].__setitem__("pass_condition", "Assumption: the output is correct"),
            lambda c: c["implementation_units"][0].__setitem__("title", "TODO implementation unit"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                contract = base_contract(); mutate(contract); rebind(contract)
                self.assert_invalid(contract, "planner-authored placeholder or assumption")
        contract = base_contract(); contract["facts"][0]["observation"] = "The observed source literally contains the word assumption."
        rebind(contract)
        self.assert_valid(contract, "handoff-ready")

    def test_performance_spec_requires_nonfunctional_measured_acceptance(self):
        contract = base_contract(); contract["specifications"][0]["kind"] = "performance"; rebind(contract)
        self.assert_invalid(contract, "requires nonfunctional measured acceptance", require="handoff-ready")
        contract["acceptance_checks"][0]["acceptance_type"] = "non_functional"
        contract["acceptance_checks"][0]["measurement"] = {"metric": "p95 latency", "threshold": "at most 100 ms", "conditions": "100 warm runs", "method": "record monotonic elapsed time"}
        rebind(contract)
        self.assert_valid(contract, "handoff-ready")

    def test_vague_supersession_and_superseded_surface_are_rejected(self):
        contract = superseded_contract(supersession_response="you choose")
        self.assert_invalid(contract, "vague supersession response")
        contract = superseded_contract(surface_uses_old=True)
        self.assert_invalid(contract, "superseded choice cannot govern current surface")

    def test_every_spec_requires_acceptance_for_decision_target(self):
        contract = base_contract(target="decision", handoff="not_requested")
        contract["implementation_units"] = []
        contract["acceptance_checks"] = []
        contract["choices"][0]["affected_acceptance_ids"] = []
        refresh(contract, include_cold=False, include_handoff=False)
        output = self.assert_invalid(contract, "requires an acceptance check", require="aligned")
        self.assertIn("S1", output["unverified_spec_ids"])

    def test_cold_steps_require_nonempty_consistent_s_a_u_mapping(self):
        contract = base_contract(); contract["reviews"]["cold_consumer"]["output"]["steps"].append({"step": "Unmapped extra step.", "spec_ids": [], "acceptance_ids": [], "unit_ids": []}); rebind(contract)
        self.assert_invalid(contract, "must map nonempty S/A/U", require="handoff-ready")

        contract = base_contract()
        s2 = copy.deepcopy(contract["specifications"][0]); s2["id"] = "S2"
        a2 = copy.deepcopy(contract["acceptance_checks"][0]); a2["id"] = "A2"; a2["spec_ids"] = ["S2"]
        u2 = unit(uid="U2", specs=["S2"], accepts=["A2"], order=2)
        contract["specifications"].append(s2); contract["acceptance_checks"].append(a2); contract["implementation_units"].append(u2)
        contract["choices"][0]["affected_spec_ids"] = ["S1", "S2"]
        contract["choices"][0]["affected_acceptance_ids"] = ["A1", "A2"]
        contract["choices"][0]["affected_unit_ids"] = ["U1", "U2"]
        refresh(contract)
        contract["reviews"]["cold_consumer"]["output"]["steps"] = [
            {"step": "Cross-owned first step.", "spec_ids": ["S1"], "acceptance_ids": ["A1"], "unit_ids": ["U2"]},
            {"step": "Cross-owned second step.", "spec_ids": ["S2"], "acceptance_ids": ["A2"], "unit_ids": ["U1"]},
        ]
        rebind(contract)
        self.assert_invalid(contract, "unit ownership is inconsistent", require="handoff-ready")

    def test_review_confirmation_ids_and_strict_temporal_order(self):
        contract = base_contract(); contract["reviews"]["cold_consumer"]["review_id"] = "R1"; contract["confirmations"]["handoff_document"]["cold_review_id"] = "R1"; rebind(contract)
        self.assert_invalid(contract, "duplicate review ID", require="handoff-ready")
        contract = base_contract(); contract["reviews"]["ambiguity_auditor"]["review_id"] = "review-one"; contract["confirmations"]["alignment_summary"]["ambiguity_review_id"] = "review-one"; contract["confirmations"]["handoff_document"]["ambiguity_review_id"] = "review-one"; rebind(contract)
        self.assert_invalid(contract, "review_id must match RN")
        contract = base_contract(); contract["confirmations"]["alignment_summary"]["confirmation_id"] = "confirmation-one"
        self.assert_invalid(contract, "confirmation_id must match UCN")
        contract = base_contract(); contract["confirmations"]["alignment_summary"]["confirmed_at"] = "2026-08-31T09:05:00+09:00"
        self.assert_invalid(contract, "after ambiguity_auditor receipt", require="aligned")
        contract = base_contract(); contract["reviews"]["cold_consumer"]["generated_at"] = contract["confirmations"]["handoff_document"]["confirmed_at"]; rebind(contract)
        self.assert_invalid(contract, "follow cold_consumer receipt", require="handoff-ready")

    def test_open_research_and_external_dependency_next_actions(self):
        contract = base_contract(); contract["open_items"] = [{"id": "O1", "kind": "research", "description": "Inspect runtime behavior.", "blocking_ids": ["S1"], "status": "open", "resolution": None}]; refresh(contract)
        self.assertEqual(self.assert_invalid(contract, require="aligned")["next_action"], "research_facts")
        contract["open_items"][0]["kind"] = "external_dependency"; contract["open_items"][0]["description"] = "Wait for the external schema owner."; refresh(contract)
        self.assertEqual(self.assert_invalid(contract, require="aligned")["next_action"], "pause")

    def test_malformed_nested_types_never_traceback(self):
        mutations = (
            lambda c: c.__setitem__("goal", None),
            lambda c: c["repository_context"]["entries"][0].__setitem__("kind", []),
            lambda c: c["choices"][0].__setitem__("policy_targets", None),
            lambda c: c["question_rounds"][0].__setitem__("choice_ids", None),
            lambda c: c["decision_surfaces"][0]["resolution"].__setitem__("choice_ids", None),
            lambda c: c["specifications"][0].__setitem__("provenance", None),
            lambda c: c["implementation_units"][0].__setitem__("acceptance_ids", None),
            lambda c: c["reviews"]["cold_consumer"].__setitem__("output", None),
            lambda c: c["confirmations"].__setitem__("alignment_summary", True),
            lambda c: c["reviews"]["cold_consumer"].__setitem__("generated_at", None),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                contract = base_contract(); mutate(contract)
                result = self.result(contract, "handoff-ready")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(set(json.loads(result.stdout)), OUTPUT_KEYS)

    def test_claimed_gate_states_and_decision_units(self):
        contract = exploring_contract(); self.assert_invalid_text(document(contract, alignment="aligned", handoff="not_requested", session="complete"), "unresolved choices remain")
        contract = exploring_contract(); self.assert_invalid_text(document(contract, alignment="aligned", handoff="ready", session="complete"), "handoff-ready requires nonempty S/A/U")
        contract = base_contract(target="decision", handoff="not_requested"); contract["implementation_units"] = [unit()]; contract["choices"][0]["affected_unit_ids"] = ["U1"]; refresh(contract, include_cold=False, include_handoff=False)
        self.assert_invalid(contract, "decision target implementation_units must be empty")

    def test_next_action_precedence_vocabulary_and_pause(self):
        self.assertEqual(self.assert_valid(exploring_contract())["next_action"], "map_choices")
        contract = exploring_contract(); contract["facts"] = []; self.assertEqual(self.assert_invalid(contract)["next_action"], "research_facts")
        contract = base_contract(with_reviews=False); contract["open_items"] = [{"id": "O1", "kind": "choice", "description": "Choose timeout.", "blocking_ids": ["S1"], "status": "open", "resolution": None}]; self.assertEqual(self.assert_invalid(contract)["next_action"], "ask_choices")
        contract = base_contract(with_reviews=False); contract["implementation_units"][0]["acceptance_ids"] = []; self.assertEqual(self.assert_invalid(contract)["next_action"], "compile_spec")
        contract = base_contract(); contract["reviews"]["ambiguity_auditor"] = None; contract["confirmations"]["alignment_summary"] = None; self.assertEqual(self.assert_invalid(contract, require="aligned")["next_action"], "run_ambiguity_audit")
        contract = base_contract(); contract["confirmations"]["alignment_summary"] = None; self.assertEqual(self.assert_invalid(contract, require="aligned")["next_action"], "request_final_confirmation")
        decision = base_contract(target="decision", handoff="not_requested"); decision["implementation_units"] = []; refresh(decision, include_cold=False, include_handoff=False); self.assertEqual(self.assert_valid(decision, require="aligned")["next_action"], "complete")
        contract = base_contract(); contract["reviews"]["cold_consumer"] = None; contract["confirmations"]["handoff_document"] = None; refresh(contract, include_cold=False, include_handoff=False); self.assertEqual(self.assert_invalid(contract, require="handoff-ready")["next_action"], "run_cold_consumer")
        contract = base_contract(); contract["reviews"]["cold_consumer"]["output"]["implicit_assumptions"] = ["timeout"]; self.assertEqual(self.assert_invalid(contract, require="handoff-ready")["next_action"], "resolve_findings")
        contract = exploring_contract(); self.assertEqual(self.assert_valid(contract, session="paused")["next_action"], "pause")

    def test_json_required_fields_and_cli_exit_codes(self):
        output = self.assert_valid(base_contract()); self.assertEqual(set(output), OUTPUT_KEYS)
        missing = subprocess.run([sys.executable, "-B", str(VALIDATOR), "/path/does/not/exist.md", "--json"], capture_output=True, text=True); self.assertEqual(missing.returncode, 2); self.assertEqual(set(json.loads(missing.stdout)), OUTPUT_KEYS)
        usage = subprocess.run([sys.executable, "-B", str(VALIDATOR), "--unknown", "--json"], capture_output=True, text=True); self.assertEqual(usage.returncode, 2); self.assertEqual(set(json.loads(usage.stdout)), OUTPUT_KEYS)
        no_path = subprocess.run([sys.executable, "-B", str(VALIDATOR), "--json"], capture_output=True, text=True); self.assertEqual(no_path.returncode, 2); self.assertEqual(set(json.loads(no_path.stdout)), OUTPUT_KEYS)
        invalid = self.run_doc(document(exploring_contract()).replace("title: Canonical fixture", "title:")); self.assertEqual(invalid.returncode, 1)
        malformed = self.run_doc(document_with_raw_json(base_contract(), "{")); self.assertEqual(malformed.returncode, 1); self.assertEqual(set(json.loads(malformed.stdout)), OUTPUT_KEYS)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "goal.md"; path.write_text(document(exploring_contract()), encoding="utf-8")
            plain = subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path)], capture_output=True, text=True)
            self.assertEqual(plain.returncode, 0, plain.stdout + plain.stderr); self.assertIn("next_action: map_choices", plain.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

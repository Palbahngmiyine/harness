#!/usr/bin/env python3
"""Deterministic contract/receipt tests for align-goal's structural validator.

Fixtures use the production ``spec_projection``/digest implementation and the
production response-log chain hash, so every confirmed choice in a fixture is
bound to a hash-chained log entry exactly as a real session would be. The
dialogue and recursive-discovery evaluations remain in the reference document.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "validate_goal_spec.py"
sys.path.insert(0, str(HERE))
import record_response as record  # noqa: E402
import validate_goal_spec as validator  # noqa: E402

NOW = "2026-08-31T09:00:00+09:00"
T_SUP = "2026-08-31T09:05:00+09:00"
T_ALIGN = "2026-08-31T09:25:00+09:00"
LATER = "2026-08-31T09:30:00+09:00"
ALIGN_TEXT = "CONFIRM ALIGNMENT: The summary exactly reflects my individual answers."
HANDOFF_TEXT = "CONFIRM HANDOFF: I approve this handoff document for implementation."
SURFACES = list(validator.SURFACES)
OUTPUT_KEYS = {
    "valid", "require", "next_action", "errors", "unresolved_choice_ids",
    "uncovered_surfaces", "untraced_spec_ids", "unverified_spec_ids",
    "graph_cycles", "graph_orphans", "stale_receipts", "spec_digest",
    "repository_context_digest", "substance", "observation", "context_drift",
    "unobserved_context", "response_log", "stamped",
}
FENCE = "`" * 3
PROJECTION_KEYS = (
    "contract_version", "revision", "target", "goal", "facts", "choices",
    "question_rounds", "decision_surfaces", "specifications", "acceptance_checks",
    "implementation_units", "open_items",
)


def digest(value):
    """Use the validator's canonical JSON/digest implementation."""

    return validator.dg(value)


def make_log(pairs):
    """Build hash-chained response log entries from (text, at) pairs."""

    entries = []
    previous = None
    for seq, (text_value, at) in enumerate(pairs, 1):
        entry = {"seq": seq, "at": at, "text": text_value, "prev": previous}
        entry["hash"] = record.chain_hash(entry)
        entries.append(entry)
        previous = entry["hash"]
    return entries


def extend_log(entries, pairs):
    previous = entries[-1]["hash"] if entries else None
    for text_value, at in pairs:
        entry = {"seq": len(entries) + 1, "at": at, "text": text_value, "prev": previous}
        entry["hash"] = record.chain_hash(entry)
        entries.append(entry)
        previous = entry["hash"]
    return entries


def ref(entries, seq):
    return {"seq": seq, "hash": entries[seq - 1]["hash"]}


def wire_log(c):
    """Rebuild the response log for every logged response, in dialogue order.

    Choice answers first, then supersessions, then confirmations; each slot's
    response_ref is rewired to its entry. Returns the entries and stashes them
    on the contract under "_log" (stripped before serialization)."""

    rows = []
    for row in c.get("choices", []):
        u = row.get("user_response")
        if isinstance(u, dict):
            rows.append((u.get("confirmed_at"), len(rows), u.get("exact"), u))
    for row in c.get("choices", []):
        s = row.get("supersession")
        if isinstance(s, dict):
            rows.append((s.get("confirmed_at"), len(rows), s.get("exact_user_response"), s))
    for kind in ("alignment_summary", "handoff_document"):
        r = c.get("confirmations", {}).get(kind) if isinstance(c.get("confirmations"), dict) else None
        if isinstance(r, dict):
            rows.append((r.get("confirmed_at"), len(rows), r.get("exact_response"), r))
    rows.sort(key=lambda item: (item[0] if isinstance(item[0], str) else "", item[1]))
    entries = make_log([(text_value, at) for at, _, text_value, _ in rows])
    for seq, (_, _, _, slot) in enumerate(rows, 1):
        slot["response_ref"] = ref(entries, seq)
    c["_log"] = entries
    return entries


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
    selected = status in {"confirmed", "superseded", "reask"}
    return {
        "id": cid,
        "question": "Which exact public contract value should be implemented?",
        "alternatives": [
            {"id": "ALT1", "value": "keep the canonical contract", "outcome_delta": "Keeps the documented contract value.", "origin": "llm"},
            {"id": "ALT2", "value": "change the contract value", "outcome_delta": "Changes the observable contract.", "origin": "llm"},
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
            "exact": f"{cid}=ALT1", "confirmed_at": NOW,
        } if selected else None),
        "confirmed_alternative_id": "ALT1" if selected else None,
        "confirmed_value": "keep the canonical contract" if selected else None,
        "scope": ["the requested goal and its implementation handoff"],
        "consequences": ["The exact public contract remains stable."],
        "affected_spec_ids": list(affected_specs or []),
        "affected_acceptance_ids": list(affected_acceptance or []),
        "affected_unit_ids": list(affected_units or []),
        "status": status,
        "reask_reason": "The cold consumer reopened this choice." if status == "reask" else None,
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
    else:
        wire_log(c)
    return c


def refresh(c, *, include_cold=True, include_handoff=True):
    """Wire the response log, then create fresh receipts and confirmations."""

    c["confirmations"] = {"alignment_summary": None, "handoff_document": None}
    wire_log(c)
    spec_digest = digest({key: c[key] for key in PROJECTION_KEYS})
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
    entries = c["_log"]
    alignment = {
        "confirmation_id": "UC1", "exact_response": ALIGN_TEXT,
        "confirmed_at": T_ALIGN,
        "spec_digest": spec_digest, "repository_context_digest": repo_digest,
        "ambiguity_review_id": "R1", "ambiguity_receipt_digest": digest(ambiguity),
    }
    extend_log(entries, [(ALIGN_TEXT, T_ALIGN)])
    alignment["response_ref"] = ref(entries, len(entries))
    handoff = None
    if include_handoff:
        cold = reviews["cold_consumer"]
        handoff = {**alignment, "confirmation_id": "UC2", "exact_response": HANDOFF_TEXT,
                   "confirmed_at": LATER, "cold_review_id": "R2", "cold_receipt_digest": digest(cold)}
        extend_log(entries, [(HANDOFF_TEXT, LATER)])
        handoff["response_ref"] = ref(entries, len(entries))
    c["confirmations"] = {"alignment_summary": alignment, "handoff_document": handoff}


def rebind(c, *, rewire=True):
    """Rebind receipts (and by default the response log) after mutations."""

    if rewire:
        wire_log(c)
    spec_digest = digest({key: c[key] for key in PROJECTION_KEYS})
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
    wire_log(c)
    return c


def superseded_contract(*, surface_uses_old=False, supersession_response="C1 is superseded by C2."):
    c = base_contract(with_reviews=False)
    c["choices"].append(choice("C2", affected_specs=["S1"], affected_acceptance=["A1"], affected_units=["U1"]))
    old = c["choices"][0]
    old["status"] = "superseded"
    old["affected_spec_ids"] = []
    old["affected_acceptance_ids"] = []
    old["affected_unit_ids"] = []
    old["supersession"] = {
        "exact_user_response": supersession_response,
        "confirmed_at": T_SUP,
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
        "response_log": "goal.responses.jsonl",
    }
    payload = {key: value for key, value in contract.items() if key != "_log"}
    front_text = "\n".join(f"{key}: {value}" for key, value in front.items())
    return f"---\n{front_text}\n---\n\n# Projection\n\nThis prose may mention an assumption without changing canonical semantics.\n\n{FENCE}json align-goal-contract\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n{FENCE}\n"


def document_with_raw_json(contract, raw_json, **kwargs):
    rendered = document(contract, **kwargs)
    marker = FENCE + "json align-goal-contract\n"
    start = rendered.index(marker) + len(marker)
    end = rendered.index("\n" + FENCE, start)
    return rendered[:start] + raw_json + rendered[end:]


class ValidatorTests(unittest.TestCase):
    maxDiff = None

    def run_doc(self, text, log=None, require="structural", extra_args=()):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "goal.md"
            path.write_text(text, encoding="utf-8")
            log_path = Path(directory) / "goal.responses.jsonl"
            lines = "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in (log or []))
            log_path.write_text(lines, encoding="utf-8")
            args = [sys.executable, "-B", str(VALIDATOR), str(path), "--require", require, "--json"]
            if "--no-observe" not in extra_args and "--repo-root" not in extra_args:
                args.append("--no-observe")
            args += list(extra_args)
            return subprocess.run(args, capture_output=True, text=True)

    def result(self, contract, require="structural", **kwargs):
        return self.run_doc(document(contract, **kwargs), contract.get("_log"), require)

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

    def assert_invalid_text(self, text, needle=None, require="structural", log=None):
        result = self.run_doc(text, log, require)
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
        log = contract["_log"]
        text = document(contract).replace("updated: " + NOW + "\n", "updated: " + NOW + "\nextra: x\n")
        self.assert_invalid_text(text, "frontmatter keys must be exactly", log=log)
        no_fence = document(contract).replace(FENCE + "json align-goal-contract\n", "").replace("\n" + FENCE + "\n", "\n")
        self.assert_invalid_text(no_fence, "exactly one", log=log)
        two_fences = document(contract) + "\n" + document(contract)[document(contract).index(FENCE + "json align-goal-contract\n"):]
        self.assert_invalid_text(two_fences, "exactly one", log=log)
        unsafe = document(contract).replace("response_log: goal.responses.jsonl", "response_log: ../outside.jsonl")
        self.assert_invalid_text(unsafe, "safe relative path", log=log)

    def test_duplicate_json_key_nan_alias_and_top_level_keys(self):
        contract = base_contract()
        log = contract["_log"]
        raw = json.dumps({k: v for k, v in contract.items() if k != "_log"}, ensure_ascii=False, indent=2)
        raw = raw.replace('"target": "implementation",', '"target": "implementation",\n  "target": "implementation",', 1)
        self.assert_invalid_text(document_with_raw_json(contract, raw), "duplicate JSON key", log=log)
        nan_raw = raw.replace('"target": "implementation",\n  "target": "implementation",', '"target": "implementation",', 1).replace('"revision": 1,', '"revision": NaN,', 1)
        self.assert_invalid_text(document_with_raw_json(contract, nan_raw), "non-standard JSON constant", log=log)
        contract = base_contract(); contract["next_action"] = "complete"
        self.assert_invalid(contract, "unexpected top-level keys")
        contract = base_contract(); contract["spec_digest"] = digest({"probe": True})
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
        wire_log(contract)
        self.assert_valid(contract, alignment="exploring", handoff="not_requested", session="active")
        contract["choices"][1]["confirmed_value"] = "keep the canonical contract"
        self.assert_invalid(contract, "candidate/asked confirmation fields must be null")
        contract = base_contract(); contract["choices"][0]["user_response"] = None
        self.assert_invalid(contract, "user_response required")
        contract = base_contract(); contract["choices"][0]["confirmed_value"] = "a different exact value"
        self.assert_invalid(contract, "confirmed_value must equal selected alternative.value")

    def test_grammar_rejects_delegated_and_free_form_confirmations(self):
        # The C<n>=<answer> grammar, not a phrase denylist, is what rejects
        # delegated/free-form replies: legitimate concrete values like
        # "follow the repository's snake_case convention" must remain recordable.
        for phrase in ("ok", "네", "1", "추천대로", "알아서 해줘", "니가 정해", "whatever you think", "go with your recommendation"):
            with self.subTest(phrase=phrase):
                contract = base_contract()
                contract["choices"][0]["user_response"]["exact"] = phrase
                rebind(contract)
                output = self.assert_invalid(contract)
                self.assertTrue(any("grammar" in e for e in output["errors"]), output["errors"])
        contract = base_contract()
        contract["choices"][0]["user_response"]["exact"] = "C1=ALT2"
        rebind(contract)
        self.assert_invalid(contract, "does not select the confirmed alternative exactly")
        contract = base_contract()
        contract["choices"][0]["user_response"]["exact"] = "C2=ALT1"
        rebind(contract)
        self.assert_invalid(contract, "must target choice C1")
        # A concrete "follow the repo convention" value is no longer blocked.
        contract = base_contract()
        contract["choices"][0]["alternatives"].append(
            {"id": "ALT3", "value": "follow the repository's existing snake_case convention", "outcome_delta": "Adopts the existing convention.", "origin": "user"})
        contract["choices"][0]["confirmed_alternative_id"] = "ALT3"
        contract["choices"][0]["confirmed_value"] = "follow the repository's existing snake_case convention"
        contract["choices"][0]["user_response"] = {"exact": "C1=OTHER: follow the repository's existing snake_case convention", "confirmed_at": NOW}
        refresh(contract)
        self.assert_valid(contract, "handoff-ready")

    def same_chain_contract(self, log_texts, alt_id, value, ref_seq, extra_alternatives=()):
        """A handoff-ready contract whose C1 is confirmed by log entry ref_seq."""
        contract = base_contract()
        for alternative in extra_alternatives:
            contract["choices"][0]["alternatives"].append(alternative)
        entries = make_log([(log_texts[0], NOW)])
        for index, text_value in enumerate(log_texts[1:], 1):
            extend_log(entries, [(text_value, f"2026-08-31T09:0{index}:00+09:00")])
        contract["choices"][0]["confirmed_alternative_id"] = alt_id
        contract["choices"][0]["confirmed_value"] = value
        contract["choices"][0]["user_response"] = {
            "exact": log_texts[ref_seq - 1],
            "confirmed_at": entries[ref_seq - 1]["at"],
            "response_ref": ref(entries, ref_seq),
        }
        contract["_log"] = entries
        rebind(contract, rewire=False)
        for kind in ("alignment_summary", "handoff_document"):
            confirmation = contract["confirmations"][kind]
            extend_log(entries, [(confirmation["exact_response"], confirmation["confirmed_at"])])
            confirmation["response_ref"] = ref(entries, len(entries))
        rebind(contract, rewire=False)
        return contract

    def test_same_chain_binds_to_its_latest_antecedent(self):
        keep, change = "keep the canonical contract", "change the contract value"
        user_alt = {"id": "ALT3", "value": "custom-value", "outcome_delta": "User supplied.", "origin": "user"}
        cases = (
            ("chained SAME forging the opposite alternative", ["C1=ALT1", "C1=SAME", "C1=SAME"], "ALT2", change, 3, (), True),
            ("chained SAME re-affirming the antecedent", ["C1=ALT1", "C1=SAME", "C1=SAME"], "ALT1", keep, 3, (), False),
            ("SAME must track the LATEST explicit answer", ["C1=ALT1", "C1=ALT2", "C1=SAME"], "ALT1", keep, 3, (), True),
            ("SAME tracking the latest explicit answer", ["C1=ALT1", "C1=ALT2", "C1=SAME"], "ALT2", change, 3, (), False),
            ("another choice's answer is not an antecedent", ["C2=ALT1", "C1=SAME"], "ALT1", keep, 2, (), True),
            ("SAME after OTHER keeps the OTHER value", ["C1=OTHER: custom-value", "C1=SAME"], "ALT3", "custom-value", 2, (user_alt,), False),
            ("SAME after OTHER cannot switch alternatives", ["C1=OTHER: custom-value", "C1=SAME"], "ALT1", keep, 2, (user_alt,), True),
            ("multi-segment antecedent is honoured", ["C1=ALT1; C9=ALT1", "C1=SAME"], "ALT1", keep, 2, (), False),
            ("multi-segment antecedent cannot be forged", ["C1=ALT1; C9=ALT1", "C1=SAME"], "ALT2", change, 2, (), True),
        )
        for label, texts, alt_id, value, seq, extra, blocked in cases:
            with self.subTest(case=label):
                contract = self.same_chain_contract(texts, alt_id, value, seq, extra)
                if blocked:
                    self.assert_invalid(contract, require="handoff-ready")
                else:
                    self.assert_valid(contract, "handoff-ready")

    def test_same_cannot_rebind_to_a_different_alternative(self):
        # Regression: C<n>=SAME must re-affirm the antecedent's alternative; it
        # cannot silently ship the opposite alternative or an un-introduced value.
        contract = base_contract()
        entries = make_log([("C1=ALT1", NOW)])
        extend_log(entries, [("C1=SAME", "2026-08-31T09:02:00+09:00")])
        contract["choices"][0]["confirmed_alternative_id"] = "ALT2"
        contract["choices"][0]["confirmed_value"] = "change the contract value"
        contract["choices"][0]["user_response"] = {"exact": "C1=SAME", "confirmed_at": "2026-08-31T09:02:00+09:00", "response_ref": ref(entries, 2)}
        contract["_log"] = entries
        rebind(contract, rewire=False)
        # receipts were wired for ALT2; the log only supports SAME->ALT1.
        for kind in ("alignment_summary", "handoff_document"):
            r = contract["confirmations"][kind]
            extend_log(entries, [(r["exact_response"], r["confirmed_at"])])
            r["response_ref"] = ref(entries, len(entries))
        rebind(contract, rewire=False)
        self.assert_invalid(contract, "SAME must re-affirm the same alternative", require="handoff-ready")
        # Honest SAME->ALT1 with the recorded alternative matching the antecedent passes.
        contract["choices"][0]["confirmed_alternative_id"] = "ALT1"
        contract["choices"][0]["confirmed_value"] = "keep the canonical contract"
        rebind(contract, rewire=False)
        self.assert_valid(contract, "handoff-ready")

    def test_response_log_binding_rejects_forged_or_missing_evidence(self):
        contract = base_contract()
        contract["choices"][0]["user_response"]["response_ref"]["hash"] = "sha256:" + "9" * 64
        self.assert_invalid(contract, "response_ref hash mismatch")
        contract = base_contract()
        contract["choices"][0]["user_response"]["response_ref"]["seq"] = 99
        self.assert_invalid(contract, "response log entry missing for seq 99")
        contract = base_contract()
        contract["_log"][0]["text"] = "C1=ALT2"
        self.assert_invalid(contract, "response log:")
        contract = base_contract()
        contract["choices"][0]["user_response"]["confirmed_at"] = "2026-08-31T09:01:00+09:00"
        self.assert_invalid(contract, "must equal response log entry time")
        contract = base_contract()
        result = self.run_doc(document(contract), [], "structural")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("response log entry missing", result.stdout)

    def test_other_flow_binds_user_origin_alternatives(self):
        contract = base_contract()
        contract["choices"][0]["alternatives"].append(
            {"id": "ALT3", "value": "custom-value", "outcome_delta": "Uses the user-supplied value.", "origin": "user"})
        contract["choices"][0]["confirmed_alternative_id"] = "ALT3"
        contract["choices"][0]["confirmed_value"] = "custom-value"
        contract["choices"][0]["user_response"] = {"exact": "C1=OTHER: custom-value", "confirmed_at": NOW}
        refresh(contract)
        self.assert_valid(contract, "handoff-ready")
        broken = copy.deepcopy(contract)
        broken["choices"][0]["alternatives"][2]["origin"] = "llm"
        rebind(broken, rewire=False)
        self.assert_invalid(broken, "OTHER response requires a user-origin alternative")
        unintroduced = copy.deepcopy(contract)
        unintroduced["choices"][0]["user_response"] = {"exact": "C1=ALT3", "confirmed_at": NOW}
        refresh(unintroduced)
        self.assert_invalid(unintroduced, "requires an earlier OTHER response")

    def test_same_requires_prior_explicit_answer_and_reask_blocks_gates(self):
        contract = base_contract()
        contract["choices"][0]["user_response"]["exact"] = "C1=SAME"
        rebind(contract)
        self.assert_invalid(contract, "SAME requires an earlier explicit logged response")
        contract = base_contract(with_reviews=False)
        contract["choices"][0]["status"] = "reask"
        contract["choices"][0]["reask_reason"] = "The cold consumer reopened this choice."
        wire_log(contract)
        output = self.assert_valid(contract, alignment="exploring", handoff="not_requested", session="active")
        self.assertEqual(output["next_action"], "ask_choices")
        self.assertIn("C1", output["unresolved_choice_ids"])
        self.assert_invalid_text(document(contract, alignment="aligned", handoff="not_requested", session="complete"),
                                 "unresolved choices remain", log=contract["_log"])

    def test_supersession_cascade_requires_dependent_reconfirmation(self):
        contract = superseded_contract()
        contract["choices"][1]["depends_on_choice_ids"] = ["C1"]
        rebind(contract, rewire=False)
        self.assert_invalid(contract, "must be re-confirmed after the supersession of C1")
        contract["choices"][1]["user_response"] = {"exact": "C2=ALT1", "confirmed_at": "2026-08-31T09:06:00+09:00"}
        rebind(contract)
        self.assert_valid(contract, "handoff-ready", alignment="aligned", handoff="ready", session="complete")

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
        contract = superseded_contract()
        contract["specifications"][0]["provenance"]["choice_ids"] = ["C1"]
        rebind(contract, rewire=False)
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

    def test_open_items_and_placeholder_rules(self):
        contract = base_contract(); contract["open_items"] = [{"id": "O1", "kind": "choice", "description": "A material choice remains open.", "blocking_ids": ["S1"], "status": "open", "resolution": None}]
        refresh(contract); self.assert_invalid(contract, "open items remain", require="aligned")
        contract = base_contract(); contract["specifications"][0]["statement"] = "{{TODO}} decide the contract."
        self.assert_invalid(contract, "contains placeholder")
        contract = base_contract(); contract["goal"]["statement"] = "Ship the {{DECIDE_LATER}} slice first."
        rebind(contract)
        self.assert_invalid(contract, "planner-authored placeholder: goal.statement")
        self.assert_valid(base_contract())

    def test_placeholder_reserved_sentinel_only_no_backtick_bypass_or_false_positives(self):
        # The reserved sentinel is caught even inside a code span (no bypass)...
        contract = base_contract()
        contract["specifications"][0]["statement"] = "Return the value `{{TODO: decide later}}` to the caller."
        rebind(contract)
        self.assert_invalid(contract, "contains placeholder", require="handoff-ready")
        # ...while genuine code notation, templating tokens, and prose 'todo' pass.
        for statement in (
            "The parser returns `Result<T, E>`, renders the <div> wrapper, assumes nothing about ordering, and lists 가정용 기기.",
            "Render the literal `{{username}}` and `{{ user.name }}` Jinja tokens unchanged.",
            "Persist each TODO item the user creates and mark it done; TBD is a valid task label.",
        ):
            with self.subTest(statement=statement[:32]):
                contract = base_contract()
                contract["specifications"][0]["statement"] = statement
                rebind(contract)
                self.assert_valid(contract, "handoff-ready")

    def test_nine_choices_split_and_round_dependencies(self):
        contract = base_contract(alignment="exploring", handoff="not_requested", session="active", with_reviews=False)
        for i in range(2, 10):
            contract["choices"].append(choice(f"C{i}"))
            contract["choices"][-1]["affected_spec_ids"] = []; contract["choices"][-1]["affected_acceptance_ids"] = []; contract["choices"][-1]["affected_unit_ids"] = []
        contract["question_rounds"] = [{"number": 1, "choice_ids": [f"C{i}" for i in range(1, 10)], "asked_at": NOW, "checkpoint": None}]
        wire_log(contract)
        self.assert_invalid(contract, "unique 1..8")
        contract["question_rounds"] = [{"number": 1, "choice_ids": [f"C{i}" for i in range(1, 9)], "asked_at": NOW, "checkpoint": None}, {"number": 2, "choice_ids": ["C9"], "asked_at": NOW, "checkpoint": None}]
        self.assert_valid(contract, alignment="exploring", handoff="not_requested", session="active")
        contract["question_rounds"].append({"number": 3, "choice_ids": ["C1"], "asked_at": NOW, "checkpoint": None})
        self.assert_invalid(contract, "exactly one round")
        contract = base_contract(alignment="exploring", handoff="not_requested", session="active", with_reviews=False)
        contract["choices"].append(choice("C2")); contract["choices"][1]["affected_spec_ids"] = []; contract["choices"][1]["affected_acceptance_ids"] = []; contract["choices"][1]["affected_unit_ids"] = []
        contract["choices"][0]["depends_on_choice_ids"] = ["C2"]
        contract["question_rounds"] = [{"number": 1, "choice_ids": ["C1"], "asked_at": NOW, "checkpoint": None}, {"number": 2, "choice_ids": ["C2"], "asked_at": NOW, "checkpoint": None}]
        wire_log(contract)
        self.assert_invalid(contract, "dependency must be earlier confirmed choice")

    def test_round_four_checkpoint_and_no_round_count_cap(self):
        contract = base_contract(alignment="exploring", handoff="not_requested", session="active", with_reviews=False)
        for i in range(2, 6):
            contract["choices"].append(choice(f"C{i}")); contract["choices"][-1]["affected_spec_ids"] = []; contract["choices"][-1]["affected_acceptance_ids"] = []; contract["choices"][-1]["affected_unit_ids"] = []
        contract["question_rounds"] = [{"number": i, "choice_ids": [f"C{i}"], "asked_at": NOW, "checkpoint": None} for i in range(1, 5)]
        wire_log(contract)
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
        contract = base_contract(); contract["repository_context"]["root"] = "/workspace/moved"
        output = self.assert_invalid(contract, require="aligned"); self.assertIn("ambiguity_auditor:repository_context_digest", output["stale_receipts"])
        contract = base_contract(); contract["reviews"]["ambiguity_auditor"]["status"] = "findings"; contract["reviews"]["ambiguity_auditor"]["output"]["new_material_choices"] = ["timeout is unspecified"]; rebind(contract, rewire=False)
        self.assert_valid(contract, alignment="exploring", handoff="not_requested", session="active"); output = self.assert_invalid(contract, "fresh ambiguity auditor PASS required", require="aligned"); self.assertEqual(output["next_action"], "resolve_findings")

    def test_cold_blockers_unmapped_and_local_choice_proof(self):
        for key in ("implicit_assumptions", "required_user_choices", "contradictions", "underspecified_clauses", "unmapped_spec_ids"):
            with self.subTest(key=key):
                contract = base_contract(); contract["reviews"]["cold_consumer"]["output"][key] = ["blocker"]; rebind(contract, rewire=False)
                output = self.assert_invalid(contract, "cold consumer blocker", require="handoff-ready"); self.assertEqual(output["next_action"], "resolve_findings")
        local = {"id": "LC1", "description": "private helper inline or split", "unit_id": "U1"}
        for key in ("same_observable_behavior", "unchanged_named_surfaces", "no_system_impact", "private_unit_only", "reversible_without_spec_change"):
            local[key] = {"satisfied": True, "evidence": "The proof is recorded for this private unit."}
        contract = base_contract(); contract["reviews"]["cold_consumer"]["output"]["local_choices"] = [local]; rebind(contract, rewire=False)
        self.assert_valid(contract, "handoff-ready")
        incomplete = copy.deepcopy(contract); del incomplete["reviews"]["cold_consumer"]["output"]["local_choices"][0]["private_unit_only"]; self.assert_invalid(incomplete, "local_choices[0] missing", require="handoff-ready")

    def test_confirmation_distinct_order_prefix_and_staleness(self):
        contract = base_contract(); contract["confirmations"]["handoff_document"]["confirmation_id"] = "UC1"
        self.assert_invalid(contract, "duplicate confirmation ID", require="handoff-ready")
        contract = base_contract(); contract["confirmations"]["handoff_document"]["confirmed_at"] = "2026-08-31T09:05:00+09:00"
        self.assert_invalid(contract, "must equal response log entry time", require="handoff-ready")
        contract = base_contract(); contract["reviews"]["cold_consumer"]["generated_at"] = "2026-08-31T09:35:00+09:00"; rebind(contract, rewire=False)
        self.assert_invalid(contract, "follow cold_consumer receipt", require="handoff-ready")
        contract = base_contract(); contract["confirmations"]["handoff_document"] = None
        self.assert_invalid(contract, "fresh handoff confirmation required", require="handoff-ready")
        contract = base_contract(); contract["reviews"]["ambiguity_auditor"]["generated_at"] = LATER
        output = self.assert_invalid(contract, "fresh alignment summary confirmation required", require="aligned")
        self.assertNotIn("ambiguity_auditor:spec_digest", output["stale_receipts"]); self.assertIn("alignment_summary:ambiguity_receipt_digest", output["stale_receipts"])
        contract = base_contract(); contract["confirmations"]["alignment_summary"]["exact_response"] = "yes, all good"
        rebind(contract)
        self.assert_invalid(contract, "must start with CONFIRM ALIGNMENT:", require="aligned")

    def test_stamp_status_replaces_false_findings_and_writes_flags(self):
        decision = base_contract(target="decision", handoff="not_requested")
        decision["implementation_units"] = []
        refresh(decision, include_cold=False, include_handoff=False)
        output = self.assert_valid(decision, alignment="exploring", handoff="not_requested", session="active")
        self.assertEqual(output["next_action"], "stamp_status")
        self.assertTrue(output["substance"]["aligned"])
        implementation = base_contract()
        output = self.assert_valid(implementation, alignment="exploring", handoff="not_requested", session="complete")
        self.assertEqual(output["next_action"], "stamp_status")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "goal.md"
            path.write_text(document(implementation, alignment="exploring", handoff="not_requested", session="complete"), encoding="utf-8")
            (Path(directory) / "goal.responses.jsonl").write_text(
                "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in implementation["_log"]), encoding="utf-8")
            run = subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path), "--require", "structural", "--json", "--no-observe", "--stamp"], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            output = json.loads(run.stdout)
            self.assertTrue(output["stamped"])
            self.assertEqual(output["next_action"], "complete")
            stamped = path.read_text(encoding="utf-8")
            self.assertIn("alignment_status: aligned", stamped)
            self.assertIn("handoff_status: ready", stamped)
            rerun = subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path), "--require", "handoff-ready", "--json", "--no-observe"], capture_output=True, text=True)
            self.assertEqual(rerun.returncode, 0, rerun.stdout + rerun.stderr)

    @unittest.skipIf(shutil.which("git") is None, "git is unavailable")
    def test_repository_observation_detects_drift_and_passes_on_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "seed"], check=True)
            head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip().lower()
            head_digest = "sha256:" + __import__("hashlib").sha256(head.encode("ascii")).hexdigest()
            (root / "observed.txt").write_text("observed content\n", encoding="utf-8")
            file_digest = "sha256:" + __import__("hashlib").sha256((root / "observed.txt").read_bytes()).hexdigest()

            contract = base_contract()
            contract["repository_context"]["entries"] = [
                {"kind": "git_head", "locator": "HEAD", "digest": head_digest},
                {"kind": "file", "locator": "observed.txt", "digest": file_digest},
            ]
            refresh(contract)
            path = root / "goal.md"
            path.write_text(document(contract), encoding="utf-8")
            (root / "goal.responses.jsonl").write_text(
                "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in contract["_log"]), encoding="utf-8")
            ok = subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path), "--require", "handoff-ready", "--json", "--repo-root", str(root)], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

            contract["repository_context"]["entries"][0]["digest"] = "sha256:" + "3" * 64
            refresh(contract)
            path.write_text(document(contract), encoding="utf-8")
            (root / "goal.responses.jsonl").write_text(
                "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in contract["_log"]), encoding="utf-8")
            drifted = subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path), "--require", "handoff-ready", "--json", "--repo-root", str(root)], capture_output=True, text=True)
            self.assertEqual(drifted.returncode, 1, drifted.stdout)
            output = json.loads(drifted.stdout)
            self.assertTrue(any("repository context drift" in e for e in output["errors"]), output["errors"])
            self.assertEqual(output["next_action"], "research_facts")

    def test_unobservable_repository_blocks_gates_unless_disabled(self):
        contract = base_contract()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "goal.md"
            path.write_text(document(contract), encoding="utf-8")
            (Path(directory) / "goal.responses.jsonl").write_text(
                "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in contract["_log"]), encoding="utf-8")
            run = subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path), "--require", "handoff-ready", "--json", "--repo-root", str(Path(directory) / "nope")], capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stdout)
            self.assertIn("unobservable", run.stdout)

    def test_complete_requires_relevant_gate_even_when_structurally_parseable(self):
        decision = base_contract(target="decision", handoff="not_requested")
        decision["implementation_units"] = []
        refresh(decision, include_cold=False, include_handoff=False)
        output = self.assert_valid(decision, alignment="exploring", handoff="not_requested", session="active")
        self.assertNotEqual(output["next_action"], "complete")
        broken = document(decision, alignment="aligned", handoff="not_requested", session="complete").replace("title: Canonical fixture", "title:")
        output = self.assert_invalid_text(broken, log=decision["_log"])
        self.assertNotEqual(output["next_action"], "complete")

    def test_repository_context_and_fact_failures_block_gates(self):
        for mutation in ("empty_entries", "null_digest"):
            with self.subTest(mutation=mutation):
                contract = base_contract()
                if mutation == "empty_entries":
                    contract["repository_context"]["entries"] = []
                else:
                    contract["repository_context"]["entries"][0]["digest"] = None
                rebind(contract, rewire=False)
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

    def test_planner_placeholder_coverage_excludes_observations(self):
        mutations = (
            lambda c: c["decision_surfaces"][0].__setitem__("reason", "{{TODO}} classify this surface"),
            lambda c: c["choices"][0].__setitem__("question", "Choose the {{DECIDE: format}} to ship"),
            lambda c: c["choices"][0]["recommendation"].__setitem__("rationale", "{{TBD}} justify this recommendation"),
            lambda c: c["acceptance_checks"][0].__setitem__("pass_condition", "[TBD] the output is correct"),
            lambda c: c["implementation_units"][0].__setitem__("title", "{{FIXME}} implementation unit"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                contract = base_contract(); mutate(contract); rebind(contract, rewire=False)
                self.assert_invalid(contract, "planner-authored placeholder")
        contract = base_contract(); contract["facts"][0]["observation"] = "The observed source literally contains a {{TODO}} marker inside TODO.md."
        rebind(contract, rewire=False)
        self.assert_valid(contract, "handoff-ready")

    def test_performance_spec_requires_nonfunctional_measured_acceptance(self):
        contract = base_contract(); contract["specifications"][0]["kind"] = "performance"; rebind(contract, rewire=False)
        self.assert_invalid(contract, "requires nonfunctional measured acceptance", require="handoff-ready")
        contract["acceptance_checks"][0]["acceptance_type"] = "non_functional"
        contract["acceptance_checks"][0]["measurement"] = {"metric": "p95 latency", "threshold": "at most 100 ms", "conditions": "100 warm runs", "method": "record monotonic elapsed time"}
        rebind(contract, rewire=False)
        self.assert_valid(contract, "handoff-ready")

    def test_superseded_surface_and_unnamed_supersession_are_rejected(self):
        contract = superseded_contract(surface_uses_old=True)
        self.assert_invalid(contract, "superseded choice cannot govern current surface")
        contract = superseded_contract(supersession_response="drop the earlier direction entirely")
        self.assert_invalid(contract, "logged response must name C1")

    def test_command_runtime_only_context_blocks_gates_when_observed(self):
        contract = base_contract()
        contract["repository_context"]["entries"] = [
            {"kind": "command", "locator": "git status", "digest": "sha256:" + "a" * 64},
            {"kind": "runtime", "locator": "python --version", "digest": "sha256:" + "b" * 64},
        ]
        refresh(contract)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "goal.md"
            path.write_text(document(contract), encoding="utf-8")
            (Path(directory) / "goal.responses.jsonl").write_text(
                "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in contract["_log"]), encoding="utf-8")
            run = subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path), "--require", "handoff-ready", "--json", "--repo-root", str(directory)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stdout)
            output = json.loads(run.stdout)
            self.assertTrue(any("no observable git_head or file entry" in e for e in output["errors"]), output["errors"])
            self.assertEqual(output["observation"], "enabled")
            # --no-observe is a documented, visible weakening: the field records it.
            weak = subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path), "--require", "handoff-ready", "--json", "--no-observe"], capture_output=True, text=True)
            self.assertEqual(weak.returncode, 0, weak.stdout)
            self.assertEqual(json.loads(weak.stdout)["observation"], "skipped")

    def test_every_spec_requires_acceptance_for_decision_target(self):
        contract = base_contract(target="decision", handoff="not_requested")
        contract["implementation_units"] = []
        contract["acceptance_checks"] = []
        contract["choices"][0]["affected_acceptance_ids"] = []
        refresh(contract, include_cold=False, include_handoff=False)
        output = self.assert_invalid(contract, "requires an acceptance check", require="aligned")
        self.assertIn("S1", output["unverified_spec_ids"])

    def test_cold_steps_require_nonempty_consistent_s_a_u_mapping(self):
        contract = base_contract(); contract["reviews"]["cold_consumer"]["output"]["steps"].append({"step": "Unmapped extra step.", "spec_ids": [], "acceptance_ids": [], "unit_ids": []}); rebind(contract, rewire=False)
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
        rebind(contract, rewire=False)
        self.assert_invalid(contract, "unit ownership is inconsistent", require="handoff-ready")

    def test_review_confirmation_ids_and_strict_temporal_order(self):
        contract = base_contract(); contract["reviews"]["cold_consumer"]["review_id"] = "R1"; contract["confirmations"]["handoff_document"]["cold_review_id"] = "R1"; rebind(contract, rewire=False)
        self.assert_invalid(contract, "duplicate review ID", require="handoff-ready")
        contract = base_contract(); contract["reviews"]["ambiguity_auditor"]["review_id"] = "review-one"; contract["confirmations"]["alignment_summary"]["ambiguity_review_id"] = "review-one"; contract["confirmations"]["handoff_document"]["ambiguity_review_id"] = "review-one"; rebind(contract, rewire=False)
        self.assert_invalid(contract, "review_id must match RN")
        contract = base_contract(); contract["confirmations"]["alignment_summary"]["confirmation_id"] = "confirmation-one"
        self.assert_invalid(contract, "confirmation_id must match UCN")
        contract = base_contract(); contract["reviews"]["cold_consumer"]["generated_at"] = contract["confirmations"]["handoff_document"]["confirmed_at"]; rebind(contract, rewire=False)
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
            lambda c: c["choices"][0].__setitem__("user_response", {"exact": [], "response_ref": 7, "confirmed_at": {}}),
            lambda c: c["question_rounds"][0].__setitem__("choice_ids", None),
            lambda c: c["decision_surfaces"][0]["resolution"].__setitem__("choice_ids", None),
            lambda c: c["specifications"][0].__setitem__("provenance", None),
            lambda c: c["implementation_units"][0].__setitem__("acceptance_ids", None),
            lambda c: c["reviews"]["cold_consumer"].__setitem__("output", None),
            lambda c: c["confirmations"].__setitem__("alignment_summary", True),
            lambda c: c["reviews"]["cold_consumer"].__setitem__("generated_at", None),
            lambda c: c["choices"][0].__setitem__("depends_on_choice_ids", [{}]),
            lambda c: c["decision_surfaces"][0]["resolution"].__setitem__("choice_ids", [{}]),
            lambda c: c["reviews"]["cold_consumer"]["output"].__setitem__("steps", [{}]),
            lambda c: c["reviews"]["cold_consumer"]["output"].__setitem__("local_choices", [{}]),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                contract = base_contract(); mutate(contract)
                result = self.result(contract, "handoff-ready")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(set(json.loads(result.stdout)), OUTPUT_KEYS)

    def test_complete_is_never_returned_for_late_confirmation_or_local_choice_failure(self):
        contract = base_contract()
        contract["reviews"]["cold_consumer"]["generated_at"] = LATER
        rebind(contract, rewire=False)
        output = self.assert_invalid(contract, require="handoff-ready")
        self.assertNotEqual(output["next_action"], "complete")

        contract = base_contract()
        local = {"id": "LC1", "description": "private helper", "unit_id": "U1"}
        for key in ("same_observable_behavior", "unchanged_named_surfaces", "no_system_impact",
                    "private_unit_only", "reversible_without_spec_change"):
            local[key] = {"satisfied": True, "evidence": "The proof is recorded for this private unit."}
        local["private_unit_only"]["satisfied"] = False
        contract["reviews"]["cold_consumer"]["output"]["local_choices"] = [local]
        rebind(contract, rewire=False)
        output = self.assert_invalid(contract, require="handoff-ready")
        self.assertNotEqual(output["next_action"], "complete")

    def test_claimed_gate_states_and_decision_units(self):
        contract = exploring_contract(); self.assert_invalid_text(document(contract, alignment="aligned", handoff="not_requested", session="complete"), "unresolved choices remain", log=contract["_log"])
        contract = exploring_contract(); self.assert_invalid_text(document(contract, alignment="aligned", handoff="ready", session="complete"), "handoff-ready requires nonempty S/A/U", log=contract["_log"])
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
        contract = base_contract(); contract["reviews"]["cold_consumer"]["output"]["implicit_assumptions"] = ["timeout"]; rebind(contract, rewire=False); self.assertEqual(self.assert_invalid(contract, require="handoff-ready")["next_action"], "resolve_findings")
        contract = exploring_contract(); self.assertEqual(self.assert_valid(contract, session="paused")["next_action"], "pause")

    def test_digest_is_unicode_normalization_invariant(self):
        import unicodedata
        nfc = unicodedata.normalize("NFC", "한글 값")
        nfd = unicodedata.normalize("NFD", "한글 값")
        self.assertNotEqual(nfc.encode(), nfd.encode())
        self.assertEqual(digest({"statement": nfc}), digest({"statement": nfd}))
        self.assertEqual(record.canon({"s": nfd}), validator.canon({"s": nfd}))

    def test_instant_normalizes_fractional_seconds_across_versions(self):
        # Every RFC-regex-valid fraction width must parse (not silently None),
        # so ordering checks behave identically on Python 3.9 through 3.14.
        base = validator.instant("2026-08-31T09:00:00+09:00")
        for stamp in ("2026-08-31T09:00:00.5+09:00", "2026-08-31T09:00:00.1234567+09:00",
                      "2026-08-31T09:00:00.000000009Z", "2026-08-31T09:00:00.12Z"):
            with self.subTest(stamp=stamp):
                self.assertIsNotNone(validator.instant(stamp), stamp)
        self.assertIsNotNone(base)

    def test_git_head_locator_shape_enforced_structurally(self):
        contract = base_contract()
        contract["repository_context"]["entries"][0]["locator"] = "HEAD~1"
        refresh(contract)
        self.assert_invalid(contract, "must be HEAD or a full commit hash")
        contract = base_contract()
        contract["repository_context"]["entries"] = [{"kind": "file", "locator": "../escape.txt", "digest": "sha256:" + "c" * 64}]
        refresh(contract)
        self.assert_invalid(contract, "must be a safe relative path")

    def test_json_required_fields_and_cli_exit_codes(self):
        output = self.assert_valid(base_contract()); self.assertEqual(set(output), OUTPUT_KEYS)
        missing = subprocess.run([sys.executable, "-B", str(VALIDATOR), "/path/does/not/exist.md", "--json"], capture_output=True, text=True); self.assertEqual(missing.returncode, 2); self.assertEqual(set(json.loads(missing.stdout)), OUTPUT_KEYS)
        usage = subprocess.run([sys.executable, "-B", str(VALIDATOR), "--unknown", "--json"], capture_output=True, text=True); self.assertEqual(usage.returncode, 2); self.assertEqual(set(json.loads(usage.stdout)), OUTPUT_KEYS)
        no_path = subprocess.run([sys.executable, "-B", str(VALIDATOR), "--json"], capture_output=True, text=True); self.assertEqual(no_path.returncode, 2); self.assertEqual(set(json.loads(no_path.stdout)), OUTPUT_KEYS)
        exploring = exploring_contract()
        invalid = self.run_doc(document(exploring).replace("title: Canonical fixture", "title:"), exploring["_log"]); self.assertEqual(invalid.returncode, 1)
        malformed = self.run_doc(document_with_raw_json(base_contract(), "{"), None); self.assertEqual(malformed.returncode, 1); self.assertEqual(set(json.loads(malformed.stdout)), OUTPUT_KEYS)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "goal.md"; path.write_text(document(exploring), encoding="utf-8")
            (Path(directory) / "goal.responses.jsonl").write_text("", encoding="utf-8")
            plain = subprocess.run([sys.executable, "-B", str(VALIDATOR), str(path), "--no-observe"], capture_output=True, text=True)
            self.assertEqual(plain.returncode, 0, plain.stdout + plain.stderr); self.assertIn("next_action: map_choices", plain.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

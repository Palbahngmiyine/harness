"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _parser_workflow(commands) -> None:
    required = lambda name: ((f"--{name}",), {"required": True})
    common = [required("workspace"), required("run-id")]
    _command(commands, "transition", "record one evidence-backed state transition",
             transition, common + [required(name) for name in (
             "entity", "to", "actor", "role", "reason", "input-digest")] + [
             (("--evidence-ref",), {"action": "append", "required": True}),
             (("--review-round",), {"type": int, "default": 0}),
             (("--failure-code",), {}), (("--failure-reason",), {}),
             (("--failure-evidence",), {"action": "append"}),
             (("--failure-recovery",), {})])
    improve = [required(name) for name in ("unit-id", "actor")]
    improve += [(("--after-round",), {"type": int, "required": True})]
    improve += [required(name) for name in ("kind", "failure-signature", "root-cause",
                "hypothesis", "action", "strategy-digest")]
    improve += [(("--scope-status",), {"default": "within_contract"}),
                (("--evidence-ref",), {"action": "append", "required": True})]
    _command(commands, "record-improvement",
             "append one validated review improvement record", record_improvement,
             common + improve)
    _command(commands, "record-improvement-candidate",
             "record one report-only improvement candidate", record_improvement_candidate,
             common + [required(name) for name in ("summary", "expected-effect", "next-action")]
             + [(("--evidence-ref",), {"action": "append", "required": True})]
             + [required(name) for name in ("scenario", "affected-scope", "impact",
                                             "decision-reason", "evidence-relation",
                                             "success-condition")])


def _parser_goal(commands) -> None:
    required = lambda name: ((f"--{name}",), {"required": True})
    common = [required("workspace"), required("run-id")]
    goal = _command(commands, "goal-sync", "record one Goal observation receipt", goal_sync,
        common + [(("--mode",), {"required": True,
                   "choices": ("bound", "no_active_goal", "unavailable")}),
                  (("--thread-id",), {}), (("--objective-sha256",), {}),
                  (("--receipt-sha256",), {}), (("--token-total",), {"type": int}),
                  required("reason"),
                  (("--evidence-ref",), {"action": "append", "required": True})])
    _command(commands, "goal-complete-sync", "record an external Goal completion receipt",
        goal_complete_sync, common + [required("receipt-sha256"),
        (("--sync-result",), {"required": True,
         "choices": ("completed", "already_completed", "failed")}), required("reason"),
        (("--evidence-ref",), {"action": "append", "required": True}),
        (("--token-total",), {"type": int})])
    _command(commands, "complete", "generate and validate the final report atomically",
             complete_run, common + [required("actor"), required("reason"),
             required("input-digest"),
             (("--evidence-ref",), {"action": "append", "required": True})])
    _command(commands, "validate", "validate one run", validate_run, common)

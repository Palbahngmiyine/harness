import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "references"
PROFILE = ROOT / "assets" / "agents" / "hwahap-sol-orchestrator.toml"
EXACT = "agent thread limit reached"
RECEIPT_FIELDS = ("command_sha256", "diff_digest", "ended_at", "exit_code",
                  "observer_thread_id", "output_sha256", "source", "started_at", "timed_out")

def compact(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())

def fallback(result: str) -> bool:
    return result == EXACT

def valid_fallback(item: dict) -> bool:
    return (fallback(item["result"]) and item["partial"] == "discarded"
            and item["luna"] == item["terra"] == "fresh"
            and item["review_order"] == "luna>terra" and item["snapshot"] == "identical"
            and item["threads"] == "distinct" and item["outcomes"] == "pass/pass"
            and item["deviations"] == 1 and item["causal"] == CAUSAL
            and item["sync"] == "units>checks>sync>ultra")

def canonical_receipt(fields: dict) -> str:
    required = (key for key in RECEIPT_FIELDS if key != "exit_code")
    if set(fields) != set(RECEIPT_FIELDS) or any(fields[key] in (None, "") for key in required):
        raise ValueError("complete invocation fields required")
    if not isinstance(fields["timed_out"], bool) or ((fields["exit_code"] is None) != fields["timed_out"]):
        raise ValueError("exit_code/timed_out mismatch")
    raw = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


CAUSAL = "summary/root_cause/impact/prevention/evidence_explanation/evidence"
BASE = {"result": EXACT, "partial": "discarded", "luna": "fresh", "terra": "fresh",
        "review_order": "luna>terra", "snapshot": "identical", "threads": "distinct",
        "outcomes": "pass/pass", "deviations": 1, "causal": CAUSAL, "sync": "units>checks>sync>ultra"}
EXECUTION_MARKERS = ("concurrent-first activation", "exact platform result `agent thread limit reached`",
                     "discard all partial parallel-attempt", "both fresh envelopes are required",
                     "identical six-field `diff_snapshot`", "Luna completes, start a fresh Terra reviewer sequentially",
                     "Substrings, case variants", "Record exactly one complete exact-v4 deviation",
                     "nonempty `evidence_explanation`", "post-source installation synchronization is external-only",
                     "every source unit/full source checks pass", "before final Sol Ultra", "never a source unit, allowed path, or `diff_snapshot` mutation",
                     "Fresh means a new thread unused by any attempt; only exact `agent thread limit reached`")
WATCHDOG_MARKERS = ("visible checkpoint", "60-second", "first miss", "second interrupts",
                    "emergency Sol orchestration/state proxy", "never writes source or skips",
                    "retained exec sessions", "never rerun", "opaque retries", "one failed recovery",
                    "completed exact-role thread with a fresh turn", "discard partial evidence",
                    "distinct Luna/Terra", "same snapshot", "one official long/full",
                    "reviewers reconcile receipts", "focused checks only", "sorted-key",
                    "whitespace-free UTF-8 JSON", "missing data stops")


def source_oracle(text: str) -> bool:
    try:
        sync = text.index("post-source installation synchronization")
        checks = text.index("after every source unit/full source checks pass")
        ultra = text.index("before final Sol Ultra")
        boundary = text.index("never a source unit, allowed path")
        return (all(marker in text for marker in EXECUTION_MARKERS)
                and text.index("fresh Luna reviewer; after") < text.index("Luna completes, start")
                and sync < checks < ultra < boundary)
    except ValueError:
        return False


class SchedulingContractTests(unittest.TestCase):
    def test_exact_capacity_result_is_the_only_fallback_trigger(self):
        self.assertTrue(fallback(EXACT))
        for value in (EXACT + " now", EXACT.upper(), "capacity", "timeout", "reviewer failed"):
            self.assertFalse(fallback(value))

    def test_fallback_requires_every_gate(self):
        self.assertTrue(valid_fallback(BASE))
        for key in BASE:
            self.assertFalse(valid_fallback(BASE | {key: "invalid"}), key)

    def test_normative_text_and_mutations(self):
        execution = compact(REFS / "execution-review.md")
        self.assertTrue(source_oracle(execution))
        for marker in EXECUTION_MARKERS:
            self.assertFalse(source_oracle(execution.replace(marker, "weakened", 1)), marker)

    def test_watchdog_and_canonical_receipt_fail_closed(self):
        for text in (compact(REFS / "execution-review.md"), compact(PROFILE)):
            self.assertTrue(all(marker in text for marker in WATCHDOG_MARKERS))
            for marker in WATCHDOG_MARKERS:
                self.assertFalse(all(value in text.replace(marker, "weak") for value in WATCHDOG_MARKERS))
            for field in RECEIPT_FIELDS: self.assertIn(f"`{field}`", text)
        values = {key: key for key in RECEIPT_FIELDS} | {"exit_code": 0, "timed_out": False}
        self.assertEqual(canonical_receipt(values), canonical_receipt(dict(reversed(tuple(values.items())))))
        for item in (values | {"exit_code": None}, values | {"timed_out": True}, values | {"source": ""},
                     {key: value for key, value in values.items() if key != "source"}):
            with self.assertRaises(ValueError): canonical_receipt(item)
        self.assertEqual(len(canonical_receipt(values | {"exit_code": None, "timed_out": True})), 64)

if __name__ == "__main__": unittest.main()

import copy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "references"
EXACT = "agent thread limit reached"


def compact(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def fallback(result: str) -> bool:
    return result == EXACT


def valid_fallback(fixture: dict) -> bool:
    return (fallback(fixture["result"]) and fixture["partial"] == "discarded"
            and fixture["luna"] == fixture["terra"] == "fresh"
            and fixture["review_order"] == "luna>terra"
            and fixture["snapshot"] == "identical"
            and fixture["threads"] == "distinct"
            and fixture["outcomes"] == "pass/pass"
            and fixture["deviations"] == 1
            and fixture["causal"] == "summary/root_cause/impact/prevention/evidence_explanation/evidence"
            and fixture["sync"] == "units>checks>sync>ultra")


BASE = {"result": EXACT, "partial": "discarded", "luna": "fresh",
        "terra": "fresh", "review_order": "luna>terra", "snapshot": "identical", "threads": "distinct",
        "outcomes": "pass/pass", "deviations": 1,
        "causal": "summary/root_cause/impact/prevention/evidence_explanation/evidence",
        "sync": "units>checks>sync>ultra"}
EXECUTION_MARKERS = ("concurrent-first activation", "exact platform result `agent thread limit reached`",
                     "discard all partial parallel-attempt", "both fresh envelopes are required",
                     "identical six-field `diff_snapshot`",
                     "Luna completes, start a fresh Terra reviewer sequentially",
                     "Substrings, case variants", "Record exactly one complete exact-v4 deviation",
                     "nonempty `evidence_explanation`", "post-source installation synchronization is external-only",
                     "every source unit/full source checks pass", "before final Sol Ultra",
                     "never a source unit, allowed path, or `diff_snapshot` mutation")


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
        for result in ("agent thread limit reached while starting Luna",
                       "AGENT THREAD LIMIT REACHED", "agent thread capacity reached",
                       "timeout", "reviewer failed"):
            self.assertFalse(fallback(result))

    def test_fallback_requires_discard_fresh_pair_and_ordered_sync(self):
        self.assertTrue(valid_fallback(BASE))
        for field, value in (("partial", "retained"), ("partial", "missing"),
                             ("luna", "missing"), ("luna", "reused"),
                             ("terra", "missing"), ("terra", "reused"),
                             ("review_order", "terra>luna"),
                             ("snapshot", "different"),
                             ("threads", "reused"), ("sync", "units>sync>checks>ultra"),
                             ("outcomes", "pass/timeout"), ("outcomes", "pass/fail"),
                             ("deviations", 0), ("deviations", 2),
                             ("causal", "summary/root_cause/impact"),
                             ("result", "timeout")):
            mutant = copy.copy(BASE)
            mutant[field] = value
            self.assertFalse(valid_fallback(mutant), field)

    def test_normative_text_and_mutations(self):
        execution = compact(REFS / "execution-review.md")
        self.assertTrue(source_oracle(execution))
        for marker in EXECUTION_MARKERS:
            mutant = execution.replace(marker, "weakened rule", 1)
            self.assertFalse(source_oracle(mutant), marker)
        reversed_order = execution.replace("Luna completes, start a fresh Terra",
                                           "Terra completes, start a fresh Luna", 1)
        self.assertFalse(source_oracle(reversed_order))
        early = execution.replace("after every source unit/full source checks pass and before final Sol Ultra",
                                  "before every source unit/full source checks pass and before final Sol Ultra", 1)
        late = execution.replace("after every source unit/full source checks pass and before final Sol Ultra",
                                 "before final Sol Ultra and after every source unit/full source checks pass", 1)
        self.assertFalse(source_oracle(early))
        self.assertFalse(source_oracle(late))
        self.assertNotIn("align-goal", (execution + compact(REFS / "protocol.md")).lower())


if __name__ == "__main__": unittest.main()

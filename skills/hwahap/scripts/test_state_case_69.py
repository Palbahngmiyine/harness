"""Case 69: bind handoff-ready align-goal S/A/U without PRFAQ."""
try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
    from .test_handoffkit import write_goal_artifact
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *
    from test_handoffkit import write_goal_artifact


class HwahapStateCase69(StateFixtureMixin01, unittest.TestCase):
    def _resign(self, contract):
        digest = hwahap_state.align_digest({key: contract[key]
            for key in hwahap_state.ALIGN_PROJECTION_KEYS})
        reviews = contract["reviews"]
        for review in reviews.values():
            review["spec_digest"] = digest
        handoff = contract["confirmations"]["handoff_document"]
        handoff.update(spec_digest=digest,
            ambiguity_receipt_digest=hwahap_state.align_digest(reviews["ambiguity_auditor"]),
            cold_receipt_digest=hwahap_state.align_digest(reviews["cold_consumer"]))

    def test_goal_handoff_initializes_and_revalidates_sealed_projection(self) -> None:
        source = write_goal_artifact(self.workspace)
        with redirect_stdout(io.StringIO()):
            hwahap_state.init_run(Namespace(workspace=str(self.workspace),
                goal_id="aligned-goal", goal_spec=str(source)))
        run_dir = self.workspace / ".hwahap" / "runs" / "aligned-goal"
        saved = json.loads((run_dir / "contract.json").read_text())["spec"]
        self.assertEqual(saved["status"], "align-goal")
        self.assertEqual(set(saved["handoff"]), {"schema", "revision", "spec_digest",
            "specifications", "acceptance_checks", "implementation_units", "confirmation"})
        hwahap_state.validate_run(Namespace(workspace=str(self.workspace),
            run_id="aligned-goal", quiet=True))
        source.write_text(source.read_text() + "changed\n", encoding="utf-8")
        with self.assertRaises(hwahap_state.HwahapError):
            hwahap_state.validate_run(Namespace(workspace=str(self.workspace),
                run_id="aligned-goal", quiet=True))

    def test_goal_handoff_rejects_stale_receipt_and_unmapped_acceptance(self) -> None:
        for change in (lambda c: c["reviews"]["cold_consumer"].update(spec_digest="sha256:" + "b" * 64),
                       lambda c: c["implementation_units"][0].update(acceptance_ids=[]),
                       lambda c: c["reviews"]["cold_consumer"]["output"]["implicit_assumptions"].append("choice")):
            with self.subTest(change=change), self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.load_goal_spec(write_goal_artifact(self.workspace, change))
            self.assertEqual(raised.exception.code, "HW_HANDOFF_UNCONFIRMED")

    def test_malformed_reviewer_is_stable_public_cli_failure(self) -> None:
        source = write_goal_artifact(self.workspace,
            lambda contract: contract["reviews"].update(ambiguity_auditor=[]))
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = hwahap_state.main(["init-goal", "--workspace", str(self.workspace),
                "--goal-id", "bad-handoff", "--goal-spec", str(source)])
        self.assertEqual(result, 1)
        self.assertEqual(stderr.getvalue(), "HW_HANDOFF_UNCONFIRMED: "
            "align-goal handoff is unavailable or invalid\n")
        self.assertFalse((self.workspace / ".hwahap" / "runs" / "bad-handoff").exists())

    def test_goal_handoff_rejects_every_unclosed_choice_status(self) -> None:
        def change(contract, status):
            contract["choices"][0]["status"] = status
            self._resign(contract)
        for status in ("candidate", "asked", "open", "unresolved", "unknown"):
            with self.subTest(status=status), self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.load_goal_spec(write_goal_artifact(
                    self.workspace, lambda contract: change(contract, status)))

    def test_goal_handoff_rejects_every_unresolved_item_status(self) -> None:
        def change(contract, status):
            contract["open_items"] = [{"status": status}]
            self._resign(contract)
        for status in ("open", "unresolved", "unknown"):
            with self.subTest(status=status), self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.load_goal_spec(write_goal_artifact(
                    self.workspace, lambda contract: change(contract, status)))


if __name__ == "__main__":
    unittest.main()

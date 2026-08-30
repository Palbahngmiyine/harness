try:
    from .test_dependency_kit import *
except ImportError:
    from test_dependency_kit import *


class VerifiedGraphTests(DependencyIntegrityTests):
    def test_state_runtime_links_only_referenced_cross_module_names(self) -> None:
        loaded = self._load("narrow_state_runtime", ROOT / "hwahap_state.py")
        loaded._ensure_dependencies()
        api = loaded._boot._api
        complete_space = api._owners["complete_run"]
        self.assertIn("publish_terminal_report", complete_space)
        self.assertNotIn("goal_sync", complete_space)
        module_count = len(api._runtime._records)
        self.assertLess(max(map(len, api._runtime._consumers.values())), module_count)

    def test_state_manifest_and_internal_module_tamper_are_rejected(self) -> None:
        for target in ("hwahap_state_manifest.json", "hwahap_state_metrics.py"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._copy_scripts(root)
                (root / target).write_text("{}\n", encoding="utf-8")
                loaded = self._load("tampered_" + target.replace(".", "_"),
                                    root / "hwahap_state.py")
                with self.assertRaises(loaded.HwahapError) as raised:
                    loaded._ensure_dependencies()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_report_graph_accepts_pins_and_rejects_module_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scripts = self._copy_report_graph(Path(directory))
            loaded = self._load("verified_report", scripts / "hwahap_report.py")
            self.assertTrue(loaded.credential_bearing_text("client_secret=canary"))
            (scripts / "hwahap_report_security.py").write_text("# changed\n",
                                                               encoding="utf-8")
            broken = self._load("tampered_report", scripts / "hwahap_report.py")
            with self.assertRaises(broken.HwahapReportError) as raised:
                broken.credential_bearing_text("client_secret=canary")
            self.assertEqual(str(raised.exception), "report dependency unavailable")

    def test_runtime_sources_do_not_execute_dynamic_source(self) -> None:
        pattern = re.compile(r"\b(?:exec|eval)\s*\(")
        for path in ROOT.glob("hwahap*.py"):
            with self.subTest(path=path.name):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))

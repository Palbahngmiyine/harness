try:
    from .test_dependency_kit import *
except ImportError:
    from test_dependency_kit import *


class VerifiedGraphTests(DependencyIntegrityTests):
    def test_state_test_launcher_propagates_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(ROOT / "test_hwahap_state.py", root)
            (root / "test_state_case_01.py").write_text(
                "import unittest\n"
                "class Failure(unittest.TestCase):\n"
                "    def test_failure(self): self.fail('canary')\n",
                encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(root / "test_hwahap_state.py")],
                cwd=root, capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)

    def test_state_runtime_links_only_referenced_cross_module_names(self) -> None:
        loaded = self._load("narrow_state_runtime", ROOT / "hwahap_state.py")
        loaded._ensure_dependencies()
        api = loaded._boot._api
        complete_space = api._owners["complete_run"]
        self.assertIn("publish_terminal_report", complete_space)
        self.assertNotIn("goal_sync", complete_space)
        module_count = len(api._runtime._records)
        self.assertLess(max(map(len, api._runtime._consumers.values())), module_count)

    def test_state_module_dependency_graph_is_acyclic(self) -> None:
        loaded = self._load("acyclic_state_runtime", ROOT / "hwahap_state.py")
        loaded._ensure_dependencies()
        api = loaded._boot._api
        modules = {space["__name__"] for space, _ in api._runtime._records}
        dependencies = {module: set() for module in modules}
        for name, consumers in api._runtime._consumers.items():
            owner = api._owners[name]["__name__"]
            for space in consumers:
                consumer = space["__name__"]
                if consumer != owner:
                    dependencies[consumer].add(owner)
        remaining = set(dependencies)
        while ready := {
                module for module in remaining
                if not dependencies[module] & remaining}:
            remaining -= ready
        self.assertEqual(remaining, set())

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

    def test_all_hwahap_module_imports_are_acyclic(self) -> None:
        sources = {path.stem: path for path in ROOT.glob("hwahap*.py")}
        dependencies = {name: set() for name in sources}
        for name, path in sources.items():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for item in ast.walk(tree):
                imported = []
                if isinstance(item, ast.Import):
                    imported = [alias.name for alias in item.names]
                elif isinstance(item, ast.ImportFrom) and item.module:
                    imported = [item.module]
                dependencies[name].update(
                    target for target in imported if target in sources)
        remaining = set(dependencies)
        while ready := {name for name in remaining
                        if not dependencies[name] & remaining}:
            remaining -= ready
        self.assertEqual(remaining, set())

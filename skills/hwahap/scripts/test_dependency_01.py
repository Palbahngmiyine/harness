try:
    from .test_dependency_kit import *
except ImportError:
    from test_dependency_kit import *

class DependencySlice1Tests(DependencyIntegrityTests):
    def test_help_and_direct_import_are_lazy(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                fake = Path(directory) / "hwahap_credentials.py"
                fake.write_text("raise RuntimeError('fake dependency')\n", encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, str(ROOT / "hwahap_state.py"), "--help"],
                    cwd=directory, env={"PATH": os.defpath, "PYTHONPATH": directory},
                    capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0)
                self.assertNotIn("fake dependency", result.stderr)
                loaded = self._load("lazy_report", ROOT / "hwahap_report.py")
                self.assertIsNone(loaded._credential_module)

class DependencySlice2Tests(DependencyIntegrityTests):
    def test_sealed_copy_accepts_pins_and_rejects_tamper_or_symlink(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._copy_scripts(root)
                loaded = self._load("sealed_state", root / "hwahap_state.py")
                loaded._ensure_dependencies()
                (root / "hwahap_credentials.py").write_text("# changed\n", encoding="utf-8")
                broken = self._load("tampered_state", root / "hwahap_state.py")
                with self.assertRaises(broken.HwahapError) as raised:
                    broken._ensure_dependencies()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                (root / "hwahap_credentials.py").unlink()
                (root / "hwahap_credentials.py").symlink_to(Path("/dev/null"))
                symlinked = self._load("symlink_state", root / "hwahap_state.py")
                with self.assertRaises(symlinked.HwahapError) as raised:
                    symlinked._ensure_dependencies()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

class DependencySlice3Tests(DependencyIntegrityTests):
    def test_report_missing_dependency_is_direct_report_error(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copy2(ROOT / "hwahap_report.py", root / "hwahap_report.py")
                loaded = self._load("missing_report_dependency", root / "hwahap_report.py")
                with self.assertRaises(ValueError) as raised:
                    loaded._ensure_credentials()
                self.assertEqual(type(raised.exception).__name__, "HwahapReportError")
                self.assertEqual(str(raised.exception), "report credential dependency unavailable")

class DependencySlice4Tests(DependencyIntegrityTests):
    def test_official_launcher_isolates_cwd_and_pythonpath(self) -> None:
            launcher = ROOT / "hwahap"
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name in ("re.py", "dataclasses.py"):
                    (root / name).write_text("raise RuntimeError('launcher-canary')\n", encoding="utf-8")
                env = {"PATH": os.defpath, "PYTHONPATH": directory}
                help_result = subprocess.run([str(launcher), "--help"], cwd=directory, env=env,
                                             capture_output=True, text=True, check=False)
                self.assertEqual(help_result.returncode, 0)
                self.assertNotIn("launcher-canary", help_result.stdout + help_result.stderr)
                invalid = subprocess.run([str(launcher), "validate", "--workspace", directory,
                                          "--run-id", "missing"], cwd=directory, env=env,
                                         capture_output=True, text=True, check=False)
                self.assertEqual(invalid.returncode, 1)
                self.assertIn("HW_STATE_INVALID:", invalid.stderr)
                self.assertNotIn("launcher-canary", invalid.stdout + invalid.stderr)
                self.assertNotIn("Traceback", invalid.stdout + invalid.stderr)

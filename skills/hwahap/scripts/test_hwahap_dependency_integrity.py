"""Sealed dependency loading and lazy-import regressions."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).parent


class DependencyIntegrityTests(unittest.TestCase):
    def _load(self, name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module

    def _copy_scripts(self, directory: Path) -> None:
        for name in ("hwahap_state.py", "hwahap_report.py", "hwahap_redaction.py", "install_project_agents.py"):
            shutil.copy2(ROOT / name, directory / name)

    def test_help_and_direct_import_are_lazy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "hwahap_redaction.py"
            fake.write_text("raise RuntimeError('fake dependency')\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "hwahap_state.py"), "--help"],
                cwd=directory, env={"PATH": os.defpath, "PYTHONPATH": directory},
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertNotIn("fake dependency", result.stderr)
            loaded = self._load("lazy_report", ROOT / "hwahap_report.py")
            self.assertIsNone(loaded._redaction_module)

    def test_sealed_copy_accepts_pins_and_rejects_tamper_or_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_scripts(root)
            loaded = self._load("sealed_state", root / "hwahap_state.py")
            loaded._ensure_dependencies()
            (root / "hwahap_redaction.py").write_text("# changed\n", encoding="utf-8")
            broken = self._load("tampered_state", root / "hwahap_state.py")
            with self.assertRaises(broken.HwahapError) as raised:
                broken._ensure_dependencies()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            (root / "hwahap_redaction.py").unlink()
            (root / "hwahap_redaction.py").symlink_to(Path("/dev/null"))
            symlinked = self._load("symlink_state", root / "hwahap_state.py")
            with self.assertRaises(symlinked.HwahapError) as raised:
                symlinked._ensure_dependencies()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_report_missing_dependency_is_direct_report_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(ROOT / "hwahap_report.py", root / "hwahap_report.py")
            loaded = self._load("missing_report_dependency", root / "hwahap_report.py")
            with self.assertRaises(ValueError) as raised:
                loaded._ensure_redaction()
            self.assertEqual(type(raised.exception).__name__, "HwahapReportError")
            self.assertEqual(str(raised.exception), "report redaction dependency unavailable")

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

    def test_launcher_is_absolute_fixed_and_rejects_symlink_entrypoint(self) -> None:
        launcher = ROOT / "hwahap"
        source = launcher.read_text(encoding="utf-8")
        self.assertNotIn("dirname", source)
        self.assertNotIn("readlink", source)
        self.assertNotIn("which", source)
        self.assertNotIn("$(", source)
        self.assertIn("-I -S", source)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_path = root / "bin"
            fake_path.mkdir()
            for name in ("python3", "dirname"):
                fake = fake_path / name
                fake.write_text("printf '%s\\n' launcher-canary >&2; exit 1\n", encoding="utf-8")
                fake.chmod(0o755)
            env = {"PATH": str(fake_path), "PYTHONPATH": str(root)}
            result = subprocess.run([str(launcher), "--help"], cwd=root, env=env,
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertNotIn("launcher-canary", result.stdout + result.stderr)
            link = root / "launcher-link"
            link.symlink_to(launcher)
            linked = subprocess.run([str(link), "--help"], cwd=root, env=env,
                                    capture_output=True, text=True, check=False)
            self.assertEqual(linked.returncode, 1)
            self.assertEqual(linked.stderr, "HW_STATE_INVALID: state is invalid\n")
            self.assertNotIn(str(root), linked.stderr)

    def test_official_commands_use_absolute_launcher_and_readme_help_runs(self) -> None:
        repository = ROOT.parents[2]
        documents = (*sorted((repository / "skills/hwahap").rglob("*.md")),
                     repository / "skills/hwahap/assets/agents/hwahap-sol-orchestrator.toml")
        marker = "<absolute-hwahap-skill-dir>/scripts/hwahap"
        for document in documents:
            for line in document.read_text(encoding="utf-8").splitlines():
                if "scripts/hwahap" in line:
                    self.assertIn(marker, line, document.name)
        readme = (repository / "README.md").read_text(encoding="utf-8")
        self.assertIn('"$PWD/skills/hwahap/scripts/hwahap" --help', readme)
        launcher = (repository / "skills/hwahap/scripts/hwahap").resolve()
        result = subprocess.run(
            [str(launcher), "--help"], cwd=repository,
            env={"PATH": os.defpath}, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout.lower())

    def test_hwahap_markdown_is_bounded_and_local_links_resolve(self) -> None:
        repository = ROOT.parents[2]
        documents = [repository / "README.md",
                     *sorted((repository / "skills/hwahap").rglob("*.md"))]
        for document in documents:
            with self.subTest(document=document.relative_to(repository)):
                self.assertLessEqual(len(document.read_text(encoding="utf-8").splitlines()), 200)
                for target in re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", document.read_text(encoding="utf-8")):
                    if "://" not in target:
                        self.assertTrue((document.parent / target).resolve().is_file(), target)


if __name__ == "__main__":
    unittest.main()

try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


class InstallerBoundaryTests(InstallerFixture, unittest.TestCase):
    def test_launcher_selects_supported_isolated_python(self):
        launcher = Path(installer.__file__).with_name("install-project-agents")
        result = subprocess.run([str(launcher), "--workspace", str(self.root)], cwd=self.root,
                                env={"PATH": "/usr/bin"}, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HW_OK: installed=6 skipped=0", result.stdout)

    def test_missing_non_directory_and_symlink_workspace_fail_closed(self):
        self.assert_code("HW_AGENT_PATH_INVALID", self.root / "missing")
        file_path = self.root / "workspace-file"
        file_path.write_text("not a directory", encoding="utf-8")
        self.assert_code("HW_AGENT_PATH_INVALID", file_path)
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        link.symlink_to(target)
        self.assert_code("HW_AGENT_PATH_INVALID", link)
        self.assertFalse((target / ".codex").exists())

    def test_invalid_source_is_checked_before_workspace_mutation(self):
        source = self.root / "source"
        source.mkdir()
        source.joinpath("hwahap-luna-implementer.toml").write_bytes(b"bad")
        with patch.object(installer, "PROFILE_DIR", source):
            self.assert_code("HW_AGENT_SOURCE_INVALID", self.root / "new")
        self.assertFalse((self.root / "new/.codex").exists())

    def test_symlinked_codex_agents_and_target_fail_closed(self):
        codex_target = self.root / "codex-target"
        codex_target.mkdir()
        workspace = self.root / "codex-workspace"
        workspace.mkdir()
        (workspace / ".codex").symlink_to(codex_target, target_is_directory=True)
        self.assert_code("HW_AGENT_PATH_INVALID", workspace)
        workspace = self.root / "agents-workspace"
        (workspace / ".codex").mkdir(parents=True)
        agents_target = self.root / "agents-target"
        agents_target.mkdir()
        (workspace / ".codex/agents").symlink_to(agents_target, target_is_directory=True)
        self.assert_code("HW_AGENT_PATH_INVALID", workspace)

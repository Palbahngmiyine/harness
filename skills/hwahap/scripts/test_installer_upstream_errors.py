try:
    from .test_installer_faultkit import InstallerFaultMixin, installer
except ImportError:
    from test_installer_faultkit import InstallerFaultMixin, installer
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


class UpstreamInstallerErrorTests(InstallerFaultMixin, unittest.TestCase):
    def test_public_cli_errors_are_static_and_path_free(self):
        self.assertEqual(set(installer.PUBLIC_ERROR_MESSAGES), {
            "HW_AGENT_ARGUMENT_INVALID", "HW_AGENT_SOURCE_INVALID", "HW_AGENT_PATH_INVALID",
            "HW_AGENT_CONFLICT", "HW_AGENT_CONFIG_INVALID", "HW_AGENT_INSTALL_FAILED"})
        marker = "Proxy-Authorization: Basic /private/tmp/installer-canary"
        for argv in (["--unknown", marker], []):
            stderr = io.StringIO()
            with redirect_stderr(stderr): self.assertEqual(installer.main(argv), 1)
            self.assertEqual(stderr.getvalue(), "HW_AGENT_ARGUMENT_INVALID: invalid installer arguments\n")
            self.assertNotIn(marker, stderr.getvalue())
        stderr = io.StringIO()
        with patch.object(installer, "install", side_effect=OSError(marker)):
            with redirect_stderr(stderr): self.assertEqual(installer.main(["--workspace", marker]), 1)
        self.assertEqual(stderr.getvalue(), "HW_AGENT_INSTALL_FAILED: profile installation failed\n")
        self.assertNotIn(marker, stderr.getvalue())

    def test_source_directory_read_error_and_cli_install_error_are_generic(self):
        marker = "Authorization: Bearer /private/tmp/source-canary"
        with patch.object(Path, "iterdir", side_effect=OSError(marker)):
            with self.assertRaises(installer.InstallError) as raised: installer.source_profiles()
        self.assertEqual(raised.exception.code, "HW_AGENT_SOURCE_INVALID")
        self.assertNotIn(marker, str(raised.exception))
        stderr = io.StringIO()
        with patch.object(installer, "install", side_effect=OSError(marker)):
            with redirect_stderr(stderr): self.assertEqual(installer.main(["--workspace", str(self.root)]), 1)
        self.assertEqual(stderr.getvalue(), "HW_AGENT_INSTALL_FAILED: profile installation failed\n")
        self.assertNotIn(marker, stderr.getvalue())

    def test_installer_never_creates_or_edits_config_toml(self):
        self.run_install(); self.assertFalse((self.root / ".codex" / "config.toml").exists())
        existing = self.root / "with-config"; (existing / ".codex").mkdir(parents=True)
        config = existing / ".codex" / "config.toml"; original = b"[project]\nname = 'user-config'\n"
        config.write_bytes(original); self.run_install(existing)
        self.assertEqual(config.read_bytes(), original)

    def test_unexpected_hwahap_profile_is_rejected_before_any_write(self):
        for index, name in enumerate(("hwahap-extra.toml", "HWAHAP-extra.TOML")):
            with self.subTest(name=name):
                agents = self.root / f"unexpected-{index}" / ".codex" / "agents"; agents.mkdir(parents=True)
                marker = agents / name; marker.write_bytes(b"credential-canary")
                with self.assertRaises(installer.InstallError) as raised: self.run_install(agents.parents[1])
                self.assertEqual(raised.exception.code, "HW_AGENT_CONFLICT")
                self.assertNotIn(name, str(raised.exception)); self.assertEqual(marker.read_bytes(), b"credential-canary")
                self.assertFalse(any((agents / path.name).exists() for path, _ in installer.source_profiles()))

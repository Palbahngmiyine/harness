try:
    from .test_installer_faultkit import InstallerFaultMixin, installer
except ImportError:
    from test_installer_faultkit import InstallerFaultMixin, installer
import os
import unittest
from unittest.mock import patch


class UpstreamInstallerDirectoryTests(InstallerFaultMixin, unittest.TestCase):
    def test_directory_replacement_uses_original_descriptors(self):
        profiles = installer.source_profiles()
        for component in ("codex", "agents"):
            for fail_index in (1, 2):
                with self.subTest(component=component, fail_index=fail_index):
                    workspace = self.root / f"swap-{component}-{fail_index}"
                    (workspace / ".codex/agents").mkdir(parents=True)
                    external = workspace / f"external-{component}-{fail_index}"; external.mkdir()
                    original_open = installer.os.open; calls = 0
                    def swap(name, flags, mode=0o777, *, dir_fd=None):
                        nonlocal calls
                        if flags & os.O_CREAT and flags & os.O_EXCL:
                            calls += 1
                            if calls == fail_index:
                                visible = workspace / ".codex" / ("agents" if component == "agents" else "")
                                moved = workspace / f"{component}-original"; visible.rename(moved)
                                visible.symlink_to(external, target_is_directory=True)
                        return original_open(name, flags, mode, dir_fd=dir_fd)
                    with patch.object(installer.os, "open", new=swap):
                        with self.assertRaises(installer.InstallError) as raised: self.run_install(workspace)
                    self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
                    self.assertNotIn(str(workspace), str(raised.exception))
                    self.assertEqual(list(external.iterdir()), [])
                    visible = workspace / ".codex" / ("agents" if component == "agents" else "")
                    self.assertTrue(visible.is_symlink())
                    original_agents = (workspace / "agents-original" if component == "agents" else workspace / "codex-original" / "agents")
                    for path, _ in profiles: self.assertFalse((original_agents / path.name).exists())

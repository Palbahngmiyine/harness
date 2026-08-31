try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import unittest


class InstallerConflictTests(InstallerFixture, unittest.TestCase):
    def test_different_existing_profile_does_not_mutate_pending_files(self):
        profiles = self.profiles()
        agents = self.agents()
        agents.mkdir(parents=True)
        conflict = agents / profiles[0][0].name
        conflict.write_bytes(b"different")
        self.assert_code("HW_AGENT_CONFLICT")
        self.assertEqual(conflict.read_bytes(), b"different")
        self.assertEqual(tuple(agents.glob("hwahap-*.toml")), (conflict,))

    def test_casefolded_unexpected_profile_is_preserved(self):
        agents = self.agents()
        agents.mkdir(parents=True)
        marker = agents / "HWAHAP-extra.TOML"
        marker.write_bytes(b"extra")
        unrelated = agents / "user-agent.toml"
        unrelated.write_bytes(b"unrelated")
        self.assert_code("HW_AGENT_CONFLICT")
        self.assertEqual(marker.read_bytes(), b"extra")
        self.assertEqual(unrelated.read_bytes(), b"unrelated")

    def test_existing_symlink_target_is_not_followed(self):
        agents = self.agents()
        agents.mkdir(parents=True)
        target = self.root / "target"
        target.write_bytes(b"outside")
        link = agents / self.profiles()[0][0].name
        link.symlink_to(target)
        self.assert_code("HW_AGENT_PATH_INVALID")
        self.assertEqual(target.read_bytes(), b"outside")

    def test_config_and_unrelated_agent_are_never_overwritten(self):
        agents = self.agents()
        agents.mkdir(parents=True)
        unrelated = agents / "user-agent.toml"
        unrelated.write_bytes(b"keep")
        config = self.root / ".codex/config.toml"
        config.write_bytes(b"[keep]\n")
        self.run_install()
        self.assertEqual(unrelated.read_bytes(), b"keep")
        self.assertEqual(config.read_bytes(), b"[keep]\n")

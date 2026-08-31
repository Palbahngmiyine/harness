try:
    from .test_installer_faultkit import InstallerFaultMixin, installer
except ImportError:
    from test_installer_faultkit import InstallerFaultMixin, installer
import unittest


class UpstreamInstallerBasicTests(InstallerFaultMixin, unittest.TestCase):
    def test_fresh_install_copies_all_profiles_byte_identically(self):
        self.run_install()
        expected = {path.name: raw for path, raw in installer.source_profiles()}
        targets = tuple(self.agents().glob("*.toml"))
        actual = {path.name: path.read_bytes() for path in targets}
        self.assertEqual(actual, expected)
        self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in targets))

    def test_second_install_is_idempotent(self):
        self.run_install()
        before = {path.name: path.read_bytes() for path in self.agents().glob("*.toml")}
        output = self.run_install()
        self.assertEqual({path.name: path.read_bytes() for path in self.agents().glob("*.toml")}, before)
        self.assertIn("installed=0", output)
        self.assertIn("skipped=6", output)

    def test_unrelated_target_profile_is_preserved(self):
        self.run_install()
        unrelated = self.agents() / "user-agent.toml"
        unrelated.write_text('name = "user-agent"\n', encoding="utf-8")
        self.run_install()
        self.assertEqual(unrelated.read_text(encoding="utf-8"), 'name = "user-agent"\n')

    def test_conflict_stops_without_mutation_or_later_installs(self):
        profiles = installer.source_profiles()
        agents = self.agents(); agents.mkdir(parents=True)
        first = agents / profiles[0][0].name; original = b"different existing profile\n"
        first.write_bytes(original)
        with self.assertRaises(installer.InstallError) as raised: self.run_install()
        self.assertEqual(raised.exception.code, "HW_AGENT_CONFLICT")
        self.assertEqual(first.read_bytes(), original)
        for path, _ in profiles[1:]: self.assertFalse((agents / path.name).exists())

    def test_preflight_conflict_does_not_create_any_pending_profile(self):
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("preflight-conflict")
        conflicting = workspace / ".codex" / "agents" / profiles[1][0].name
        conflicting.write_bytes(b"conflict-canary")
        with self.assertRaises(installer.InstallError) as raised: self.run_install(workspace)
        self.assertEqual(raised.exception.code, "HW_AGENT_CONFLICT")
        self.assertEqual(conflicting.read_bytes(), b"conflict-canary")
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)
        for path, _ in profiles[2:]: self.assertFalse((workspace / ".codex" / "agents" / path.name).exists())

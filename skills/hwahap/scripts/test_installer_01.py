try:
    from .test_installerkit import *
except ImportError:
    from test_installerkit import *

import tomllib


class InstallerContractTests(InstallerFixture, unittest.TestCase):
    def test_source_contract_and_byte_identical_install(self):
        profiles = installer.source_profiles()
        self.assertEqual(len(profiles), 6)
        for path, raw in profiles:
            value = tomllib.loads(raw.decode())
            expected = installer.PROFILE_CONTRACT[path.name]
            self.assertEqual(value["name"], expected[0])
            self.assertEqual(value["model"], expected[1])
        self.run_install()
        installed = {
            path.name: path.read_bytes()
            for path in (self.root / ".codex/agents").iterdir()
        }
        self.assertEqual(installed, {path.name: raw for path, raw in profiles})

    def test_idempotence_and_unrelated_config_preservation(self):
        agents = self.root / ".codex/agents"
        agents.mkdir(parents=True)
        unrelated = agents / "user-agent.toml"
        unrelated.write_bytes(b"user")
        config = self.root / ".codex/config.toml"
        config.write_bytes(b"[keep]\n")
        self.run_install()
        output = self.run_install()
        self.assertIn("installed=0", output)
        self.assertIn("skipped=6", output)
        self.assertEqual(unrelated.read_bytes(), b"user")
        self.assertEqual(config.read_bytes(), b"[keep]\n")

    def test_conflict_and_unexpected_profile_write_nothing(self):
        profiles = installer.source_profiles()
        agents = self.root / ".codex/agents"
        agents.mkdir(parents=True)
        conflict = agents / profiles[0][0].name
        conflict.write_bytes(b"different")
        with self.assertRaises(installer.InstallError) as error:
            installer.install(str(self.root))
        self.assertEqual(error.exception.code, "HW_AGENT_CONFLICT")
        self.assertEqual(conflict.read_bytes(), b"different")
        extra = agents / "hwahap-extra.toml"
        extra.write_bytes(b"extra")
        with self.assertRaises(installer.InstallError) as error:
            installer.install(str(self.root))
        self.assertEqual(error.exception.code, "HW_AGENT_CONFLICT")
        self.assertEqual(extra.read_bytes(), b"extra")

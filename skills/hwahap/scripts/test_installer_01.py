try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import tomllib
import unittest


class InstallerContractTests(InstallerFixture, unittest.TestCase):
    def test_source_contract_and_byte_identical_install(self):
        profiles = self.profiles()
        self.assertEqual(len(profiles), 6)
        for path, raw in profiles:
            value = tomllib.loads(raw.decode())
            expected = installer.PROFILE_CONTRACT[path.name]
            self.assertEqual((value["name"], value["model"]), expected[:2])
        self.run_install()
        installed = {p.name: p.read_bytes() for p in self.agents().glob("*.toml")}
        self.assertEqual(installed, {p.name: raw for p, raw in profiles})
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.agents().glob("*.toml")))

    def test_idempotence_and_unrelated_config_preservation(self):
        agents = self.agents()
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

    def test_metadata_tamper_is_rejected_before_workspace_mutation(self):
        source = self.root / "source"
        source.mkdir()
        for path, raw in self.profiles():
            source.joinpath(path.name).write_bytes(raw)
        target = source / "hwahap-luna-verifier.toml"
        target.write_bytes(target.read_bytes().replace(b"independent verifier", b"tampered verifier"))
        with self.assertRaises(installer.InstallError) as error:
            installer.source_profiles(source)
        self.assertEqual(error.exception.code, "HW_AGENT_SOURCE_INVALID")

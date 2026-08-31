try:
    from .test_installer_faultkit import InstallerFaultMixin, installer
except ImportError:
    from test_installer_faultkit import InstallerFaultMixin, installer
import unittest
from unittest.mock import patch


class UpstreamInstallerSourceTests(InstallerFaultMixin, unittest.TestCase):
    def test_source_set_and_metadata_are_validated_before_workspace_mutation(self):
        source = self.root / "one-profile-source"
        source.mkdir()
        source.joinpath("hwahap-luna-implementer.toml").write_bytes(installer.source_profiles()[0][1])
        with patch.object(installer, "PROFILE_DIR", source):
            with self.assertRaises(installer.InstallError) as raised:
                self.run_install()
        self.assertEqual(raised.exception.code, "HW_AGENT_SOURCE_INVALID")
        self.assertFalse((self.root / ".codex").exists())

    def test_source_profile_instructions_are_digest_pinned(self):
        source = self.root / "instruction-tamper-source"
        source.mkdir()
        for path, raw in installer.source_profiles():
            if path.name == "hwahap-luna-verifier.toml":
                raw = raw.replace(b"independent verifier", b"independent executor")
            (source / path.name).write_bytes(raw)
        with self.assertRaises(installer.InstallError) as raised:
            installer.source_profiles(source)
        self.assertEqual(raised.exception.code, "HW_AGENT_SOURCE_INVALID")
        source = self.root / "bad-metadata-source"
        source.mkdir()
        for path, raw in installer.source_profiles():
            (source / path.name).write_bytes(raw.replace(b'model = "gpt-5.6-luna"', b'model = "wrong"'))
        with patch.object(installer, "PROFILE_DIR", source):
            self.assert_code("HW_AGENT_SOURCE_INVALID")
        self.assertFalse((self.root / ".codex").exists())

    def test_source_profiles_reject_casefolded_hwahap_extras(self):
        source = self.root / "case-variant-source"
        source.mkdir()
        for path, raw in installer.source_profiles():
            (source / path.name).write_bytes(raw)
        (source / "user-agent.toml").write_bytes(b"name = 'unrelated'\n")
        for name in ("HWAHAP-extra.toml", "HWAHAP-extra.TOML"):
            (source / name).write_bytes(b"name = 'extra'\n")
            with self.assertRaises(installer.InstallError) as raised:
                installer.source_profiles(source)
            self.assertEqual(raised.exception.code, "HW_AGENT_SOURCE_INVALID")
            with patch.object(installer, "PROFILE_DIR", source):
                self.assert_code("HW_AGENT_SOURCE_INVALID")
            self.assertFalse((self.root / ".codex").exists())
            (source / name).unlink()
        self.assertEqual({path.name for path, _ in installer.source_profiles(source)}, installer.REQUIRED_PROFILE_NAMES)

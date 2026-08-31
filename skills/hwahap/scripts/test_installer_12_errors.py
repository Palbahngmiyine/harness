try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


class InstallerErrorTests(InstallerFixture, unittest.TestCase):
    def test_source_and_cli_errors_are_generic_and_secret_free(self):
        marker = "Authorization: Bearer /private/tmp/source-canary"
        with patch.object(Path, "iterdir", side_effect=OSError(marker)):
            with self.assertRaises(installer.InstallError) as raised:
                installer.source_profiles()
        self.assertEqual(raised.exception.code, "HW_AGENT_SOURCE_INVALID")
        self.assertNotIn(marker, str(raised.exception))
        stderr = io.StringIO()
        with patch.object(installer, "install", side_effect=OSError(marker)):
            with redirect_stderr(stderr):
                self.assertEqual(installer.main(["--workspace", str(self.root)]), 1)
        self.assertEqual(stderr.getvalue(),
                         "HW_AGENT_INSTALL_FAILED: profile installation failed\n")
        self.assertNotIn(marker, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

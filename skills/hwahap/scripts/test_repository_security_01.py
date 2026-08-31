try:
    from .test_repository_security_kit import *
except ImportError:
    from test_repository_security_kit import *


class RepositorySecuritySlice1Tests(unittest.TestCase):
    def test_generated_state_and_implementation_prfaq_are_not_tracked(self) -> None:
        git = shutil.which("git", path=os.defpath)
        self.assertIsNotNone(git)
        tracked = subprocess.run([git, "ls-files", "-z"], cwd=REPOSITORY, capture_output=True, check=True).stdout.decode("utf-8").split("\0")
        self.assertFalse(any(path == ".hwahap" or path.startswith(".hwahap/") for path in tracked))
        self.assertFalse(any(path == "docs/prfaq" or path.startswith("docs/prfaq/") for path in tracked))

    def test_production_files_have_no_embedded_authentication_material(self) -> None:
        for path in PRODUCTION_FILES:
            with self.subTest(path=path.relative_to(REPOSITORY)):
                self.assertEqual(text_findings(path.read_text(encoding="utf-8")), [])
                if path.suffix == ".py":
                    self.assertEqual(python_literal_findings(path), [])

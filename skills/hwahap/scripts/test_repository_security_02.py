try:
    from .test_repository_security_kit import *
except ImportError:
    from test_repository_security_kit import *


class RepositorySecuritySlice2Tests(unittest.TestCase):
    def test_scanner_detects_constructed_regression_samples(self) -> None:
        samples = ("https://" + "user" + ":" + "pass" + "@example.invalid", "gh" + "p_" + "A1" * 18, "-----BEGIN " + "PRIVATE KEY-----")
        for sample in samples:
            self.assertTrue(text_findings(sample))

    def test_workflows_pin_actions_and_use_read_only_permissions(self) -> None:
        workflows = sorted((REPOSITORY / ".github/workflows").glob("*.yml"))
        self.assertTrue(workflows)
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("pull_request_target:", text)
                self.assertIn("permissions:\n  contents: read\n", text)
                refs = re.findall(r"(?m)^\s*uses:\s*[^@\s]+@([^\s#]+)", text)
                self.assertTrue(refs)
                self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs))
        self.assertTrue((REPOSITORY / ".github/dependabot.yml").is_file())

try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *


class ReportSlice48Tests(HwahapReportTests):
    def test_standalone_provider_and_high_entropy_tokens_are_redacted(self) -> None:
        provider_tokens = ("gh" + "p_" + "A1" * 18, "sk-" + "proj-" + "aB3_" * 6,
                           "xox" + "b-" + "Ab3" * 8, "npm" + "_" + "Ab3" * 7,
                           "sk_" + "live_" + "Ab3" * 6, "AI" + "za" + "Ab3_" * 8 + "Ab3",
                           "AK" + "IA" + "A1" * 8, "Ab3dEf5h" + "Ij7kLm9n" + "Op2qRs4t" + "Uv6wXy8z+/=")
        for token in provider_tokens:
            with self.subTest(token_type=token[:4]):
                self.assertTrue(state.contains_sensitive_data(token))
                self.assertTrue(report.contains_sensitive_data(token))
                self.assertNotIn(token, report._text(token))
        for safe in ("token_total=3", "a" * 40, "sha256:" + "a" * 64):
            self.assertFalse(state.contains_sensitive_data(safe))
            self.assertFalse(report.contains_sensitive_data(safe))

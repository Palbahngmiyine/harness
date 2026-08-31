try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *


class ReportSlice45Tests(HwahapReportTests):
    def test_cards_use_explicit_material_variants_without_blanket_outlines(self) -> None:
        contract, run, units, events, digests = self.fixture()
        run["deviations"] = [{"summary": "finding", "root_cause": "cause", "impact": "impact",
                              "prevention": "fix", "evidence": ["receipt"],
                              "evidence_explanation": "matrix가 중첩 입력 거부를 검증함"}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
        style = report.STYLE_BLOCK
        self.assertIn(".panel{min-width:0;overflow:hidden}", style)
        self.assertIn(".md-card{min-width:0;border-radius:var(--md-sys-shape-corner-medium);overflow:hidden}", style)
        self.assertIn(".md-card-filled{background:var(--md-sys-color-surface-container-highest);box-shadow:var(--md-sys-elevation-level0)}", style)
        self.assertIn(".md-card-elevated{background:var(--md-sys-color-surface-container-low);box-shadow:var(--md-sys-elevation-level1)}", style)
        self.assertNotIn(".md-card-outlined", style)
        self.assertNotIn(".card,.receipt,.proposal-card,.risk-card{min-width:0;padding:var(--space-5);border", style)
        self.assertNotIn(".evidence-vault{border:1px", style)
        self.assertNotIn("border-block-start:4px solid var(--md-sys-color-secondary)", style)
        self.assertNotIn("border-block-start:4px solid var(--md-sys-color-error)", style)
        self.assertNotIn("border-inline-start:4px solid var(--md-sys-color-primary)", style)
        self.assertIn('class="outcome-panel panel md-card md-card-elevated"', text)
        self.assertIn('class="change-card panel md-card md-card-filled"', text)
        self.assertIn('class="card md-card md-card-filled"', text)
        self.assertIn('.evidence-rationale{margin:0 var(--space-5) var(--space-5)', style)
        self.assertIn('background:var(--md-sys-color-secondary-container)', style)
        self.assertNotIn('.evidence-rationale{border', style)
        self.assertIn('<div class="evidence-rationale"><span class="field-label">왜 이 검사로 개선됐다고 판단했나</span>', text)

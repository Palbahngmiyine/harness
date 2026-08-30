try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice1Tests(HwahapReportTests):
    def test_static_report_has_required_sections_and_material3_contract(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            self.assertTrue(report.validate_report_bytes(data, digest, payload))
            text = data.decode()
            self.assertIn('<h1>Hwahap 실행 결과</h1>', text)
            self.assertIn('<meta name="material-design-system" content="Material Design 3">', text)
            self.assertIn('--md-sys-color-primary', text)
            self.assertIn('--md-sys-typescale-display-large', text)
            self.assertIn('--md-sys-shape-corner-extra-extra-large', text)
            self.assertIn('--md-sys-elevation-level1', text)
            self.assertIn('--md-sys-motion-standard-effects', text)
            self.assertIn('prefers-color-scheme:dark', text)
            self.assertIn('prefers-contrast:more', text)
            self.assertIn('prefers-reduced-motion:reduce', text)
            self.assertNotIn('Astryx', text)
            self.assertNotIn('<script', text)
            self.assertNotIn('<link', text)
            self.assertIn('id="agents"', text)
            self.assertIn('gpt-5.6-sol', text)
            self.assertIn('final', text)
            self.assertIn('Acceptance commands', text)
            self.assertIn('확인 가능 여부', text)
            self.assertIn('viewport', text)
            self.assertIn('platform aggregate not exposed', text)
            self.assertIn('총 토큰', text)
            self.assertIn('확인할 수 없음', text)
            self.assertIn('기록 없음', text)
            self.assertNotIn('>None<', text)
            self.assertNotIn("{'availability':", text)
            for label in ('목표', '제외 범위', '허용 경로', '금지 변경', '완료 기준', '테스트 명령', '작업 단위', '에이전트 실행', '검수 회차', '확인 가능 여부', '사유'):
                self.assertIn(label, text)
            self.assertIn('class="table-wrap"', text)
            self.assertNotIn('<pre>', text)
            for semantic in ('summary-grid', '<nav class="section-nav"', '<details id="evidence-vault"',
                             '<ol class="timeline">', '<caption>', '<table>', '<dl>'):
                self.assertIn(semantic, text)

class ReportSlice2Tests(HwahapReportTests):
    def test_report_css_wraps_long_tokens_and_preserves_table_scroll_contract(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            text = report.render_report(payload, digest).decode()
            self.assertIn("body{margin:0;background:var(--md-sys-color-surface);color:var(--md-sys-color-on-surface);font:var(--md-sys-typescale-body-large);overflow-wrap:anywhere}", text)
            self.assertIn(".table-wrap{max-width:100%;overflow-x:auto", text)
            self.assertIn("table{border-collapse:collapse;width:100%;min-width:700px", text)
            self.assertIn("td,th{padding:var(--md-sys-spacing-3);text-align:start;vertical-align:top;overflow-wrap:anywhere", text)
            self.assertIn("@media (max-width:599px)", text)
            self.assertIn("@media (min-width:600px) and (max-width:839px)", text)
            self.assertIn("@media (min-width:840px)", text)
            self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))

class ReportSlice3Tests(HwahapReportTests):
    def test_material3_tokens_cover_foundations_and_accessible_color_pairs(self) -> None:
            style = report.STYLE_BLOCK
            for role in ("display", "headline", "title", "body", "label"):
                for size in ("large", "medium", "small"):
                    self.assertIn(f"--md-sys-typescale-{role}-{size}:", style)
            for shape in ("extra-small", "small", "medium", "large", "extra-large",
                          "extra-extra-large", "full"):
                self.assertIn(f"--md-sys-shape-corner-{shape}:", style)
            for foundation in ("--md-sys-color-primary", "--md-sys-elevation-level1",
                               "--md-sys-spacing-4", "--md-sys-motion-standard-effects"):
                self.assertIn(foundation, style)
            light_pairs = (
                ("#fff", "#65558f"), ("#201047", "#e9ddff"), ("#1d192b", "#e8def8"),
                ("#31111d", "#ffd8e4"), ("#410e0b", "#f9dedc"), ("#1d1b20", "#fff7ff"),
                ("#49454f", "#e7e0ec"), ("#042100", "#b7f397"), ("#221b00", "#ffe170"),
            )
            dark_pairs = (
                ("#cfbdfe", "#36275d"), ("#e9ddff", "#4d3f75"), ("#cbc2db", "#332d41"),
                ("#e8def8", "#4a4458"), ("#efb8c8", "#492532"), ("#ffd8e4", "#633b48"),
                ("#f2b8b5", "#601410"), ("#f9dedc", "#8c1d18"), ("#e6e0e9", "#141218"),
                ("#cac4d0", "#49454f"), ("#b7f397", "#24510b"), ("#ffe170", "#574600"),
            )
            for foreground, background in (*light_pairs, *dark_pairs):
                with self.subTest(foreground=foreground, background=background):
                    self.assertGreaterEqual(_contrast(foreground, background), 4.5)

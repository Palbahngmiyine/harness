try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *


class ReportSlice3Tests(HwahapReportTests):
    def test_icy_blue_material_roles_scales_and_accessible_color_pairs(self) -> None:
        style = report.STYLE_BLOCK
        color_roles = (
            "--md-sys-color-primary:#007acc", "--md-sys-color-on-primary:#fff",
            "--md-sys-color-primary-container:#ccebff", "--md-sys-color-on-primary-container:#001f33",
            "--md-sys-color-secondary:#005c99", "--md-sys-color-tertiary:#003d66",
            "--md-sys-color-error:#b3261e", "--md-sys-color-error-container:#f9dedc",
            "--md-sys-color-surface:#fbfdff", "--md-sys-color-surface-container-lowest:#fff",
            "--md-sys-color-surface-container-low:#f7fcff", "--md-sys-color-surface-container:#f1faff",
            "--md-sys-color-surface-container-high:#ebf8ff", "--md-sys-color-surface-container-highest:#e5f5ff",
            "--md-sys-color-on-surface:#001f33", "--md-sys-color-on-surface-variant:#003d66",
            "--md-sys-color-outline:#005c99", "--md-sys-color-outline-variant:#99d6ff",
            "--md-sys-color-primary:#66c2ff", "--md-sys-color-surface:#001524",
            "--md-sys-color-surface-container-highest:#003d66", "--md-sys-color-on-surface:#e5f5ff",
        )
        for token in color_roles:
            self.assertIn(token, style)
        for obsolete in ("#6750a4", "#eaddff", "#fffbfe", "#f7f2fa"):
            self.assertNotIn(obsolete, style)
        for role in ("display", "headline", "title", "body", "label"):
            for size in ("large", "medium", "small"):
                self.assertIn(f"--md-sys-typescale-{role}-{size}:", style)
        for shape in ("none", "extra-small", "small", "medium", "large", "large-increased",
                      "extra-large", "extra-large-increased", "extra-extra-large", "full"):
            self.assertIn(f"--md-sys-shape-corner-{shape}:", style)
        for foundation in ("--md-sys-elevation-level0", "--md-sys-elevation-level1",
                           "--md-sys-motion-standard-effects", "--md-sys-state-hover-opacity:.08",
                           "--md-sys-state-focus-opacity:.10", "--md-sys-state-pressed-opacity:.10"):
            self.assertIn(foundation, style)
        light_pairs = (("#001f33", "#fbfdff"), ("#003d66", "#fbfdff"), ("#ffffff", "#007acc"),
                       ("#001f33", "#ccebff"), ("#001f33", "#e5f5ff"), ("#001524", "#99d6ff"),
                       ("#410e0b", "#f9dedc"), ("#0a3818", "#b8f2c5"), ("#2a2000", "#ffe16f"))
        dark_pairs = (("#e5f5ff", "#001524"), ("#ccebff", "#001524"), ("#001f33", "#66c2ff"),
                      ("#e5f5ff", "#005c99"), ("#001524", "#99d6ff"), ("#ccebff", "#003d66"),
                      ("#001f33", "#33adff"), ("#ffffff", "#007acc"), ("#f9dedc", "#8c1d18"),
                      ("#b8f2c5", "#0a3818"), ("#ffe16f", "#4c3d00"))
        for foreground, background in (*light_pairs, *dark_pairs):
            with self.subTest(foreground=foreground, background=background):
                self.assertGreaterEqual(_contrast(foreground, background), 4.5)

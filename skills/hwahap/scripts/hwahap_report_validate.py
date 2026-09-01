"""Validate canonical report HTML."""

import html

from hwahap_report_assets import META_STATIC, STYLE_BLOCK
from hwahap_report_canonical import validate_payload
from hwahap_report_ledger import payload_ledger_block
from hwahap_report_parser import ReportContentParser
from hwahap_report_security import credential_bearing_text
from hwahap_report_types import REPORT_IDS

STATIC_IDS = frozenset((*REPORT_IDS, "report", "evidence-vault"))
MATERIAL = (
    '<meta name="material-design-system" content="Material Design 3">',
    "--md-sys-color-primary", "--md-sys-color-on-primary",
    "--md-sys-typescale-display-large", "--md-sys-typescale-headline-medium",
    "--md-sys-typescale-title-large", "--md-sys-typescale-body-large",
    "--md-sys-typescale-label-large", "--md-sys-shape-corner-extra-small",
    "--md-sys-shape-corner-extra-extra-large", "--md-sys-elevation-level1",
    "--md-sys-motion-standard-effects", "prefers-color-scheme:dark",
    "prefers-contrast:more", "prefers-reduced-motion:reduce",
    "@media (max-width:599px)", "@media (min-width:600px) and (max-width:839px)",
    "@media (min-width:840px)", "@media (min-width:1200px)",
    "@media (min-width:1600px)", '<a class="skip-link" href="#summary">',
    'aria-label="보고서 주요 항목"', "오케스트레이션 절차 편차와 재발 방지",
    "절차 영향", "발생 원인", "재발 방지", "예방 효과의 한계",
    "아직 남은 위험", "다음에 개선할 수 있는 것",
    '<details id="evidence-vault" class="evidence-vault">',
)
ORDER = ("summary", "deviations", "improvement-candidates", "next-actions",
         "tests-metrics", "evidence-vault", "contract", "agents", "units",
         "timeline", "reviews", "scope-audit", "failures-recovery",
         "provenance", "report-data")


def validate_report_bytes(data: bytes, source_digest: str, payload: dict) -> bool:
    validate_payload(payload, source_digest)
    text = data.decode("utf-8")
    parser = ReportContentParser()
    parser.feed(text)
    parser.close()
    if text.count(payload_ledger_block(payload)) != 1:
        raise ValueError("report data ledger mismatch")
    unsafe = any(credential_bearing_text(value) for value in parser.values)
    unsafe = unsafe or any(credential_bearing_text("".join(segment))
                           for segment in parser.text_segments if segment)
    if unsafe:
        raise ValueError("credential-bearing report content is unsafe")
    source_meta = f'<meta name="hwahap-source-sha256" content="{html.escape(source_digest, quote=True)}">'
    if parser.tag_counts.get("meta") != len(META_STATIC) + 1 \
            or parser.tag_counts.get("script", 0) or parser.tag_counts.get("link", 0) \
            or parser.tag_counts.get("style") != 1:
        raise ValueError("report static structure count mismatch")
    if any(text.count(fragment) != 1 for fragment in (*META_STATIC, source_meta, STYLE_BLOCK)):
        raise ValueError("report static structure mismatch")
    for ident in REPORT_IDS:
        if f'id="{ident}"' not in text:
            raise ValueError(f"missing report section: {ident}")
    if len(parser.id_values) != len(STATIC_IDS) or set(parser.id_values) != STATIC_IDS:
        raise ValueError("report ids are not unique or complete")
    if any(fragment not in text for fragment in MATERIAL):
        raise ValueError("Material 3 report contract is incomplete")
    if any(value in text for value in ("Astryx", "astryx", "ReactDOM", "react-dom",
                                        "importmap", "<script")):
        raise ValueError("legacy report dependency remains")
    positions = [text.find(f'id="{ident}"') for ident in ORDER]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise ValueError("report reading order is invalid")
    return True

"""Build a static, redacted Hwahap report using Material 3 foundations."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import stat
import sys
import types
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

class HwahapReportError(ValueError):
    """Stable direct-report validation error."""

_PIN_REDACTION_ENGINE_SHA256 = "aa2d19d5b4f6af13cc2a53c6d91bda453713d3526a02efe561b6fd939691e687"
_redaction_module = None

def _sealed_module(filename: str, digest: str, exports: tuple[str, ...], error: str):
    directory = Path(__file__).parent
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    fd = dfd = None
    try:
        dfd = os.open(str(directory), flags)
        d_before = os.fstat(dfd)
        fd = os.open(filename, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=dfd)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid not in (0, os.geteuid())
                or not before.st_mode & 0o444 or before.st_mode & 0o022 or before.st_size > 2 * 1024 * 1024):
            raise ValueError
        data = bytearray()
        while len(data) <= before.st_size:
            chunk = os.read(fd, min(65536, before.st_size + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        d_after = os.fstat(dfd)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        if len(data) != before.st_size or identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or (d_before.st_dev, d_before.st_ino) != (d_after.st_dev, d_after.st_ino):
            raise ValueError
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest):
            raise ValueError
        module = types.ModuleType("_hwahap_sealed_" + filename.replace(".py", ""))
        module.__file__ = str(directory / filename)
        sys.modules[module.__name__] = module
        try:
            exec(compile(bytes(data), "<hwahap-sealed>", "exec"), module.__dict__)
        finally:
            sys.modules.pop(module.__name__, None)
        if any(not hasattr(module, name) for name in exports):
            raise ValueError
        return module
    except Exception:
        raise ImportError(error) from None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        if dfd is not None:
            try:
                os.close(dfd)
            except Exception:
                pass

def _ensure_redaction() -> None:
    global _redaction_module, _shared_contains_sensitive_data, _shared_redact
    if _redaction_module is not None:
        return
    try:
        module = _sealed_module("hwahap_redaction.py", _PIN_REDACTION_ENGINE_SHA256, ("contains_sensitive_data", "redact"), "redaction dependency unavailable")
    except ImportError:
        raise HwahapReportError("report redaction dependency unavailable") from None
    _redaction_module = module
    _shared_contains_sensitive_data, _shared_redact = module.contains_sensitive_data, module.redact

_shared_contains_sensitive_data = _shared_redact = None


EVENT_FIELDS = ("timestamp", "type", "sequence", "entity", "from", "to", "actor", "role", "reason", "input_digest", "evidence_refs", "review_round")
CONTRACT_LISTS = ("goals", "non_goals", "allowed_paths", "forbidden_changes", "acceptance_criteria", "test_commands")
REPORT_IDS = ("summary", "report-data", "contract", "agents", "units", "timeline", "reviews", "scope-audit", "tests-metrics", "failures-recovery", "deviations", "provenance", "improvement-candidates", "next-actions")
REPORT_STATIC_IDS = frozenset((*REPORT_IDS, "report", "evidence-vault"))
REPORT_TAGS = frozenset(("a", "article", "aside", "body", "br", "caption", "dd", "details", "div", "dl", "dt", "footer", "h1", "h2", "h3", "head", "header", "html", "li", "main", "meta", "nav", "ol", "p", "section", "small", "span", "strong", "style", "summary", "table", "tbody", "td", "th", "thead", "time", "title", "tr", "ul"))
REPORT_ATTRS = frozenset(("aria-label", "aria-live", "charset", "class", "colspan", "content", "href", "id", "lang", "name", "scope"))
REPORT_TEXT_BOUNDARIES = frozenset(("a", "article", "aside", "body", "br", "caption", "dd", "details", "div", "dl", "dt", "footer", "h1", "h2", "h3", "head", "header", "html", "li", "main", "nav", "ol", "p", "section", "strong", "summary", "table", "tbody", "td", "th", "thead", "time", "title", "tr", "ul"))
DIFF_SNAPSHOT_FIELDS = ("base_commit", "target_commit", "base_tree", "target_tree", "diff_digest", "changed_paths")
DECISION_CONTEXT_FIELDS = ("scenario", "affected_scope", "impact", "decision_reason", "evidence_relation", "success_condition")
IMPROVEMENT_CANDIDATE_FIELDS = ("status", "summary", "evidence", "expected_effect", "next_action", "decision_context")
CONTRACT_LABELS = {"goals": "목표", "non_goals": "제외 범위", "allowed_paths": "허용 경로", "forbidden_changes": "금지 변경", "acceptance_criteria": "완료 기준", "test_commands": "테스트 명령"}
METRIC_LABELS = {"unit_count": "작업 단위", "agent_runs": "에이전트 실행", "review_rounds": "검수 회차", "recoveries": "복구", "replans": "재계획", "scope_deviations": "범위 편차", "test_runs": "기록된 테스트 실행 수", "elapsed_seconds": "기록된 소요 시간(초)", "availability": "확인 가능 여부", "reason": "사유", "source": "출처", "total": "총 토큰"}
AVAILABILITY_LABELS = {"available": "확인됨", "unavailable": "확인할 수 없음"}
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
ABS_PATH = re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s<>\"']+/)+[^\s<>\"']+")
STYLE_BLOCK = """<style>
:root{color-scheme:light dark;--md-sys-color-primary:#007acc;--md-sys-color-on-primary:#fff;--md-sys-color-primary-container:#ccebff;--md-sys-color-on-primary-container:#001f33;--md-sys-color-secondary:#005c99;--md-sys-color-on-secondary:#fff;--md-sys-color-secondary-container:#e5f5ff;--md-sys-color-on-secondary-container:#001f33;--md-sys-color-tertiary:#003d66;--md-sys-color-on-tertiary:#fff;--md-sys-color-tertiary-container:#99d6ff;--md-sys-color-on-tertiary-container:#001524;--md-sys-color-error:#b3261e;--md-sys-color-on-error:#fff;--md-sys-color-error-container:#f9dedc;--md-sys-color-on-error-container:#410e0b;--md-sys-color-surface:#fbfdff;--md-sys-color-surface-container-lowest:#fff;--md-sys-color-surface-container-low:#f7fcff;--md-sys-color-surface-container:#f1faff;--md-sys-color-surface-container-high:#ebf8ff;--md-sys-color-surface-container-highest:#e5f5ff;--md-sys-color-on-surface:#001f33;--md-sys-color-on-surface-variant:#003d66;--md-sys-color-outline:#005c99;--md-sys-color-outline-variant:#99d6ff;--hwahap-color-success:#146c2e;--hwahap-color-success-container:#b8f2c5;--hwahap-color-on-success-container:#0a3818;--hwahap-color-warning:#745b00;--hwahap-color-warning-container:#ffe16f;--hwahap-color-on-warning-container:#2a2000;--md-ref-typeface-brand:Roboto,"Noto Sans KR",system-ui,-apple-system,BlinkMacSystemFont,sans-serif;--md-ref-typeface-plain:Roboto,"Noto Sans KR",system-ui,-apple-system,BlinkMacSystemFont,sans-serif;--md-ref-typeface-mono:"Roboto Mono","SFMono-Regular",ui-monospace,Menlo,monospace;--md-sys-typescale-display-large:400 3.5625rem/4rem var(--md-ref-typeface-brand);--md-sys-typescale-display-medium:400 2.8125rem/3.25rem var(--md-ref-typeface-brand);--md-sys-typescale-display-small:400 2.25rem/2.75rem var(--md-ref-typeface-brand);--md-sys-typescale-headline-large:400 2rem/2.5rem var(--md-ref-typeface-brand);--md-sys-typescale-headline-medium:400 1.75rem/2.25rem var(--md-ref-typeface-brand);--md-sys-typescale-headline-small:400 1.5rem/2rem var(--md-ref-typeface-brand);--md-sys-typescale-title-large:400 1.375rem/1.75rem var(--md-ref-typeface-brand);--md-sys-typescale-title-medium:500 1rem/1.5rem var(--md-ref-typeface-plain);--md-sys-typescale-title-small:500 .875rem/1.25rem var(--md-ref-typeface-plain);--md-sys-typescale-body-large:400 1rem/1.5rem var(--md-ref-typeface-plain);--md-sys-typescale-body-medium:400 .875rem/1.25rem var(--md-ref-typeface-plain);--md-sys-typescale-body-small:400 .75rem/1rem var(--md-ref-typeface-plain);--md-sys-typescale-label-large:500 .875rem/1.25rem var(--md-ref-typeface-plain);--md-sys-typescale-label-medium:500 .75rem/1rem var(--md-ref-typeface-plain);--md-sys-typescale-label-small:500 .6875rem/1rem var(--md-ref-typeface-plain);--md-sys-shape-corner-none:0;--md-sys-shape-corner-extra-small:4px;--md-sys-shape-corner-small:8px;--md-sys-shape-corner-medium:12px;--md-sys-shape-corner-large:16px;--md-sys-shape-corner-large-increased:20px;--md-sys-shape-corner-extra-large:28px;--md-sys-shape-corner-extra-large-increased:32px;--md-sys-shape-corner-extra-extra-large:48px;--md-sys-shape-corner-full:9999px;--md-sys-elevation-level0:none;--md-sys-elevation-level1:0 1px 2px rgb(0 31 51/.18),0 1px 3px 1px rgb(0 31 51/.08);--md-sys-motion-standard-effects:150ms cubic-bezier(.2,0,0,1);--md-sys-motion-standard-spatial:250ms cubic-bezier(.2,0,0,1);--md-sys-state-hover-opacity:.08;--md-sys-state-focus-opacity:.10;--md-sys-state-pressed-opacity:.10;--space-1:4px;--space-2:8px;--space-3:12px;--space-4:16px;--space-5:20px;--space-6:24px;--space-8:32px;--space-10:40px;--space-12:48px;--layout-max:1440px;--layout-margin:16px;--section-space:48px}
@media (prefers-color-scheme:dark){:root{--md-sys-color-primary:#66c2ff;--md-sys-color-on-primary:#001f33;--md-sys-color-primary-container:#005c99;--md-sys-color-on-primary-container:#e5f5ff;--md-sys-color-secondary:#99d6ff;--md-sys-color-on-secondary:#001524;--md-sys-color-secondary-container:#003d66;--md-sys-color-on-secondary-container:#ccebff;--md-sys-color-tertiary:#33adff;--md-sys-color-on-tertiary:#001f33;--md-sys-color-tertiary-container:#007acc;--md-sys-color-on-tertiary-container:#fff;--md-sys-color-error:#f2b8b5;--md-sys-color-on-error:#601410;--md-sys-color-error-container:#8c1d18;--md-sys-color-on-error-container:#f9dedc;--md-sys-color-surface:#001524;--md-sys-color-surface-container-lowest:#000d16;--md-sys-color-surface-container-low:#001a2c;--md-sys-color-surface-container:#001f33;--md-sys-color-surface-container-high:#002b47;--md-sys-color-surface-container-highest:#003d66;--md-sys-color-on-surface:#e5f5ff;--md-sys-color-on-surface-variant:#ccebff;--md-sys-color-outline:#99d6ff;--md-sys-color-outline-variant:#005c99;--hwahap-color-success:#8dd99b;--hwahap-color-success-container:#0a3818;--hwahap-color-on-success-container:#b8f2c5;--hwahap-color-warning:#e9c349;--hwahap-color-warning-container:#4c3d00;--hwahap-color-on-warning-container:#ffe16f;--md-sys-elevation-level1:0 1px 2px rgb(0 0 0/.3),0 1px 3px 1px rgb(0 0 0/.2)}}
@media (prefers-contrast:more){:root{--md-sys-color-primary:#003d66;--md-sys-color-on-primary:#fff;--md-sys-color-surface:#fff;--md-sys-color-surface-container-lowest:#fff;--md-sys-color-surface-container-low:#f7fcff;--md-sys-color-surface-container:#f1faff;--md-sys-color-surface-container-high:#e5f5ff;--md-sys-color-surface-container-highest:#ccebff;--md-sys-color-on-surface:#001524;--md-sys-color-on-surface-variant:#003d66;--md-sys-color-outline:#003d66;--md-sys-color-outline-variant:#005c99}}
@media (prefers-contrast:more) and (prefers-color-scheme:dark){:root{--md-sys-color-primary:#e5f5ff;--md-sys-color-on-primary:#001524;--md-sys-color-surface:#000;--md-sys-color-surface-container-lowest:#000;--md-sys-color-surface-container-low:#001524;--md-sys-color-surface-container:#001f33;--md-sys-color-surface-container-high:#003d66;--md-sys-color-surface-container-highest:#005c99;--md-sys-color-on-surface:#fff;--md-sys-color-on-surface-variant:#e5f5ff;--md-sys-color-outline:#e5f5ff;--md-sys-color-outline-variant:#99d6ff}}
*,*::before,*::after{box-sizing:border-box}html{overflow-x:hidden;background:var(--md-sys-color-surface);scroll-behavior:smooth}body{margin:0;min-width:0;min-height:100vh;background:var(--md-sys-color-surface);color:var(--md-sys-color-on-surface);font:var(--md-sys-typescale-body-large);letter-spacing:.03125rem;-webkit-font-smoothing:antialiased;overflow-wrap:anywhere}a{color:var(--md-sys-color-primary);text-underline-offset:.2em;text-decoration-thickness:.08em}a:focus-visible,summary:focus-visible{outline:3px solid var(--md-sys-color-primary);outline-offset:2px}.skip-link{position:fixed;z-index:20;inset-block-start:var(--space-2);inset-inline-start:var(--space-2);display:inline-flex;align-items:center;min-block-size:48px;padding-inline:var(--space-4);border-radius:var(--md-sys-shape-corner-full);background:var(--md-sys-color-primary);color:var(--md-sys-color-on-primary);transform:translateY(-160%)}.skip-link:focus{transform:translateY(0)}.top-app-bar{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:var(--space-4);min-block-size:64px;padding-block:var(--space-2);padding-inline:max(var(--layout-margin),calc((100vw - var(--layout-max))/2 + var(--layout-margin)));background:var(--md-sys-color-surface-container);border-block-end:1px solid var(--md-sys-color-outline-variant)}.app-title{font:var(--md-sys-typescale-title-large)}.app-kicker,.eyebrow{color:var(--md-sys-color-primary);font:var(--md-sys-typescale-label-medium);letter-spacing:.0625rem}.section-nav{max-width:var(--layout-max);margin:0 auto;padding:var(--space-3) var(--layout-margin);display:flex;gap:var(--space-2);overflow-x:auto;scrollbar-width:thin;scroll-padding-inline:var(--layout-margin)}.nav-chip{--state-layer-color:var(--md-sys-color-on-secondary-container);position:relative;isolation:isolate;overflow:hidden;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;min-block-size:48px;padding-inline:var(--space-4);white-space:nowrap;border:1px solid var(--md-sys-color-outline);border-radius:var(--md-sys-shape-corner-full);background:var(--md-sys-color-surface);color:var(--md-sys-color-on-surface);font:var(--md-sys-typescale-label-large);text-decoration:none}.nav-chip::after,details>summary::after{content:"";position:absolute;z-index:-1;inset:0;background:var(--state-layer-color,currentColor);opacity:0;pointer-events:none;transition:opacity var(--md-sys-motion-standard-effects)}.nav-chip:hover::after,details>summary:hover::after{opacity:var(--md-sys-state-hover-opacity)}.nav-chip:focus-visible::after,details>summary:focus-visible::after{opacity:var(--md-sys-state-focus-opacity)}.nav-chip:active::after,details>summary:active::after{opacity:var(--md-sys-state-pressed-opacity)}main{max-width:var(--layout-max);margin-inline:auto;padding:0 var(--layout-margin) 80px}main>section,main>.decision-layout,main>.evidence-vault{margin-block:var(--section-space)}section{scroll-margin-block-start:80px}h1,h2,h3,p{margin-block-start:0}h1,h2,h3{font-family:var(--md-ref-typeface-brand);letter-spacing:0}h1{margin-block-end:var(--space-4);font:var(--md-sys-typescale-display-small)}h2{margin-block-end:var(--space-4);font:var(--md-sys-typescale-headline-medium)}h3{margin-block-end:var(--space-3);font:var(--md-sys-typescale-title-large)}p{max-width:60ch}.section-intro{max-width:60ch;color:var(--md-sys-color-on-surface-variant);font:var(--md-sys-typescale-body-large)}.hero{display:grid;gap:var(--space-8);align-items:center;padding-block:var(--space-8)}.hero-copy-block{max-width:60ch}.stack>*+*{margin-block-start:var(--space-4)}.hero-copy{max-width:60ch;color:var(--md-sys-color-on-surface-variant);font:var(--md-sys-typescale-title-large)}.panel{min-width:0;overflow:hidden}.md-card{min-width:0;border-radius:var(--md-sys-shape-corner-medium);overflow:hidden}.md-card-filled{background:var(--md-sys-color-surface-container-highest);box-shadow:var(--md-sys-elevation-level0)}.md-card-elevated{background:var(--md-sys-color-surface-container-low);box-shadow:var(--md-sys-elevation-level1)}.panel-head{display:flex;justify-content:space-between;align-items:center;gap:var(--space-4);padding:var(--space-5);background:var(--md-sys-color-primary-container);color:var(--md-sys-color-on-primary-container);border-block-end:1px solid var(--md-sys-color-outline-variant)}.panel-head .eyebrow{color:var(--md-sys-color-on-primary-container)}.panel-head h3{margin:0}.status-chip,.label-chip{display:inline-flex;align-items:center;gap:var(--space-2);min-block-size:32px;padding-inline:var(--space-3);border-radius:var(--md-sys-shape-corner-full);font:var(--md-sys-typescale-label-medium);letter-spacing:.03125rem}.status-chip::before{display:grid;place-items:center;inline-size:18px;block-size:18px;border:1px solid currentColor;border-radius:var(--md-sys-shape-corner-full);font-weight:700}.status-success{background:var(--hwahap-color-success-container);color:var(--hwahap-color-on-success-container)}.status-success::before{content:"✓"}.status-warning{background:var(--hwahap-color-warning-container);color:var(--hwahap-color-on-warning-container)}.status-warning::before{content:"!"}.status-error{background:var(--md-sys-color-error-container);color:var(--md-sys-color-on-error-container)}.status-error::before{content:"×"}.summary-grid{display:grid;background:var(--md-sys-color-surface-container-lowest)}.metric{min-width:0;padding:var(--space-5);border-block-end:1px solid var(--md-sys-color-outline-variant)}.metric:last-child{border-block-end:0}.metric-label,.field-label{display:block;margin-block-end:var(--space-1);color:var(--md-sys-color-on-surface-variant);font:var(--md-sys-typescale-label-medium)}.metric-value{display:block;font:var(--md-sys-typescale-title-large)}.cards,.metrics-grid,.proposal-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:var(--space-4);margin-block-start:var(--space-6)}.change-grid{display:grid;gap:var(--space-6);margin-block-start:var(--space-6)}.card,.receipt,.proposal-card,.risk-card{min-width:0;padding:var(--space-5)}.change-card-header{display:flex;align-items:center;justify-content:space-between;gap:var(--space-4);padding:var(--space-5);border-block-end:1px solid var(--md-sys-color-outline-variant)}.change-card-header h3{margin:0}.change-card-body{display:grid;padding-inline:var(--space-5)}.change-field{min-width:0;padding-block:var(--space-5)}.change-field+.change-field{border-block-start:1px solid var(--md-sys-color-outline-variant)}.expected-change{margin:0 var(--space-5) var(--space-5);padding:var(--space-4);border-radius:var(--md-sys-shape-corner-medium);background:var(--hwahap-color-success-container);color:var(--hwahap-color-on-success-container)}.notice{color:var(--md-sys-color-on-surface-variant);font:var(--md-sys-typescale-body-medium)}details{border-radius:var(--md-sys-shape-corner-large)}details>summary{--state-layer-color:var(--md-sys-color-primary);position:relative;isolation:isolate;overflow:hidden;cursor:pointer;list-style:none;display:flex;align-items:center;gap:var(--space-2);min-block-size:48px;padding:var(--space-3) var(--space-4);border:1px solid transparent;border-radius:var(--md-sys-shape-corner-full);color:var(--md-sys-color-primary);font:var(--md-sys-typescale-label-large)}details>summary::-webkit-details-marker{display:none}details>summary::before{content:"›";display:inline-grid;place-items:center;inline-size:24px;block-size:24px;font-size:1.5rem;transition:transform var(--md-sys-motion-standard-spatial)}details[open]>summary{background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container);border-color:var(--md-sys-color-outline)}details[open]>summary::before{transform:rotate(90deg)}.evidence-vault{border-radius:var(--md-sys-shape-corner-extra-large);background:var(--md-sys-color-surface-container-low)}.evidence-vault>summary{padding:var(--space-5);border-radius:var(--md-sys-shape-corner-extra-large);font:var(--md-sys-typescale-title-large)}.evidence-content{padding:0 var(--space-5) var(--space-5)}.evidence-content>section{margin-block:var(--space-12)}.empty{color:var(--md-sys-color-on-surface-variant);font-style:italic}ul,ol{padding-inline-start:1.4rem}.timeline{display:grid;gap:var(--space-3)}.timeline li{padding:var(--space-4);border-radius:var(--md-sys-shape-corner-medium);background:var(--md-sys-color-surface-container-highest)}dl{margin:0}dt{margin-block-start:var(--space-3);color:var(--md-sys-color-on-surface-variant);font:var(--md-sys-typescale-label-medium)}dd{margin-inline-start:0;min-width:0}.table-wrap{max-width:100%;overflow-x:auto;border:1px solid var(--md-sys-color-outline);border-radius:var(--md-sys-shape-corner-medium)}table{border-collapse:collapse;width:100%;min-width:700px;background:var(--md-sys-color-surface-container-lowest)}caption{padding:var(--space-3);text-align:start;color:var(--md-sys-color-on-surface-variant);font:var(--md-sys-typescale-title-medium)}td,th{padding:var(--space-3);text-align:start;vertical-align:top;overflow-wrap:anywhere;border-block-end:1px solid var(--md-sys-color-outline-variant)}th{background:var(--md-sys-color-surface-container);font:var(--md-sys-typescale-label-medium)}tbody tr:last-child td{border-block-end:0}.receipt-list{display:grid;gap:var(--space-4)}.receipt dl{display:grid;grid-template-columns:minmax(8rem,auto) 1fr;gap:var(--space-1) var(--space-3)}.snapshot{font-family:var(--md-ref-typeface-mono);font-size:.75rem}.supporting-pane>section{padding:var(--space-5);border-radius:var(--md-sys-shape-corner-large-increased);background:var(--md-sys-color-surface-container)}.report-footer{margin-block-start:var(--section-space);padding-block-start:var(--space-6);border-block-start:1px solid var(--md-sys-color-outline-variant);color:var(--md-sys-color-on-surface-variant);font:var(--md-sys-typescale-body-medium)}
.causal-chain{display:grid;gap:var(--space-3);margin-block:var(--space-5)}.causal-step{padding:var(--space-4);border-radius:var(--md-sys-shape-corner-small);background:var(--md-sys-color-surface-container-lowest)}.causal-step p{margin-block-end:0}.evidence-brief{margin:0 var(--space-4) var(--space-4);padding:var(--space-5);border-radius:var(--md-sys-shape-corner-medium);background:var(--md-sys-color-surface-container-low);color:var(--md-sys-color-on-surface)}.evidence-conclusion{font:var(--md-sys-typescale-title-medium)}.fivew3h-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:var(--space-3);margin-block:var(--space-5)}.fivew3h-grid>div{min-width:0;padding:var(--space-4);border-radius:var(--md-sys-shape-corner-small);background:var(--md-sys-color-surface-container-lowest)}.fivew3h-grid dt{margin-block-start:0;color:var(--md-sys-color-primary)}.evidence-source{padding-block-start:var(--space-4);border-block-start:1px solid var(--md-sys-color-outline-variant)}.evidence-limit{margin-block:var(--space-4) 0;padding:var(--space-4);border-radius:var(--md-sys-shape-corner-small);background:var(--md-sys-color-error-container);color:var(--md-sys-color-on-error-container)}.completion-judgment{padding:var(--space-5);border-radius:var(--md-sys-shape-corner-medium);background:var(--md-sys-color-primary-container);color:var(--md-sys-color-on-primary-container);font:var(--md-sys-typescale-title-medium)}.decision-list{display:grid;gap:var(--space-4);margin-block-start:var(--space-6)}.decision-item{padding:var(--space-5);border-radius:var(--md-sys-shape-corner-medium);background:var(--md-sys-color-surface-container-highest)}
.evidence-rationale{margin:0 var(--space-5) var(--space-5);padding:var(--space-4);border-radius:var(--md-sys-shape-corner-medium);background:var(--md-sys-color-secondary-container);color:var(--md-sys-color-on-secondary-container)}.evidence-rationale .field-label{margin-block-end:var(--space-2);color:inherit}.evidence-rationale p{max-width:none;margin:0;font:var(--md-sys-typescale-body-medium)}
@media (max-width:599px){.top-app-bar{min-block-size:56px}.change-card-header{align-items:flex-start;flex-direction:column}.evidence-content{padding-inline:var(--space-3)}.receipt dl{grid-template-columns:1fr}.evidence-brief{margin-inline:0;padding:var(--space-4)}}
@media (min-width:600px) and (max-width:839px){:root{--layout-margin:24px;--section-space:64px}.summary-grid{grid-template-columns:1fr 1fr}.metric:nth-child(odd){border-inline-end:1px solid var(--md-sys-color-outline-variant)}.metric:nth-last-child(-n+2){border-block-end:0}}
@media (min-width:840px){:root{--layout-margin:24px;--section-space:72px}.hero{grid-template-columns:minmax(0,1fr) minmax(300px,420px);gap:var(--space-10);padding-block:var(--space-12)}.summary-grid{grid-template-columns:1fr 1fr}.metric:nth-child(odd){border-inline-end:1px solid var(--md-sys-color-outline-variant)}.metric:nth-last-child(-n+2){border-block-end:0}.decision-layout{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(280px,.85fr);gap:var(--space-6);align-items:start}.supporting-pane{position:sticky;inset-block-start:var(--space-4)}}
@media (min-width:1200px){:root{--layout-margin:32px;--section-space:80px}.decision-layout{grid-template-columns:minmax(0,2fr) minmax(320px,1fr);gap:var(--space-8)}.change-card-body{grid-template-columns:repeat(3,minmax(0,1fr));padding:var(--space-5)}.change-field{padding:0 var(--space-5)}.change-field:first-child{padding-inline-start:0}.change-field:last-child{padding-inline-end:0}.change-field+.change-field{border-block-start:0;border-inline-start:1px solid var(--md-sys-color-outline-variant)}.proposal-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (min-width:1600px){:root{--layout-margin:48px;--section-space:96px}.decision-layout{grid-template-columns:minmax(0,2fr) minmax(360px,1fr)}}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before,*::after{animation:none!important;transition:none!important}}
@media print{.skip-link,.section-nav{display:none}.top-app-bar{position:static}.supporting-pane{position:static}.evidence-vault{border:none}.evidence-vault>summary{display:none}.evidence-vault>.evidence-content{display:block!important}.table-wrap{overflow:visible}body{background:#fff;color:#000}}
</style>"""
META_STATIC = ('<meta charset="utf-8">', '<meta name="viewport" content="width=device-width, initial-scale=1">', '<meta name="color-scheme" content="light dark">', '<meta name="material-design-system" content="Material Design 3">', '<meta name="material-theme-source" content="Material Design 3 official guidance">', '<meta name="color-theme-name" content="Icy Blue">', '<meta name="color-theme-seed" content="#C2E7FF">', '<meta name="color-theme-source" content="https://coolors.co/tailwind/c2e7ff">', '<meta name="material-foundations-pages" content="68">', '<meta name="material-source-url" content="https://m3.material.io/foundations">', '<meta name="material-spec-snapshot" content="2026-08-29">', '<meta name="hwahap-redaction-policy" content="credentials,authorization,bearer,api-key,private-key,password; bounded">')


def contains_sensitive_data(value: object) -> bool:
    if not isinstance(value, str):
        return False
    _ensure_redaction()
    return _shared_contains_sensitive_data(value)


def _text(value: Any, workspace: str = "") -> str:
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    _ensure_redaction()
    value = _shared_redact(value)
    root = workspace.rstrip("/")
    if root:
        value = re.sub(re.escape(root) + r"(?=/|$)", "$WORKSPACE", value)
    value = ABS_PATH.sub("[external reference]", value)
    return value.strip()


def _clean(value: Any, workspace: str = "") -> Any:
    if isinstance(value, str):
        return _text(value, workspace)
    if isinstance(value, list):
        return [_clean(item, workspace) for item in value]
    if isinstance(value, dict):
        return {str(key): _clean(item, workspace) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    return value


def _pick(value: Any, keys: tuple[str, ...], workspace: str) -> dict[str, Any]:
    return {key: _clean(value[key], workspace) for key in keys if isinstance(value, dict) and key in value}


def _snapshot(value: Any, workspace: str) -> dict[str, Any]:
    return _pick(value, DIFF_SNAPSHOT_FIELDS, workspace)


def _scope_audit(value: Any, workspace: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    result = {"authority": "derived-report-only",
              "affects_gate": False, "source_diff_digest": value.get("source_diff_digest"),
              "contract_lock_sha256": value.get("contract_lock_sha256"), "paths": []}
    for key in ("source_diff_digest", "contract_lock_sha256"):
        if not isinstance(result[key], str):
            result[key] = None
    for item in value.get("paths", []) if isinstance(value.get("paths"), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        path = {"path": _clean(item["path"], workspace),
                "contract_allowed": bool(item.get("contract_allowed")),
                "passed_unit_covered": bool(item.get("passed_unit_covered")),
                "forbidden_overlap": bool(item.get("forbidden_overlap")),
                "matched_contract_rules": _clean([rule for rule in item.get("matched_contract_rules", []) if isinstance(rule, str)], workspace),
                "matched_forbidden_rules": _clean([rule for rule in item.get("matched_forbidden_rules", []) if isinstance(rule, str)], workspace),
                "verdict": item.get("verdict") if item.get("verdict") in {"pass", "fail"} else "fail"}
        path["covering_passed_units"] = [
            {"unit_id": _clean(unit.get("unit_id"), workspace),
             "matched_rules": _clean(unit.get("matched_rules", []), workspace)}
            for unit in item.get("covering_passed_units", []) if isinstance(unit, dict)]
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        path["evidence"] = {"diff_digest": evidence.get("diff_digest"),
                            "contract_lock_sha256": evidence.get("contract_lock_sha256"),
                            "passed_unit_ids": [unit_id for unit_id in evidence.get("passed_unit_ids", [])
                                                 if isinstance(unit_id, str)]}
        result["paths"].append(path)
    return result


def _command_receipts(value: Any, prefix: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [{"name": f"{prefix}-{index}", "sha256": "sha256:" + hashlib.sha256(command.encode("utf-8")).hexdigest()}
            for index, command in enumerate(value, 1) if isinstance(command, str)]


def _roles(value: Any, workspace: str) -> dict[str, Any]:
    names = ("orchestrator", "implementer", "verifier", "scope_reviewer", "final_reviewer")
    keys = ("agent", "model", "effort", "fast", "fallback_effort")
    return {name: _pick(value.get(name), keys, workspace) for name in names if isinstance(value, dict) and isinstance(value.get(name), dict)}


def _review(value: Any, workspace: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = _pick(value, ("round", "diff_digest", "changed_paths", "outcome"), workspace)
    if _snapshot(value.get("diff_snapshot"), workspace):
        result["diff_snapshot"] = _snapshot(value.get("diff_snapshot"), workspace)
    for key in ("verifier", "scope_reviewer"):
        result[key] = _pick(value.get(key), ("model", "effort", "status", "thread_id", "diff_digest", "evidence"), workspace)
        snapshot = _snapshot(value.get(key, {}).get("diff_snapshot") if isinstance(value.get(key), dict) else None, workspace)
        if snapshot:
            result[key]["diff_snapshot"] = snapshot
    return result


def _unit(value: Any, workspace: str) -> dict[str, Any]:
    result = _pick(value, ("unit_id", "title", "status", "writer", "allowed_paths", "replan_count"), workspace)
    result["acceptance_commands"] = _command_receipts(value.get("acceptance_commands"), "acceptance-command") if isinstance(value, dict) else []
    result["test_receipts"] = [_pick(item, ("test_id", "command_index", "command_sha256", "source", "execution_receipt_sha256", "observer_role", "observer_thread_id", "diff_digest", "started_at", "ended_at", "exit_code", "output_sha256", "status"), workspace) | ({"diff_snapshot": _snapshot(item.get("diff_snapshot"), workspace)} if _snapshot(item.get("diff_snapshot"), workspace) else {})
                                for item in value.get("test_receipts", [])
                                if isinstance(value, dict) and isinstance(item, dict)] if isinstance(value, dict) and isinstance(value.get("test_receipts"), list) else []
    result["review_history"] = [_review(item, workspace) for item in value.get("review_history", [])] if isinstance(value, dict) and isinstance(value.get("review_history"), list) else []
    result["improvement_history"] = [_pick(item, ("after_round", "kind", "failure_signature", "root_cause", "hypothesis", "action", "strategy_digest", "scope_status", "evidence"), workspace) for item in value.get("improvement_history", [])] if isinstance(value, dict) and isinstance(value.get("improvement_history"), list) else []
    for key in ("failure", "recovery"):
        result[key] = _pick(value.get(key), ("code", "reason", "evidence", "recovery", "action"), workspace) if isinstance(value, dict) else {}
    return result


def _goal_link(value: Any, workspace: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"current": {}, "history": []}
    keys = ("mode", "source", "thread_id", "external_status", "objective_sha256", "receipt_sha256", "reason", "evidence", "observed_at", "completion_sync", "sync_result", "token_total")
    history = value.get("history") if isinstance(value.get("history"), list) else []
    return {"current": _pick(value.get("current"), keys, workspace), "history": [_pick(item, keys, workspace) for item in history]}


def _decision_context(value: Any, workspace: str) -> dict[str, Any]:
    return _pick(value, DECISION_CONTEXT_FIELDS, workspace)


def _improvement_candidates(value: Any, workspace: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [(_pick(item, IMPROVEMENT_CANDIDATE_FIELDS[:-1], workspace)
             | {"decision_context": _decision_context(item.get("decision_context"), workspace)})
            for item in value if isinstance(item, dict)]


def build_payload(workspace: str | Path, contract: dict, run: dict, units: list[dict], events: list[dict], state_digests: dict,
                  scope_audit: dict | None = None) -> dict:
    root = str(Path(workspace).absolute())
    spec = _pick(contract.get("spec"), ("source", "sha256", "confirmed_at"), root)
    contract_data = _pick(contract, ("schema_version", "goal_id", "goal", "locked", "lock_sha256"), root)
    for key in CONTRACT_LISTS:
        contract_data[key] = _clean(contract.get(key, []), root)
    contract_data["test_commands"] = _command_receipts(contract.get("test_commands"), "test-command")
    run_data = _pick(run, ("schema_version", "goal_id", "status", "started_at", "completed_at", "fast_status"), root)
    run_data["roles"] = _roles(run.get("roles"), root)
    profiles = run.get("agent_profiles") if isinstance(run.get("agent_profiles"), dict) else {}
    run_data["agent_profiles"] = {key: _clean(value, root) for key, value in profiles.items() if isinstance(key, str) and key.endswith(".toml") and isinstance(value, str) and SHA256.fullmatch(value)}
    metrics = _pick(run.get("metrics"), ("unit_count", "agent_runs", "review_rounds", "recoveries", "replans", "scope_deviations", "test_runs", "elapsed_seconds"), root)
    token = _pick(run.get("metrics", {}).get("token_usage"), ("availability", "reason", "source", "total"), root) if isinstance(run.get("metrics"), dict) else {}
    run_data["metrics"] = metrics | {"token_usage": token}
    run_data["deviations"] = [_pick(item, ("summary", "root_cause", "impact", "prevention", "evidence", "evidence_explanation"), root) for item in run.get("deviations", [])] if isinstance(run.get("deviations"), list) else []
    run_data["deferred_security"] = [(_pick(item, ("summary", "reason", "next_action", "evidence"), root)
                                      | {"decision_context": _decision_context(item.get("decision_context"), root)})
                                     for item in run.get("deferred_security", []) if isinstance(item, dict)] if isinstance(run.get("deferred_security"), list) else []
    run_data["final_review"] = _pick(run.get("final_review"), ("status",), root) | {"attempts": [_pick(item, ("model", "effort", "status", "thread_id", "diff_digest", "evidence"), root) | ({"diff_snapshot": _snapshot(item.get("diff_snapshot"), root)} if _snapshot(item.get("diff_snapshot"), root) else {}) for item in run.get("final_review", {}).get("attempts", [])] if isinstance(run.get("final_review"), dict) else []}
    run_data["goal_link"] = _goal_link(run.get("goal_link"), root)
    clean_units = sorted([_unit(item, root) for item in units if isinstance(item, dict)], key=lambda item: item.get("unit_id", ""))
    event_data = [_pick(event, EVENT_FIELDS, root) for event in events if isinstance(event, dict)]
    digests = state_digests if isinstance(state_digests, dict) else {}
    digest_data = {key: value for key, value in digests.items() if isinstance(key, str) and isinstance(value, str) and SHA256.fullmatch(value)}
    acceptance_commands = [command for item in clean_units for command in item.get("acceptance_commands", []) if isinstance(command, dict)]
    test_receipts = [{"unit_id": item.get("unit_id"), "receipts": item.get("test_receipts", [])} for item in clean_units]
    payload = {"schema_version": 2, "scope_audit": _scope_audit(scope_audit, root), "summary": {"goal": _text(contract.get("goal"), root), "status": _text(run.get("status"), root), "run_id": _text(run.get("goal_id"), root)}, "contract": contract_data | {"spec": spec}, "agents": {"roles": run_data["roles"], "profiles": run_data["agent_profiles"]}, "units": clean_units, "timeline": event_data, "reviews": {"units": [{"unit_id": item.get("unit_id"), "history": item.get("review_history", [])} for item in clean_units], "final_review": run_data["final_review"]}, "tests-metrics": {"metrics": run_data["metrics"], "acceptance_commands": acceptance_commands, "test_receipts": test_receipts}, "failures-recovery": [{"unit_id": item.get("unit_id"), "failure": item.get("failure", {}), "recovery": item.get("recovery", {}), "improvement_history": item.get("improvement_history", [])} for item in clean_units], "deviations": {"items": run_data["deviations"], "deferred_security": run_data["deferred_security"]}, "provenance": {"fast_status": run_data.get("fast_status"), "spec": spec, "agent_profiles": run_data.get("agent_profiles", {}), "goal_link": run_data["goal_link"], "state_digests": digest_data}, "improvement-candidates": _improvement_candidates(run.get("improvement_candidates"), root), "next-actions": _next_actions(run_data, clean_units)}
    return _clean(payload, root)


def _next_actions(run: dict, units: list[dict]) -> list[str]:
    actions = []
    if run.get("deviations"): actions.append("범위 편차의 prevention을 확인하고 재발 방지를 기록하세요.")
    if run.get("deferred_security"): actions.append("보류된 보안 작업은 승인 전 구현하지 말고 다음 결정을 기록하세요.")
    if any(sum(1 for item in unit.get("review_history", []) if item.get("outcome") == "fail") >= 2 for unit in units): actions.append("반복 실패의 새 가설과 전략을 검토하세요. 개선 후보는 [보고 전용]입니다.")
    token = run.get("metrics", {}).get("token_usage", {})
    if token.get("availability") == "unavailable": actions.append("정확한 token aggregate가 없어 추정하지 마세요.")
    if run.get("fast_status") == "unknown": actions.append("Fast 상태의 관찰 증거를 다음 보고에 남기세요.")
    return actions or ["추가 조치 없음."]


def canonical_payload_bytes(payload: dict) -> bytes:
    try:
        if not isinstance(payload, dict):
            raise ValueError
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except Exception:
        raise HwahapReportError("report data is invalid") from None


def canonical_payload_digest(payload: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def _report_pair_is_unsafe(key: str, value: object) -> bool:
    candidate = value if isinstance(value, str) else "value"
    return any(contains_sensitive_data(f"{key}{operator}{candidate}") for operator in ("=", ":"))


def _report_data_has_unsafe_text(value: object) -> bool:
    if isinstance(value, str):
        return contains_sensitive_data(value) or ABS_PATH.search(value) is not None
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and (ABS_PATH.search(key) is not None or _report_pair_is_unsafe(key, item)):
                return True
            if _report_data_has_unsafe_text(item):
                return True
        return False
    if isinstance(value, list):
        return any(_report_data_has_unsafe_text(item) for item in value)
    return False


def validate_report_data_bytes(data: bytes, expected_payload: dict, expected_digest: str) -> bool:
    try:
        if not isinstance(data, bytes) or not isinstance(expected_payload, dict):
            raise ValueError
        text = data.decode("utf-8", errors="strict")
        actual_payload = json.loads(text)
        canonical = canonical_payload_bytes(expected_payload)
        if (actual_payload != expected_payload or data != canonical
                or not isinstance(expected_digest, str)
                or expected_digest != "sha256:" + hashlib.sha256(canonical).hexdigest()
                or _report_data_has_unsafe_text(actual_payload)):
            raise ValueError
        return True
    except Exception:
        raise HwahapReportError("report data is invalid") from None


def _payload_ledger(payload: dict) -> tuple[tuple[str, str, str], ...]:
    rows: list[tuple[str, str, str]] = []
    def visit(value: object, pointer: str) -> None:
        if isinstance(value, dict):
            if not value:
                rows.append((pointer, "object", "{}"))
            else:
                for key in sorted(value):
                    if not isinstance(key, str):
                        raise ValueError
                    escaped = key.replace("~", "~0").replace("/", "~1")
                    visit(value[key], pointer + "/" + escaped)
        elif isinstance(value, list):
            if not value:
                rows.append((pointer, "array", "[]"))
            else:
                for index, item in enumerate(value):
                    visit(item, pointer + "/" + str(index))
        else:
            kind = "null" if value is None else "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "string" if isinstance(value, str) else None
            if kind is None:
                raise ValueError
            rows.append((pointer, kind, json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))))
    visit(payload, "")
    return tuple(rows)


def _payload_ledger_block(payload: dict) -> str:
    ledger = _payload_ledger(payload)
    _ensure_redaction()
    rows = "".join(f"<tr><td>{html.escape(_shared_redact(path), quote=True)}</td><td>{kind}</td><td>{html.escape(_text(value), quote=True)}</td></tr>" for path, kind, value in ledger)
    count = len(ledger)
    return (f'<section id="report-data"><h2>정본 데이터 전체 목록</h2>'
            f'<p class="section-intro">{count}개 JSON 값과 빈 컨테이너를 생략 없이 표시합니다. '
            '이 표는 감사를 위한 원본 근거이며, 위의 사람이 읽는 요약보다 우선하지 않습니다.</p>'
            f'<div class="table-wrap"><table><caption>정본 report-data.json ledger · {count}개 행</caption>'
            f'<thead><tr><th scope="col">JSON 경로</th><th scope="col">형식</th><th scope="col">값</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></section>')


def _validate_report_payload(payload: dict, source_digest: str) -> None:
    try:
        if not isinstance(payload, dict) or canonical_payload_digest(payload) != source_digest:
            raise ValueError
        validate_report_data_bytes(canonical_payload_bytes(payload), payload, source_digest)
    except Exception:
        raise HwahapReportError("report data is invalid") from None


def render_report(payload: dict, source_digest: str) -> bytes:
    _validate_report_payload(payload, source_digest)
    def esc(value: Any) -> str:
        return html.escape(_text(value), quote=True)
    def items(values: Any) -> str:
        values = values if isinstance(values, list) else []
        return "<p class=\"empty\">기록 없음</p>" if not values else "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in values) + "</ul>"
    def comma_items(values: Any) -> str:
        values = values if isinstance(values, list) else []
        return "<br>".join(esc(item) for item in values)
    def snapshot_html(value: Any) -> str:
        if not isinstance(value, dict):
            return '<span class="empty">기록 없음</span>'
        fields = "".join(f"<dt>{esc(key)}</dt><dd>{comma_items(value[key]) if isinstance(value[key], list) else esc(value[key])}</dd>"
                         for key in DIFF_SNAPSHOT_FIELDS if key in value)
        return f'<dl class="snapshot">{fields}</dl>' if fields else '<span class="empty">기록 없음</span>'
    def command_items(values: Any) -> str:
        values = values if isinstance(values, list) else []
        return "<p class=\"empty\">기록 없음</p>" if not values else "<ul>" + "".join(f"<li>{esc(item.get('name'))}: {esc(item.get('sha256'))}</li>" for item in values if isinstance(item, dict)) + "</ul>"
    def shown(value: Any) -> str:
        return "기록 없음" if value is None or value == "" else esc(value)
    def card(label: str, value: Any) -> str:
        return f'<article class="card md-card md-card-filled"><h3>{esc(label)}</h3><p>{esc(value)}</p></article>'
    def unique_texts(values: Any) -> list[str]:
        result: list[str] = []
        for value in values if isinstance(values, list) else []:
            text = _text(value)
            if text and text not in result:
                result.append(text)
        return result
    def duration_text(value: Any) -> str:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            return "기록 없음"
        seconds = int(value)
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        parts = ([f"{days}일"] if days else []) + ([f"{hours}시간"] if hours else [])
        parts += ([f"{minutes}분"] if minutes else []) + ([f"{seconds}초"] if seconds or not parts else [])
        return " ".join(parts)
    def fivew3h_details(summary_label: str, claim: str, rows: tuple[tuple[str, str], ...],
                         evidence: Any, limitation: str) -> str:
        facts = "".join(f'<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>' for label, value in rows)
        return (f'<details class="evidence-explanation"><summary>{esc(summary_label)}</summary>'
                f'<div class="evidence-brief"><p class="evidence-conclusion"><strong>이 근거가 뒷받침하는 판단</strong><br>{esc(claim)}</p>'
                f'<dl class="fivew3h-grid">{facts}</dl><div class="evidence-source"><strong>근거 원문</strong>{items(evidence)}</div>'
                f'<p class="evidence-limit"><strong>이 근거로는 알 수 없는 것</strong><br>{esc(limitation)}</p></div></details>')
    summary = payload.get("summary", {})
    contract = payload.get("contract", {})
    agents = payload.get("agents", {})
    units = payload.get("units", [])
    timeline = payload.get("timeline", []) if isinstance(payload.get("timeline"), list) else []
    first_event = timeline[0] if timeline and isinstance(timeline[0], dict) else {}
    last_event = timeline[-1] if timeline and isinstance(timeline[-1], dict) else {}
    report_actor = _text(last_event.get("actor")) or "항목별 기록 주체 미기록"
    first_timestamp = _text(first_event.get("timestamp"))
    last_timestamp = _text(last_event.get("timestamp"))
    if first_timestamp and last_timestamp and first_timestamp != last_timestamp:
        report_when = f"상태 이벤트 기준 {first_timestamp}부터 {last_timestamp}까지"
    elif last_timestamp:
        report_when = f"상태 이벤트에는 {last_timestamp}만 기록됨; 항목별 확인 시각은 미기록"
    else:
        report_when = "항목별 확인 시각 미기록"
    contract_meta = (("schema_version", contract.get("schema_version")), ("goal_id", contract.get("goal_id")),
                     ("goal", contract.get("goal")), ("locked", contract.get("locked")),
                     ("lock_sha256", contract.get("lock_sha256")))
    contract_spec = contract.get("spec", {}) if isinstance(contract.get("spec"), dict) else {}
    contract_meta_html = "".join(f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>" for key, value in (*contract_meta,
        ("spec source", contract_spec.get("source")), ("spec sha256", contract_spec.get("sha256")),
        ("spec confirmed_at", contract_spec.get("confirmed_at"))))
    contract_html = (f'<article class="card md-card md-card-filled"><h3>계약 메타데이터</h3><dl>{contract_meta_html}</dl></article>' +
                     "".join(f"<article class=\"card md-card md-card-filled\"><h3>{esc(CONTRACT_LABELS[key])}</h3>{command_items(contract.get(key)) if key == 'test_commands' else items(contract.get(key))}</article>" for key in CONTRACT_LISTS))
    role_html = "".join(f'<article class="card md-card md-card-filled"><h3>{esc(role)}</h3><p>agent: {esc(info.get("agent"))}</p><p>model: {esc(info.get("model"))}</p><p>effort: {esc(info.get("effort"))}</p><p>Fast: {esc(info.get("fast", info.get("fallback_effort", "unknown")))}</p></article>' for role, info in agents.get("roles", {}).items() if isinstance(info, dict))
    profile_html = "".join(f'<article class="card md-card md-card-filled"><h3>agent profile</h3><p>filename: {esc(name)}</p><p>digest: {esc(digest)}</p></article>' for name, digest in agents.get("profiles", {}).items())
    agents_html = role_html + profile_html or card("상태", "역할 정보 없음")
    unit_html = "".join(f'<article class="card md-card md-card-filled"><h3>{esc(unit.get("unit_id"))}: {esc(unit.get("title"))}</h3><p>상태: {esc(unit.get("status"))}</p><p>writer: {shown(unit.get("writer"))}</p><p>replan_count: {shown(unit.get("replan_count"))}</p><p>허용 경로</p>{items(unit.get("allowed_paths"))}<p>Acceptance receipts</p>{command_items(unit.get("acceptance_commands"))}<p>검토 {len(unit.get("review_history", []))}회 · 개선 {len(unit.get("improvement_history", []))}건</p></article>' for unit in units) or '<p class="empty">기록 없음</p>'
    timeline_html = "".join(f'<li><dl>{"".join(f"<dt>{esc(field)}</dt><dd>{comma_items(event.get(field)) if isinstance(event.get(field), list) else esc(event.get(field))}</dd>" for field in EVENT_FIELDS)}</dl></li>' for event in payload.get("timeline", []))
    reviews = payload.get("reviews", {})
    def reviewer_cell(value: Any) -> str:
        if not isinstance(value, dict):
            return '<span class="empty">기록 없음</span>'
        return "<dl>" + "".join(f"<dt>{esc(key)}</dt><dd>{esc(value.get(key))}</dd>" for key in ("status", "model", "effort", "thread_id", "diff_digest")) + "</dl>"
    review_rows = "".join(f'<tr><td>{esc(unit.get("unit_id"))}</td><td>{esc(review.get("round"))}</td><td>{esc(review.get("outcome"))}</td><td>{reviewer_cell(review.get("verifier"))}</td><td>{reviewer_cell(review.get("scope_reviewer"))}</td><td>{comma_items(review.get("changed_paths", []))}</td><td>{comma_items(review.get("verifier", {}).get("evidence", []))}</td><td>{comma_items(review.get("scope_reviewer", {}).get("evidence", []))}</td><td>{snapshot_html(review.get("diff_snapshot"))}</td></tr>' for unit in reviews.get("units", []) for review in unit.get("history", [])) or '<tr><td colspan="9" class="empty">기록 없음</td></tr>'
    final_attempts = reviews.get("final_review", {}).get("attempts", [])
    final_review_html = f'<p>aggregate status: {esc(reviews.get("final_review", {}).get("status"))}</p>' + (
        '<div class="receipt-list">' + "".join(
            f'<article class="receipt md-card md-card-filled"><p>{esc(attempt.get("model"))} / {esc(attempt.get("effort"))} / {esc(attempt.get("status"))} / {esc(attempt.get("thread_id"))}</p><p>diff_digest: {esc(attempt.get("diff_digest"))}</p><p>evidence: {comma_items(attempt.get("evidence", []))}</p>{snapshot_html(attempt.get("diff_snapshot"))}</article>'
            for attempt in final_attempts if isinstance(attempt, dict)) + '</div>' if final_attempts else '<p class="empty">기록 없음</p>')
    scope = payload.get("scope_audit", {})
    def audit_units(value: Any) -> str:
        if not isinstance(value, list):
            return ""
        return "; ".join(f'{esc(item.get("unit_id"))}: {comma_items(item.get("matched_rules", []))}'
                          for item in value if isinstance(item, dict))
    scope_rows = "".join(
        f'<article class="card md-card md-card-filled"><h3>{esc(item.get("path"))}: {esc(item.get("verdict"))}</h3>'
        f'<p>contract_allowed: {esc(item.get("contract_allowed"))}; passed_unit_covered: {esc(item.get("passed_unit_covered"))}; forbidden_overlap: {esc(item.get("forbidden_overlap"))}</p>'
        f'<p>계약 규칙: {comma_items(item.get("matched_contract_rules", []))}</p>'
        f'<p>통과 단위·규칙: {audit_units(item.get("covering_passed_units"))}</p>'
        f'<p>금지 규칙: {comma_items(item.get("matched_forbidden_rules", []))}</p>'
        f'<p>증거 diff digest: {esc(item.get("evidence", {}).get("diff_digest"))}; contract lock: {esc(item.get("evidence", {}).get("contract_lock_sha256"))}; passed unit IDs: {comma_items(item.get("evidence", {}).get("passed_unit_ids", []))}</p></article>'
        for item in (scope.get("paths", []) if isinstance(scope, dict) else [])
        if isinstance(item, dict)
    ) or '<p class="empty">기록 없음</p>'
    scope_audit_html = f'<dl><dt>authority</dt><dd>{esc(scope.get("authority"))}</dd><dt>affects_gate</dt><dd>{esc(scope.get("affects_gate"))}</dd><dt>source_diff_digest</dt><dd>{esc(scope.get("source_diff_digest"))}</dd><dt>contract_lock_sha256</dt><dd>{esc(scope.get("contract_lock_sha256"))}</dd></dl><div class="cards">{scope_rows}</div>'
    metrics = payload.get("tests-metrics", {}).get("metrics", {})
    def display(value: Any) -> str:
        if value is None or value == "":
            return "기록 없음"
        if isinstance(value, list):
            return comma_items(value) or "기록 없음"
        return esc(AVAILABILITY_LABELS.get(value, value))
    def metric_value(key: str, value: Any) -> str:
        if key == "agent_runs" and isinstance(value, dict):
            return f"{esc(METRIC_LABELS.get('availability'))}: {display(value.get('availability'))}; {esc(METRIC_LABELS.get('reason'))}: {display(value.get('reason'))}"
        return esc(value)
    metrics_html = "".join(f"<dt>{esc(METRIC_LABELS.get(key, '기타 정보'))}</dt><dd>{metric_value(key, value)}</dd>" for key, value in metrics.items() if key != "token_usage")
    token = metrics.get("token_usage", {})
    command_html = command_items(payload.get("tests-metrics", {}).get("acceptance_commands", []))
    def receipt_items(values: Any) -> str:
        labels = (("status", "결과"), ("source", "출처"), ("observer_role", "관찰 역할"),
                  ("observer_thread_id", "Luna verifier thread"), ("diff_digest", "검토 diff digest"),
                  ("execution_receipt_sha256", "실행 receipt digest"), ("command_sha256", "명령 digest"),
                  ("output_sha256", "출력 digest"), ("started_at", "시작"), ("ended_at", "종료"),
                  ("exit_code", "exit code"), ("command_index", "명령 번호"))
        cards = []
        if isinstance(values, list):
            for item in values:
                if not isinstance(item, dict) or not isinstance(item.get("receipts"), list):
                    continue
                for receipt in item["receipts"]:
                    if not isinstance(receipt, dict):
                        continue
                    fields = "".join(f"<dt>{esc(label)}</dt><dd>{esc(receipt.get(key))}</dd>" for key, label in labels)
                    fields += f'<dt>diff snapshot</dt><dd>{snapshot_html(receipt.get("diff_snapshot"))}</dd>'
                    cards.append(f'<article class="receipt md-card md-card-filled"><h3>{esc(item.get("unit_id"))}/{esc(receipt.get("test_id"))}</h3><dl>{fields}</dl></article>')
        return '<div class="receipt-list">' + "".join(cards) + '</div>' if cards else '<p class="empty">기록 없음</p>'
    receipt_groups = payload.get("tests-metrics", {}).get("test_receipts", [])
    receipt_count = sum(len(item.get("receipts", [])) for item in receipt_groups if isinstance(item, dict) and isinstance(item.get("receipts"), list))
    final_paths = unique_texts([path for attempt in final_attempts if isinstance(attempt, dict)
                                for path in (attempt.get("diff_snapshot", {}).get("changed_paths", [])
                                             if isinstance(attempt.get("diff_snapshot"), dict) else [])])
    completion_where = (f"최종 검토 snapshot의 변경 경로 {len(final_paths)}개. 전체 경로는 원본 증거의 최종 검토에 있음"
                        if final_paths else "최종 검토와 연결된 변경 경로가 정본 payload에 없음")
    overall_where = (f"이 항목과 특정 경로의 직접 연결은 미기록. 전체 완료 snapshot에는 변경 경로 {len(final_paths)}개가 있음"
                     if final_paths else "이 항목과 연결된 변경 경로가 정본 payload에 없음")
    def evidence_reference_text(values: Any) -> str:
        return " / ".join(unique_texts(values)) or "근거 원문 없음"
    def contextual_evidence(label: str, claim: str, why: str, method: str, evidence: Any,
                            limitation: str, context: Any = None) -> str:
        evidence_values = evidence if isinstance(evidence, list) else []
        context = context if isinstance(context, dict) else {}
        scenario = _text(context.get("scenario"))
        affected_scope = _text(context.get("affected_scope"))
        impact = _text(context.get("impact"))
        decision_reason = _text(context.get("decision_reason"))
        evidence_relation = _text(context.get("evidence_relation"))
        success_condition = _text(context.get("success_condition"))
        why_text = " ".join(value for value in (why, impact, decision_reason) if value)
        rows = (("누가 (Who)", f"항목별 작성자는 미기록. 완료 상태 기록자는 {report_actor}"),
                ("언제 (When)", f"{report_when}. 문제가 되는 조건: {scenario or '구체적 시나리오 미기록'}"),
                ("어디서 (Where)", f"{affected_scope or '영향 범위 미기록'}. {overall_where}"),
                ("무엇을 (What)", scenario or claim),
                ("왜 (Why)", why_text),
                ("어떻게 (How)", evidence_relation or method),
                ("얼마나 (How much)", f"해결 판단 기준: {success_condition or '미기록'}; 근거 문구 {len(evidence_values)}개; 직접 연결된 구조화 receipt 필드는 없음"),
                ("얼마 동안 (How long)", "항목별 조사·검증 시간 미기록"))
        return fivew3h_details(label, claim, rows, evidence_values, limitation)
    def decision_context_html(value: Any, subject_label: str) -> str:
        context = value if isinstance(value, dict) else {}
        if any(not _text(context.get(field)) for field in DECISION_CONTEXT_FIELDS):
            return ('<p class="evidence-limit"><strong>판단 설명 누락</strong><br>'
                    f'{esc(subject_label)}의 실제 발생 상황, 영향, 결정 이유, 근거 연결, 해결 기준이 정본 데이터에 모두 기록되지 않았습니다. '
                    '이 상태에서는 제목만으로 위험이나 후속 작업의 필요성을 판단할 수 없습니다.</p>')
        fields = ((f"왜 {subject_label}인가", f"{context['scenario']} {context['impact']}"),
                  ("어디에 영향을 주는가", context["affected_scope"]),
                  ("왜 사용자가 결정해야 하는가", context["decision_reason"]),
                  ("근거가 이 판단을 뒷받침하는 방식", context["evidence_relation"]),
                  ("해결됐다고 볼 기준", context["success_condition"]))
        return '<div class="causal-chain">' + "".join(
            f'<div class="causal-step"><span class="field-label">{esc(label)}</span><p>{esc(text)}</p></div>'
            for label, text in fields) + '</div>'
    def improvement_text(record: dict[str, Any]) -> str:
        def shown(value: Any) -> str:
            if value is None or value == "":
                return "기록 없음"
            if isinstance(value, list):
                return ", ".join(shown(item) for item in value)
            return _text(value)
        return "; ".join(f"{key}={shown(record.get(key))}" for key in ("after_round", "kind", "failure_signature", "root_cause", "hypothesis", "action", "strategy_digest", "scope_status", "evidence"))
    candidate_html = "".join(
        f'<article class="proposal-card tile md-card md-card-filled"><span class="label-chip status-warning">사용자 결정 필요</span>'
        f'<h3>{esc(candidate.get("summary"))}</h3>'
        f'{decision_context_html(candidate.get("decision_context"), "개선 후보")}'
        f'<span class="field-label">기대 효과</span><p>{esc(candidate.get("expected_effect"))}</p>'
        f'<span class="field-label">다음 결정</span><p>{esc(candidate.get("next_action"))}</p>'
        f'{contextual_evidence("제안 근거와 한계 보기", _text(candidate.get("summary")), "완료 결과에 후속 후보로 기록됐지만 현재 목표 범위를 넓히므로 사용자 승인이 필요함", f"근거 원문 ‘{evidence_reference_text(candidate.get('evidence'))}’을 제안 출처로 기록하고 proposed 상태·기대 효과·다음 조치를 함께 대조함", candidate.get("evidence"), "기록된 성공 기준을 실제로 충족하기 전에는 기대 효과가 발생했다고 볼 수 없음", candidate.get("decision_context"))}'
        f'<p class="notice">보고 전용 · 사용자 승인 전에는 실행하지 않음</p></article>'
        for candidate in payload.get("improvement-candidates", []) if isinstance(candidate, dict)
    ) or '<p class="empty">추가 개선 제안 없음</p>'
    failure_items = [item for item in payload.get("failures-recovery", []) if item.get("failure") or item.get("recovery") or item.get("improvement_history")]
    failure_html = "".join(
        f'<article class="card md-card md-card-filled"><h3>{esc(item.get("unit_id"))}</h3>'
        f'<p>{esc(item.get("failure", {}).get("code", "실패 없음"))}: {esc(item.get("failure", {}).get("reason", ""))}</p>'
        f'{contextual_evidence("실패 판단 근거와 한계 보기", _text(item.get("failure", {}).get("reason")) or "실패 기록", "해당 작업 단위가 실패 상태가 된 이유를 확인하기 위함", "failure code·reason과 연결된 근거 원문을 대조함", item.get("failure", {}).get("evidence"), "원문에 연결된 실행 receipt가 없으면 이 보고서만으로 실패를 재현할 수 없음")}'
        f'<p>failure.recovery: {shown(item.get("failure", {}).get("recovery"))}</p><p>recovery.reason: {shown(item.get("recovery", {}).get("reason"))}</p><p>recovery.action: {shown(item.get("recovery", {}).get("action"))}</p>'
        f'{contextual_evidence("복구 판단 근거와 한계 보기", _text(item.get("recovery", {}).get("action")) or "복구 기록", "실패 뒤 어떤 조치로 원래 계획에 복귀했는지 확인하기 위함", "recovery reason·action과 개선 이력을 근거 원문과 대조함", item.get("recovery", {}).get("evidence"), "복구 후 결과가 지속된 기간과 운영 환경의 효과는 기록되지 않음")}'
        f'{items([improvement_text(record) for record in item.get("improvement_history", [])])}</article>'
        for item in failure_items) or '<p class="empty">기록 없음</p>'
    deviation_html = "".join(
        f'<article class="change-card panel md-card md-card-filled"><header class="change-card-header">'
        f'<div><span class="eyebrow">Resolved finding</span><h3>{esc(item.get("summary"))}</h3></div>'
        f'<span class="status-chip status-success">개선 적용·검증됨</span></header>'
        f'<div class="change-card-body"><div class="change-field"><span class="field-label">이전 문제</span><p>{esc(item.get("impact"))}</p></div>'
        f'<div class="change-field"><span class="field-label">발생 원인</span><p>{esc(item.get("root_cause"))}</p></div>'
        f'<div class="change-field"><span class="field-label">적용한 개선</span><p>{esc(item.get("prevention"))}</p></div></div>'
        f'<p class="expected-change"><strong>이전 대비 기대 변화</strong><br>'
        '위의 “이전 문제”가 다시 발생하기 전에 “적용한 개선”에 적힌 검사로 '
        '같은 유형의 누락이나 오판을 발견하거나 차단할 것으로 기대합니다. '
        '표시된 검증 근거 범위의 기대이며 실제 운영 효과를 보장한다는 뜻은 아닙니다.</p>'
        f'<div class="evidence-rationale"><span class="field-label">왜 이 검사로 개선됐다고 판단했나</span>'
        f'<p>{shown(item.get("evidence_explanation"))}</p></div>'
        f'{contextual_evidence("검증 근거와 한계 보기", _text(item.get("prevention")), "기록된 원인에 대응하는 예방 조치가 적용됐다는 판단을 확인하기 위함", _text(item.get("evidence_explanation")) or "근거와 개선 조치의 연결 설명이 기록되지 않음", item.get("evidence"), "실행 receipt와 연결된 구체적 설명이 없거나 동일 문제가 다시 발생하지 않는 기간을 측정하지 않았다면 실제 운영 효과까지 보장하지 않음")}</article>'
        for item in payload.get("deviations", {}).get("items", [])
    ) or '<p class="empty">기록된 문제와 개선 없음</p>'
    deferred_html = "".join(
        f'<article class="risk-card tile md-card md-card-filled"><span class="status-chip status-error">아직 확인되지 않음</span>'
        f'<h3>{esc(item.get("summary"))}</h3>{decision_context_html(item.get("decision_context"), "남은 위험")}'
        f'<span class="field-label">남은 이유</span><p>{esc(item.get("reason"))}</p>'
        f'<span class="field-label">다음 결정</span><p>{esc(item.get("next_action"))}</p>'
        f'{contextual_evidence("남은 위험의 근거와 한계 보기", _text(item.get("summary")), _text(item.get("reason")) or "직접 검증 범위가 부족함", f"근거 원문은 확인 범위를 ‘{evidence_reference_text(item.get('evidence'))}’로 한정하고, 남은 이유에는 제외된 검증 범위를 기록함", item.get("evidence"), "기록된 해결 기준을 직접 검증하기 전에는 이 위험이 해소됐다고 볼 수 없음", item.get("decision_context"))}</article>'
        for item in payload.get("deviations", {}).get("deferred_security", [])
    ) or '<p class="empty">별도로 보류된 위험 없음</p>'
    provenance = payload.get("provenance", {})
    goal_current = provenance.get("goal_link", {}).get("current", {})
    spec = provenance.get("spec", {})
    prov_fields = [("fast_status", provenance.get("fast_status")),
                   ("spec source", spec.get("source")), ("spec sha256", spec.get("sha256")),
                   ("spec confirmed_at", spec.get("confirmed_at"))]
    prov_fields.extend((f"Goal current {key}", goal_current.get(key)) for key in ("thread_id", "receipt_sha256", "objective_sha256", "observed_at", "token_total", "source", "reason"))
    prov_fields.append(("Goal current evidence", goal_current.get("evidence", [])))
    prov_fields.extend((("Goal mode", goal_current.get("mode")), ("Goal sync", goal_current.get("completion_sync")), ("Goal sync result", goal_current.get("sync_result"))))
    prov_fields.extend((f"state digest {key}", value) for key, value in provenance.get("state_digests", {}).items())
    prov_fields.extend((f"agent profile {key}", value) for key, value in provenance.get("agent_profiles", {}).items())
    prov_html = "".join(f"<dt>{esc(key)}</dt><dd>{display(value)}</dd>" for key, value in prov_fields)
    goal_history_html = items([json.dumps(item, ensure_ascii=False, sort_keys=True) for item in provenance.get("goal_link", {}).get("history", []) if isinstance(item, dict)])
    style = STYLE_BLOCK
    token_html = f"{esc(METRIC_LABELS['availability'])}: {display(token.get('availability'))}; {esc(METRIC_LABELS['source'])}: {display(token.get('source'))}; {esc(METRIC_LABELS['total'])}: {display(token.get('total'))}; {esc(METRIC_LABELS['reason'])}: {display(token.get('reason'))}"
    status = str(summary.get("status", "unknown"))
    status_class = "status-success" if status == "completed" else "status-error" if status in {"failed", "blocked", "cancelled"} else "status-warning"
    status_label = "완료" if status == "completed" else "실패 또는 중단" if status in {"failed", "blocked", "cancelled"} else "진행 상태 확인 필요"
    passed_units = sum(1 for unit in units if isinstance(unit, dict) and unit.get("status") == "passed")
    total_units = len(units) if isinstance(units, list) else 0
    latest_reviews = [unit.get("review_history", [])[-1] for unit in units if isinstance(unit, dict)
                      and isinstance(unit.get("review_history"), list) and unit.get("review_history")]
    def review_chain_passes(review: Any) -> bool:
        if not isinstance(review, dict) or review.get("outcome") != "pass":
            return False
        verifier = review.get("verifier", {})
        scope_reviewer = review.get("scope_reviewer", {})
        digests = [review.get("diff_digest"), verifier.get("diff_digest"), scope_reviewer.get("diff_digest")]
        snapshot = review.get("diff_snapshot", {})
        if isinstance(snapshot, dict):
            digests.append(snapshot.get("diff_digest"))
        present = [value for value in digests if isinstance(value, str) and value]
        return (isinstance(verifier, dict) and verifier.get("status") == "pass"
                and isinstance(scope_reviewer, dict) and scope_reviewer.get("status") == "pass"
                and len(present) == 4 and len(set(present)) == 1)
    reviewed_units = sum(1 for review in latest_reviews if review_chain_passes(review))
    final_passes = [attempt for attempt in final_attempts if isinstance(attempt, dict) and attempt.get("status") == "pass"]
    final_review_passed = reviews.get("final_review", {}).get("status") == "pass" and bool(final_passes)
    completion_consistent = (status == "completed" and total_units > 0 and passed_units == total_units
                             and reviewed_units == total_units and final_review_passed)
    completion_evidence = unique_texts([
        evidence for review in latest_reviews if isinstance(review, dict)
        for reviewer in (review.get("verifier", {}), review.get("scope_reviewer", {}))
        if isinstance(reviewer, dict) for evidence in reviewer.get("evidence", [])
    ] + [evidence for attempt in final_attempts if isinstance(attempt, dict) for evidence in attempt.get("evidence", [])])
    writers = unique_texts([unit.get("writer") for unit in units if isinstance(unit, dict)])
    verifier_models = unique_texts([review.get("verifier", {}).get("model") for review in latest_reviews if isinstance(review, dict)])
    scope_models = unique_texts([review.get("scope_reviewer", {}).get("model") for review in latest_reviews if isinstance(review, dict)])
    final_models = unique_texts([attempt.get("model") for attempt in final_attempts if isinstance(attempt, dict)])
    who_text = (f"구현 {', '.join(writers) or '미기록'}; Luna 검증 {', '.join(verifier_models) or '미기록'}; "
                f"Terra 범위 검수 {', '.join(scope_models) or '미기록'}; Sol 최종 검토 {', '.join(final_models) or '미기록'}")
    recorded_tests = metrics.get("test_runs")
    receipt_gap = (isinstance(recorded_tests, int) and recorded_tests != receipt_count)
    if completion_consistent:
        completion_conclusion = (f"실행 기록상 완료 판정은 일관됩니다. 작업 단위 {passed_units}개가 모두 통과했고, "
                                 f"각 단위의 최신 Luna 검증과 Terra 범위 검수 {reviewed_units}개가 같은 diff에서 통과했으며, "
                                 "Sol 최종 검토도 통과한 뒤 상태가 completed로 기록됐습니다.")
    else:
        completion_conclusion = (f"상태는 {status_label}로 기록됐지만 완료 판정에 필요한 기록이 모두 맞물리지 않습니다. "
                                 f"작업 단위 {passed_units}/{total_units}, 단위 검토 {reviewed_units}/{total_units}, "
                                 f"Sol 최종 검토 {'통과' if final_review_passed else '미통과'}입니다.")
    receipt_explanation = (f"메트릭에는 테스트 실행 {display(recorded_tests)}회가 기록됐지만 상세 실행 receipt는 {receipt_count}건입니다. "
                           "두 수치는 같은 증거가 아니므로 상세 receipt가 없는 실행은 이 HTML만으로 명령과 출력을 재현할 수 없습니다."
                           if receipt_gap else f"기록된 테스트 실행은 {display(recorded_tests)}회이고 상세 실행 receipt는 {receipt_count}건입니다.")
    deviation_count = len(payload.get("deviations", {}).get("items", []))
    completion_rows = (
        ("누가 (Who)", who_text),
        ("언제 (When)", report_when),
        ("어디서 (Where)", completion_where),
        ("무엇을 (What)", f"목표 ‘{_text(summary.get('goal'))}’의 상태를 {status_label}로 판단"),
        ("왜 (Why)", f"상태 {status}; 작업 단위 {passed_units}/{total_units}; 동일 diff 단위 검토 {reviewed_units}/{total_units}; Sol 최종 검토 {'pass' if final_review_passed else '미통과'}"),
        ("어떻게 (How)", "작업 단위 상태 → Luna 기능 검증 → Terra 계획·범위 검수 → Sol 최종 snapshot 검토 → completed 상태 순서로 기록을 대조"),
        ("얼마나 (How much)", f"검수 회차 {display(metrics.get('review_rounds'))}회; 기록된 테스트 실행 {display(recorded_tests)}회; 상세 receipt {receipt_count}건; 개선 {deviation_count}건"),
        ("얼마 동안 (How long)", f"소요 시간 메트릭 {duration_text(metrics.get('elapsed_seconds'))}; 개별 단계 시간은 미기록"),
    )
    risk_count = len(payload.get("deviations", {}).get("deferred_security", []))
    candidate_count = len(payload.get("improvement-candidates", []))
    def decision_record(action: Any) -> str:
        action_text = _text(action)
        relevant_section = "이 보고서"
        decision_evidence: list[str] = []
        why = "정본 payload가 후속 조치로 기록했기 때문"
        method = "관련 기록과 원문 근거를 확인한 뒤 승인·보류·추가 검증 중 하나를 사용자가 선택"
        count_text = "관련 항목 수를 자동으로 연결할 수 없음"
        if action_text.startswith("범위 편차"):
            records = payload.get("deviations", {}).get("items", [])
            relevant_section, count_text = "문제와 개선 섹션", f"개선 기록 {len(records)}건"
            why = "이미 적용한 prevention이 같은 유형의 문제를 막는지 사용자가 수용해야 하기 때문"
            decision_evidence = unique_texts([value for item in records if isinstance(item, dict)
                                              for value in [item.get("summary"), *item.get("evidence", [])]])
        elif action_text.startswith("보류된 보안"):
            records = payload.get("deviations", {}).get("deferred_security", [])
            relevant_section, count_text = "아직 남은 위험 섹션", f"보류된 위험 {len(records)}건"
            reasons = unique_texts([item.get("decision_context", {}).get("decision_reason")
                                    for item in records if isinstance(item, dict)
                                    and isinstance(item.get("decision_context"), dict)])
            why = " ".join(reasons) or "위험별 사용자 결정 이유가 기록되지 않아 판단 근거가 불충분함"
            decision_evidence = unique_texts([value for item in records if isinstance(item, dict)
                                              for value in [item.get("summary"), item.get("reason"), *item.get("evidence", [])]])
        elif "반복 실패" in action_text:
            histories = [record for unit in units if isinstance(unit, dict)
                         for record in unit.get("improvement_history", []) if isinstance(record, dict)]
            relevant_section, count_text = "실패·복구 원본 기록", f"개선 이력 {len(histories)}건"
            why = "두 번 실패한 작업은 같은 전략을 반복하지 않고 Sol 재계획 여부를 결정해야 하기 때문"
            decision_evidence = unique_texts([value for record in histories for value in record.get("evidence", [])])
        elif "token" in action_text:
            relevant_section, count_text = "원본 수치의 token 사용량", "token aggregate 1항목"
            why = "플랫폼이 정확한 합계를 제공하지 않은 상태에서 추정치를 사실처럼 쓰지 않기 위함"
            decision_evidence = unique_texts([token.get("availability"), token.get("reason"), token.get("source")])
        elif "Fast 상태" in action_text:
            relevant_section, count_text = "출처와 digest의 fast_status", "Fast 상태 1항목"
            why = "실제 Fast 활성 여부를 관찰한 receipt가 없어 모델 실행 조건을 확정할 수 없기 때문"
            decision_evidence = [f"fast_status={_text(provenance.get('fast_status')) or '기록 없음'}"]
        rows = (("누가 (Who)", "사용자가 최종 결정. Hwahap는 정본 payload 조건을 근거로 이 조치만 제시"),
                ("언제 (When)", "이 보고서를 검토한 뒤; 결정 기한은 미기록"),
                ("어디서 (Where)", relevant_section),
                ("무엇을 (What)", action_text),
                ("왜 (Why)", why),
                ("어떻게 (How)", method),
                ("얼마나 (How much)", count_text),
                ("얼마 동안 (How long)", "결정·후속 작업 소요 시간 미기록"))
        details = fivew3h_details("이 결정이 필요한 근거와 한계 보기", action_text, rows, decision_evidence,
                                  "이 보고서는 결정을 제안할 뿐 승인으로 간주하거나 후속 작업을 자동 실행하지 않음")
        return f'<article class="decision-item"><h3>{esc(action_text)}</h3><p><strong>판단 이유</strong><br>{esc(why)}</p>{details}</article>'
    decision_html = '<div class="decision-list">' + "".join(decision_record(action) for action in payload.get("next-actions", [])) + '</div>'
    summary_metrics = (
        f'<article class="outcome-panel panel md-card md-card-elevated"><div class="panel-head"><div><span class="eyebrow">Verified outcome</span><h3>완료 근거 요약</h3></div>'
        f'<span class="status-chip {status_class}">{esc(status_label)}</span></div>'
        f'<div class="summary-grid"><div class="metric"><span class="metric-label">최종 판정</span><span class="metric-value">실행 기록상 {esc(status_label)} · Sol {esc(reviews.get("final_review", {}).get("status"))}</span></div>'
        f'<div class="metric"><span class="metric-label">통과한 작업 단위</span><span class="metric-value">{passed_units} / {total_units}</span></div>'
        f'<div class="metric"><span class="metric-label">검증 기록</span><span class="metric-value">실행 {display(recorded_tests)}회 · 상세 receipt {receipt_count}건</span></div>'
        f'<div class="metric"><span class="metric-label">발견·개선한 문제</span><span class="metric-value">{deviation_count}건</span></div></div></article>'
    )
    human_sections = (
        f'<section id="summary" class="hero"><div class="hero-copy-block stack">'
        f'<span class="eyebrow">Hwahap orchestration · {esc(summary.get("run_id"))}</span><h1>Hwahap 실행 결과</h1>'
        f'<p class="hero-copy">{esc(summary.get("goal"))}</p>'
        f'<p class="section-intro">결론과 변화부터 읽고, 전체 snapshot·receipt·JSON 값은 맨 아래 원본 증거에서 확인할 수 있습니다.</p></div>{summary_metrics}</section>'
        f'<div class="decision-layout"><div><section id="deviations"><span class="eyebrow">Before → after</span>'
        f'<h2>무엇이 문제였고 어떻게 개선했나</h2><p class="section-intro">각 항목은 이전 문제, 발생 원인, 적용한 개선, 이전 대비 기대 변화를 같은 순서로 보여줍니다.</p>'
        f'<div class="change-grid">{deviation_html}</div></section></div>'
        f'<aside class="supporting-pane" aria-label="남은 위험"><section><span class="eyebrow">Remaining risk</span><h2>아직 남은 위험</h2>'
        f'<p class="section-intro">완료 판정과 별개로 아직 직접 검증하지 못했거나 새 승인이 필요한 항목 {risk_count}건입니다.</p>'
        f'<div class="cards">{deferred_html}</div></section></aside></div>'
        f'<section id="improvement-candidates"><span class="eyebrow">Report only</span><h2>다음에 개선할 수 있는 것</h2>'
        f'<p class="section-intro">현재 기능을 실패로 바꾸지 않는 후속 후보 {candidate_count}건입니다. 기대 효과와 다음 결정을 확인한 뒤 사용자가 승인해야 실행합니다.</p>'
        f'<div class="proposal-grid">{candidate_html}</div></section>'
        f'<section id="next-actions"><span class="eyebrow">Decision</span><h2>지금 사용자가 판단할 것</h2>{decision_html}</section>'
        f'<section id="tests-metrics"><span class="eyebrow">Verification</span><h2>어떤 근거로 완료라고 판단했나</h2>'
        f'<p class="completion-judgment">{esc(completion_conclusion)}</p><p class="section-intro">{esc(receipt_explanation)}</p>'
        f'{fivew3h_details("완료 판단의 5W3H와 근거 원문 보기", completion_conclusion, completion_rows, completion_evidence, receipt_explanation)}'
        f'<div class="metrics-grid"><article class="card tile md-card md-card-filled"><h3>원본 수치</h3><p class="notice">수치는 판정 문장을 뒷받침하는 기록이며, 수치만으로 완료를 뜻하지 않습니다.</p><dl>{metrics_html}</dl><p>{token_html}</p></article>'
        f'<article class="card tile md-card md-card-filled"><h3>Sol 최종 리뷰 원문</h3>{final_review_html}</article></div>'
        f'<details><summary>테스트 명령과 receipt 전체 보기</summary><h3>Acceptance commands</h3>{command_html}'
        f'<h3>Test receipts</h3>{receipt_items(payload.get("tests-metrics", {}).get("test_receipts", []))}</details></section>'
    )
    technical_sections = (
        f'<details id="evidence-vault" class="evidence-vault"><summary>원본 증거 전체 보기 · snapshot, 상태 이력, JSON ledger</summary><div class="evidence-content">'
        f'<p class="section-intro">아래 내용은 감사와 재검증을 위한 전체 자료입니다. 앞의 결론·문제·개선 설명과 같은 정본 데이터를 사용합니다.</p>'
        f'<section id="contract"><h2>잠긴 계약</h2><div class="cards">{contract_html}</div></section>'
        f'<section id="agents"><h2>에이전트·역할 파이프라인</h2><div class="cards">{agents_html}</div></section>'
        f'<section id="units"><h2>작업 단위</h2><div class="cards">{unit_html}</div></section>'
        f'<section id="timeline"><h2>전체 타임라인</h2><ol class="timeline">{timeline_html}</ol></section>'
        f'<section id="reviews"><h2>단위별 검토</h2><div class="table-wrap"><table><caption>Luna 검증과 Terra 범위 검토</caption>'
        f'<thead><tr><th scope="col">단위</th><th scope="col">회차</th><th scope="col">결과</th><th scope="col">Luna</th><th scope="col">Terra</th><th scope="col">변경 경로</th><th scope="col">Luna 증거</th><th scope="col">Terra 증거</th><th scope="col">Git snapshot</th></tr></thead><tbody>{review_rows}</tbody></table></div>'
        f'<h3>최종 검토</h3>{final_review_html}</section>'
        f'<section id="scope-audit"><h2>범위 감사</h2>{scope_audit_html}</section>'
        f'<section id="failures-recovery"><h2>실패·복구 전체 기록</h2><div class="cards">{failure_html}</div></section>'
        f'<section id="provenance"><h2>출처와 digest</h2><dl>{prov_html}</dl><h3>Goal history</h3>{goal_history_html}</section>'
        f'{_payload_ledger_block(payload)}</div></details>'
    )
    app_header = (
        f'<a class="skip-link" href="#summary">결론으로 건너뛰기</a><header class="top-app-bar">'
        f'<div><span class="app-kicker">Local evidence report</span><div class="app-title">Hwahap</div></div>'
        f'<span class="status-chip {status_class}">{esc(status_label)}</span></header>'
        f'<nav class="section-nav" aria-label="보고서 주요 항목"><a class="nav-chip" href="#summary">결론</a>'
        f'<a class="nav-chip" href="#deviations">문제와 개선</a><a class="nav-chip" href="#improvement-candidates">다음 개선</a>'
        f'<a class="nav-chip" href="#tests-metrics">검증 근거</a><a class="nav-chip" href="#evidence-vault">원본 증거</a></nav>'
    )
    footer = ('<footer class="report-footer"><p>Material Design 3의 공식 color role, type scale, shape scale, '
              'adaptive breakpoint, state layer, 접근성 지침을 적용한 네트워크 독립형 정적 보고서입니다.</p>'
              '<p><a href="https://m3.material.io/foundations">Material 3 Foundations</a> · '
              '<a href="https://m3.material.io/styles/color/roles">Color roles</a> · '
              '<a href="https://m3.material.io/foundations/layout/breakpoints/overview">Breakpoints</a></p></footer>')
    main = f'<main id="report">{human_sections}{technical_sections}{footer}</main>'
    head = ('<!doctype html><html lang="ko"><head>' + "".join(META_STATIC[:-1])
            + '<meta name="hwahap-source-sha256" content="' + esc(source_digest) + '">' + META_STATIC[-1]
            + '<title>Hwahap 실행 결과 · 문제, 개선, 근거</title>' + style + '</head><body>')
    return (head + app_header + main + '</body></html>').encode("utf-8")


class _ReportContentParser(HTMLParser):
    """Collect generated report text and attribute values, excluding markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []
        self.text_segments: list[list[str]] = [[]]
        self.tag_counts: dict[str, int] = {}
        self.id_values: list[str] = []

    def _append_attributes(self, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value is not None:
                self.id_values.append(value)
        self.values.extend(value for _, value in attrs if value is not None)

    def _append_text_boundary(self, tag: str) -> None:
        if tag in REPORT_TEXT_BOUNDARIES and self.text_segments[-1]:
            self.text_segments.append([])

    def _validate_markup(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        names = [name for name, _ in attrs]
        if tag not in REPORT_TAGS or any(name not in REPORT_ATTRS for name in names) or len(names) != len(set(names)):
            raise ValueError("unsupported report markup")
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._validate_markup(tag, attrs)
        self._append_text_boundary(tag)
        self._append_attributes(attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._validate_markup(tag, attrs)
        self._append_text_boundary(tag)
        self._append_attributes(attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag not in REPORT_TAGS:
            raise ValueError("unsupported report markup")
        self._append_text_boundary(tag)

    def handle_data(self, data: str) -> None:
        self.values.append(data)
        if data:
            self.text_segments[-1].append(data)

    def handle_comment(self, data: str) -> None:
        raise ValueError("unsupported report markup")

    def handle_pi(self, data: str) -> None:
        raise ValueError("unsupported report markup")

    def handle_decl(self, decl: str) -> None:
        if decl != "doctype html":
            raise ValueError("unsupported report markup")

    def unknown_decl(self, data: str) -> None:
        raise ValueError("unsupported report markup")


def validate_report_bytes(data: bytes, source_digest: str, payload: dict) -> bool:
    _validate_report_payload(payload, source_digest)
    text = data.decode("utf-8")
    parser = _ReportContentParser()
    parser.feed(text)
    parser.close()
    expected_ledger = _payload_ledger_block(payload)
    if text.count(expected_ledger) != 1:
        raise ValueError("report data ledger mismatch")
    if any(contains_sensitive_data(value) for value in parser.values) or any(
            contains_sensitive_data("".join(segment)) for segment in parser.text_segments if segment):
        raise ValueError("credential-bearing report content is unsafe")
    source_meta = f'<meta name="hwahap-source-sha256" content="{html.escape(source_digest, quote=True)}">'
    static_fragments = (*META_STATIC, source_meta, STYLE_BLOCK)
    if parser.tag_counts.get("meta") != len(META_STATIC) + 1:
        raise ValueError("report static structure count mismatch")
    if parser.tag_counts.get("script", 0) != 0 or parser.tag_counts.get("link", 0) != 0 or parser.tag_counts.get("style") != 1:
        raise ValueError("report static structure count mismatch")
    if any(text.count(fragment) != 1 for fragment in static_fragments):
        raise ValueError("report static structure mismatch")
    for ident in REPORT_IDS:
        if f'id="{ident}"' not in text:
            raise ValueError(f"missing report section: {ident}")
    if len(parser.id_values) != len(REPORT_STATIC_IDS) or set(parser.id_values) != REPORT_STATIC_IDS:
        raise ValueError("report ids are not unique or complete")
    if f'<meta name="hwahap-source-sha256" content="{html.escape(source_digest, quote=True)}">' not in text:
        raise ValueError("source digest mismatch")
    required_material = (
        '<meta name="material-design-system" content="Material Design 3">',
        '<meta name="material-theme-source" content="Material Design 3 official guidance">',
        '<meta name="color-theme-name" content="Icy Blue">',
        '<meta name="color-theme-seed" content="#C2E7FF">',
        '<meta name="color-theme-source" content="https://coolors.co/tailwind/c2e7ff">',
        '<meta name="material-foundations-pages" content="68">',
        '<meta name="material-source-url" content="https://m3.material.io/foundations">',
        "--md-sys-color-primary:#007acc", "--md-sys-color-on-primary:#fff",
        "--md-sys-color-primary-container:#ccebff", "--md-sys-color-surface:#fbfdff",
        "--md-sys-color-surface-container-low:#f7fcff", "--md-sys-color-on-surface:#001f33",
        "--md-sys-color-on-surface-variant:#003d66", "--md-sys-color-outline:#005c99",
        "--md-sys-color-outline-variant:#99d6ff", "--md-ref-typeface-brand", "--space-12:48px",
        "--md-sys-typescale-display-large",
        "--md-sys-typescale-headline-medium", "--md-sys-typescale-title-large",
        "--md-sys-typescale-body-large", "--md-sys-typescale-label-large",
        "--md-sys-shape-corner-none", "--md-sys-shape-corner-extra-small",
        "--md-sys-shape-corner-extra-extra-large", "--md-sys-shape-corner-full",
        "--md-sys-elevation-level0", "--md-sys-elevation-level1",
        "--md-sys-motion-standard-effects", "--md-sys-state-hover-opacity:.08",
        ".hero{display:grid", ".panel{min-width:0;overflow:hidden}", ".panel-head{display:flex",
        ".md-card{min-width:0;border-radius:", ".md-card-filled{background:",
        ".md-card-elevated{background:", ".summary-grid{display:grid", ".change-field{",
        "prefers-color-scheme:dark", "prefers-contrast:more", "prefers-reduced-motion:reduce",
        "@media (max-width:599px)", "@media (min-width:600px) and (max-width:839px)",
        "@media (min-width:840px)", "@media (min-width:1200px)", "@media (min-width:1600px)",
        '<a class="skip-link" href="#summary">', 'aria-label="보고서 주요 항목"',
        "무엇이 문제였고 어떻게 개선했나", "이전 문제", "발생 원인", "적용한 개선",
        "이전 대비 기대 변화", "아직 남은 위험", "다음에 개선할 수 있는 것",
        "Material 3 Foundations", "Color roles", "Breakpoints", '<aside class="supporting-pane"',
        '<details id="evidence-vault" class="evidence-vault">',
    )
    if any(fragment not in text for fragment in required_material):
        raise ValueError("Material report theme contract is incomplete")
    forbidden_card_treatment = (
        ".panel{min-width:0;background:",
        ".card,.receipt,.proposal-card,.risk-card{min-width:0;padding:var(--space-5);border",
        ".evidence-vault{border:1px",
        "border-block-start:4px solid var(--md-sys-color-secondary)",
        "border-block-start:4px solid var(--md-sys-color-error)",
        "border-inline-start:4px solid var(--md-sys-color-primary)",
    )
    if any(fragment in text for fragment in forbidden_card_treatment):
        raise ValueError("Material card variants must not use blanket outlines")
    if any(forbidden in text for forbidden in ("Astryx", "astryx", "OpenDesign", "opendesign", "#1a73e8", "ReactDOM", "react-dom", "importmap", '<script')):
        raise ValueError("legacy report dependency remains")
    ordered_ids = ("summary", "deviations", "improvement-candidates", "next-actions", "tests-metrics",
                   "evidence-vault", "contract", "agents", "units", "timeline", "reviews", "scope-audit",
                   "failures-recovery", "provenance", "report-data")
    positions = [text.find(f'id="{ident}"') for ident in ordered_ids]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise ValueError("report reading order is invalid")
    return True

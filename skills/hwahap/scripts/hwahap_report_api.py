"""Import the verified report graph and bind its credential engine."""

import hwahap_report_credential_dependency as credential
import hwahap_report_types as types
import hwahap_report_assets as assets
import hwahap_report_security as security
import hwahap_report_clean as clean
import hwahap_report_unit as unit
import hwahap_report_goal as goal
import hwahap_report_assemble as assemble
import hwahap_report_payload as payload
import hwahap_report_canonical as canonical
import hwahap_report_ledger as ledger
import hwahap_report_view as view
import hwahap_report_core_sections as core_sections
import hwahap_report_review_sections as review_sections
import hwahap_report_metrics as metrics
import hwahap_report_changes as changes
import hwahap_report_provenance as provenance
import hwahap_report_human as human
import hwahap_report_evidence as evidence
import hwahap_report_render as render
import hwahap_report_parser as parser
import hwahap_report_validate as validate

security._module = credential
modules = {
    "types": types, "assets": assets, "security": security, "clean": clean,
    "unit": unit, "goal": goal, "assemble": assemble, "payload": payload,
    "canonical": canonical, "ledger": ledger, "view": view,
    "core_sections": core_sections, "review_sections": review_sections,
    "metrics": metrics, "changes": changes, "provenance": provenance,
    "human": human, "evidence": evidence, "render": render,
    "parser": parser, "validate": validate,
}

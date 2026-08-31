"""Shared credential detection and redaction API."""

from hwahap_credential_detect import credential_bearing_text, findings, redact
from hwahap_credential_normalize import is_redacted, normalized_text, view
from hwahap_credential_patterns import (
    ASSIGNMENT_CREDENTIAL,
    AUTH_HEADER_CREDENTIAL,
    BEARER_CREDENTIAL,
    CREDENTIAL_URL,
    CURL_CREDENTIAL,
    FLAG_CREDENTIAL,
    HEADER_CREDENTIAL,
    PEM,
    PROVIDER_TOKEN,
    HIGH_ENTROPY,
)
from hwahap_credential_types import CredentialFinding, NormalizedView

contains_sensitive_data = credential_bearing_text

__all__ = (
    "ASSIGNMENT_CREDENTIAL", "AUTH_HEADER_CREDENTIAL", "BEARER_CREDENTIAL",
    "CREDENTIAL_URL", "CURL_CREDENTIAL", "FLAG_CREDENTIAL",
    "HEADER_CREDENTIAL", "PEM", "PROVIDER_TOKEN", "HIGH_ENTROPY",
    "CredentialFinding", "NormalizedView", "contains_sensitive_data",
    "credential_bearing_text", "findings", "is_redacted", "normalized_text",
    "redact", "view",
)

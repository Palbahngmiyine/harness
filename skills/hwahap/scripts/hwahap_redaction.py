"""Backward-compatible redaction API backed by the shared credential engine."""

from hwahap_credentials import (
    ASSIGNMENT_CREDENTIAL, AUTH_HEADER_CREDENTIAL, BEARER_CREDENTIAL,
    CREDENTIAL_URL, CURL_CREDENTIAL, FLAG_CREDENTIAL, HEADER_CREDENTIAL, PEM,
    PROVIDER_TOKEN, HIGH_ENTROPY, CredentialFinding, NormalizedView,
    credential_bearing_text, findings, is_redacted, normalized_text, redact, view,
)
from hwahap_credential_normalize import _views

ASSIGNMENT_SECRET_PATTERN = ASSIGNMENT_CREDENTIAL
AUTH_HEADER_SECRET_PATTERN = AUTH_HEADER_CREDENTIAL
HEADER_SECRET_PATTERN = HEADER_CREDENTIAL
BEARER_TOKEN_PATTERN = BEARER_CREDENTIAL
SECRET_FLAG_PATTERN = FLAG_CREDENTIAL
CURL_AUTH_PATTERN = CURL_CREDENTIAL
CREDENTIAL_URL_PATTERN = CREDENTIAL_URL
PEM_PRIVATE_KEY_PATTERN = PEM
PROVIDER_TOKEN_PATTERN = PROVIDER_TOKEN
HIGH_ENTROPY_SECRET_PATTERN = HIGH_ENTROPY
SensitiveDataFinding = CredentialFinding
contains_sensitive_data = credential_bearing_text

__all__ = (
    "ASSIGNMENT_SECRET_PATTERN", "AUTH_HEADER_SECRET_PATTERN",
    "HEADER_SECRET_PATTERN", "BEARER_TOKEN_PATTERN", "SECRET_FLAG_PATTERN",
    "CURL_AUTH_PATTERN", "CREDENTIAL_URL_PATTERN", "PEM_PRIVATE_KEY_PATTERN",
    "PROVIDER_TOKEN_PATTERN", "HIGH_ENTROPY_SECRET_PATTERN", "NormalizedView",
    "SensitiveDataFinding", "contains_sensitive_data", "findings", "is_redacted",
    "normalized_text", "redact", "view",
)

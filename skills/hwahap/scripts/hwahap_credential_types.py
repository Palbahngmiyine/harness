"""Credential detector value types."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedView:
    raw: str
    text: str
    origins: tuple[int, ...]


@dataclass(frozen=True)
class CredentialFinding:
    kind: str
    start: int
    end: int
    value_start: int = 0
    value_end: int = 0
    scheme: str = ""
    normalized_start: int = 0
    normalized_end: int = 0
    normalized_value_start: int = 0
    normalized_value_end: int = 0

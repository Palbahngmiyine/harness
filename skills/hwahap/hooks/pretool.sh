#!/bin/bash
# Capture PreToolUse payloads during the U1 platform probe.
set -euo pipefail
if [ "${HWAHAP_PROBE_DECISION:-}" = deny ]; then
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"U1 probe denial"}}'
  exit 0
fi
if [ -n "${HWAHAP_PROBE_DIR:-}" ]; then
  mkdir -p "$HWAHAP_PROBE_DIR"
  /usr/bin/tee "$HWAHAP_PROBE_DIR/PreToolUse.json" >/dev/null
fi

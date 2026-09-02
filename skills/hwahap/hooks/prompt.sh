#!/bin/bash
# Capture UserPromptSubmit payloads during the U1 platform probe.
set -euo pipefail
if [ -n "${HWAHAP_PROBE_DIR:-}" ]; then
  mkdir -p "$HWAHAP_PROBE_DIR"
  /usr/bin/tee "$HWAHAP_PROBE_DIR/UserPromptSubmit.json" >/dev/null
fi

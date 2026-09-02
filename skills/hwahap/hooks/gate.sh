#!/bin/bash
# Capture Stop payloads during the U1 platform probe.
set -euo pipefail
if [ "${HWAHAP_PROBE_DECISION:-}" = block ]; then
  payload=$(</dev/stdin)
  if [ "$(printf '%s' "$payload" | jq -r '.stop_hook_active')" = false ]; then
    printf '%s\n' '{"decision":"block","reason":"U1 probe continuation"}'
  fi
  exit 0
fi
if [ -n "${HWAHAP_PROBE_BACKGROUND_PID:-}" ]; then
  nohup sleep 30 >/dev/null 2>&1 &
  printf '%s\n' "$!" >"$HWAHAP_PROBE_BACKGROUND_PID"
fi
if [ -n "${HWAHAP_PROBE_DIR:-}" ]; then
  mkdir -p "$HWAHAP_PROBE_DIR"
  /usr/bin/tee "$HWAHAP_PROBE_DIR/Stop.json" >/dev/null
fi

#!/bin/bash
# Run every deterministic Hwahap v2 fixture and fuzz harness once.
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
tests=(brief-usage.sh boundary.sh capture-posttool.sh check.sh coverage-contract.sh deliver.sh e2e.sh gate.sh integrate.sh pretool-posttool.sh prompt.sh templates.sh)
for test_file in "${tests[@]}"; do bash "$root/$test_file"; done
for test_file in "$root"/fuzz/*.sh; do bash "$test_file"; done
bash "$root/lint-conditions.sh"
bash "$root/lint-messages.sh"
printf 'all deterministic suites pass\n'

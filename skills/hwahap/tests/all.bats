#!/usr/bin/env bats
# Expose each deterministic harness as an independent Bats test.
setup() { root=$(cd "$BATS_TEST_DIRNAME" && pwd); }
@test "goal contract" { run bash "$root/check.sh"; [ "$status" -eq 0 ]; }
@test "answer recording" { run bash "$root/prompt.sh"; [ "$status" -eq 0 ]; }
@test "brief and usage" { run bash "$root/brief-usage.sh"; [ "$status" -eq 0 ]; }
@test "worker capture" { run bash "$root/capture-posttool.sh"; [ "$status" -eq 0 ]; }
@test "execution gates" { run bash "$root/pretool-posttool.sh"; [ "$status" -eq 0 ]; }
@test "integration" { run bash "$root/integrate.sh"; [ "$status" -eq 0 ]; }
@test "stop gate" { run bash "$root/gate.sh"; [ "$status" -eq 0 ]; }
@test "delivery" { run bash "$root/deliver.sh"; [ "$status" -eq 0 ]; }
@test "API-free lifecycle" { run bash "$root/e2e.sh"; [ "$status" -eq 0 ]; }
@test "parallel boundaries" { run bash "$root/boundary.sh"; [ "$status" -eq 0 ]; }
@test "coverage parser" { run bash "$root/coverage-contract.sh"; [ "$status" -eq 0 ]; }
@test "goal fuzz" { run bash "$root/fuzz/goal.sh"; [ "$status" -eq 0 ]; }
@test "answer fuzz" { run bash "$root/fuzz/answers.sh"; [ "$status" -eq 0 ]; }
@test "command fuzz" { run bash "$root/fuzz/command.sh"; [ "$status" -eq 0 ]; }
@test "patch fuzz" { run bash "$root/fuzz/patch.sh"; [ "$status" -eq 0 ]; }
@test "structural lint" { run bash "$root/lint-conditions.sh"; [ "$status" -eq 0 ]; }
@test "documented templates" { run bash "$root/templates.sh"; [ "$status" -eq 0 ]; }
@test "hook messages have fixtures" { run bash "$root/lint-messages.sh"; [ "$status" -eq 0 ]; }
@test "improve start gate" { run bash "$root/improve-gate.sh"; [ "$status" -eq 0 ]; }

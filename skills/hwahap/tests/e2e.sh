#!/bin/bash
# Drive align, worker, review, integration, gate, and draft delivery without an API.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-e2e.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo" remote="$tmp/origin.git" codex_home="$tmp/codex"
shim="$root/tests/fixtures/bin"
git init -q --bare "$remote"
mkdir -p "$repo/src" "$repo/.hwahap/out/review"
git -C "$repo" init -q -b main
git -C "$repo" config user.email fixture@example.com
git -C "$repo" config user.name Fixture
printf 'base\n' >"$repo/src/check.sh"; git -C "$repo" add src; git -C "$repo" commit -qm base
git -C "$repo" remote add origin "$remote"; git -C "$repo" push -q -u origin main
jq --arg parallel "${HWAHAP_E2E_MAX_PARALLEL:-3}" '.goal_id="e2e" | .goal.statement="e2e fixture" | .units[0].test="grep -q shim src/check.sh" | .full_suite="grep -q shim src/check.sh" | .budget.max_parallel=($parallel|tonumber)' \
  "$root/tests/fixtures/check/valid/goal.json" >"$repo/.hwahap/goal.json"

prompt() { jq -nc --arg cwd "$repo" --arg prompt "$1" '{cwd:$cwd,prompt:$prompt}' | CODEX_HOME="$codex_home" HWAHAP_NOW=2026-09-02T00:00:00Z "$root/hooks/prompt.sh"; }
prompt 'C1=ALT1 C2=ALT1 S2=NA S3=NA S4=NA S5=NA S6=NA S7=NA S8=NA S9=NA S10=NA S11=NA S12=NA'
jq --slurpfile a "$repo/.hwahap/answers.jsonl" '.choices |= map(. as $c | .answer.choice_sha256=([$a[]|select(.key==$c.id)][-1].bound_sha256)) | .surfaces.not_applicable |= with_entries(.key as $k | .value.answer.hash=([$a[]|select(.key==$k)][-1].bound_sha256))' "$repo/.hwahap/goal.json" >"$tmp/goal"; mv "$tmp/goal" "$repo/.hwahap/goal.json"
jq -r --rawfile head "$root/data/brief.head.md" --arg mode cold --arg unit '' --arg patch '' --arg question '' -f "$root/jq/brief.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/out/review/cold.brief.md"
cold='codex exec -C . -s read-only --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=medium --ephemeral -o .hwahap/out/review/cold.md'
payload=$(jq -nc --arg cwd "$repo" --arg command "$cold" '{cwd:$cwd,tool_input:{command:$command}}'); test -z "$(cd "$repo" && "$root/hooks/pretool.sh" <<<"$payload")"
(cd "$repo" && PATH="$shim:$PATH" CODEX_SHIM_LOG="$tmp/codex.log" codex exec -C . -s read-only --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=medium --ephemeral -o .hwahap/out/review/cold.md <.hwahap/out/review/cold.brief.md)
test "$(cd "$repo" && HWAHAP_NOW=2026-09-02T00:00:00Z "$root/hooks/posttool.sh" <<<"$payload")" = 'cold review pass'
jq -r -f "$root/jq/render.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/align.md"; prompt 'CONFIRM ALIGN'
jq --slurpfile a "$repo/.hwahap/answers.jsonl" '([$a[]|select(.key=="CONFIRM")][-1]) as $c | .confirm={text:$c.text,ts:$c.ts,revision:.revision,goal_sha256:$c.bound_sha256,render_sha256:$c.render_sha256}' "$repo/.hwahap/goal.json" >"$tmp/goal"; mv "$tmp/goal" "$repo/.hwahap/goal.json"

git -C "$repo" worktree add -q --detach .hwahap/wt/U1 HEAD
jq -r --rawfile head "$root/data/brief.head.md" --arg mode worker --arg unit U1 --arg patch '' --arg question '' -f "$root/jq/brief.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/out/U1.brief.md"
worker='codex exec -C .hwahap/wt/U1 -s workspace-write --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=high -c model_verbosity=low -c model_reasoning_summary=none -c web_search=disabled -c tool_output_token_limit=4000 --ephemeral --json -o .hwahap/out/U1.last.md'
payload=$(jq -nc --arg cwd "$repo" --arg command "$worker" '{cwd:$cwd,tool_input:{command:$command}}')
test -z "$(cd "$repo" && CODEX_HOME="$codex_home" "$root/hooks/pretool.sh" <<<"$payload")"
(cd "$repo" && PATH="$shim:$PATH" CODEX_SHIM_LOG="$tmp/codex.log" CODEX_SHIM_PATH=src/check.sh codex exec -C .hwahap/wt/U1 -s workspace-write --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=high -c model_verbosity=low -c model_reasoning_summary=none -c web_search=disabled -c tool_output_token_limit=4000 --ephemeral --json -o .hwahap/out/U1.last.md <.hwahap/out/U1.brief.md >.hwahap/out/U1.events.jsonl)
case "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" in 'U1 pass '*) ;; *) exit 1 ;; esac

jq -r --rawfile head "$root/data/brief.head.md" --rawfile patch "$repo/.hwahap/out/U1.patch" --arg mode review --arg unit U1 --arg question '' -f "$root/jq/brief.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/out/review/U1.brief.md"
review='codex exec -C .hwahap/wt/U1 -s read-only --ignore-user-config -m gpt-5.6-terra -c model_reasoning_effort=high --ephemeral -o .hwahap/out/review/U1.md'
payload=$(jq -nc --arg cwd "$repo" --arg command "$review" '{cwd:$cwd,tool_input:{command:$command}}')
test -z "$(cd "$repo" && "$root/hooks/pretool.sh" <<<"$payload")"
(cd "$repo" && PATH="$shim:$PATH" CODEX_SHIM_LOG="$tmp/codex.log" codex exec -C .hwahap/wt/U1 -s read-only --ignore-user-config -m gpt-5.6-terra -c model_reasoning_effort=high --ephemeral -o .hwahap/out/review/U1.md <.hwahap/out/review/U1.brief.md)
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'U1 review pass integration=pass'

git -C "$repo/.hwahap/wt/integration" diff HEAD >"$repo/.hwahap/out/integration.patch"
jq -r --rawfile head "$root/data/brief.head.md" --rawfile patch "$repo/.hwahap/out/integration.patch" --arg mode review --arg unit integration --arg question '' -f "$root/jq/brief.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/out/review/integration.brief.md"
final='codex exec -C .hwahap/wt/integration -s read-only --ignore-user-config -m gpt-5.6-terra -c model_reasoning_effort=high --ephemeral -o .hwahap/out/review/integration.md'
payload=$(jq -nc --arg cwd "$repo" --arg command "$final" '{cwd:$cwd,tool_input:{command:$command}}')
test -z "$(cd "$repo" && "$root/hooks/pretool.sh" <<<"$payload")"
(cd "$repo" && PATH="$shim:$PATH" CODEX_SHIM_LOG="$tmp/codex.log" codex exec -C .hwahap/wt/integration -s read-only --ignore-user-config -m gpt-5.6-terra -c model_reasoning_effort=high --ephemeral -o .hwahap/out/review/integration.md <.hwahap/out/review/integration.brief.md)
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'integration review pass'

payload=$(jq -nc --arg cwd "$repo" '{cwd:$cwd,stop_hook_active:false}')
test -z "$(cd "$repo" && PATH="$shim:$PATH" CODEX_HOME="$codex_home" GH_MODE=success "$root/hooks/gate.sh" <<<"$payload")"
jq -e '.deliver=="done" and .pr_url=="https://example.test/new" and .units_passed==1' "$repo/.hwahap/summary.json" >/dev/null
test "$(wc -l <"$tmp/codex.log")" -eq 4
git --git-dir="$remote" show-ref --verify --quiet refs/heads/hwahap/e2e
if [ -n "${HWAHAP_E2E_RESULT:-}" ]; then { for file in U1.patch U1.test.txt integration.test.txt review/U1.md review/integration.md; do shasum -a 256 "$repo/.hwahap/out/$file" | awk -v file="$file" '{print file, $1}'; done; jq -S 'del(.config.max_parallel)' "$repo/.hwahap/summary.json"; } >"$HWAHAP_E2E_RESULT"; fi
printf 'e2e align worker review integrate gate deliver\n'

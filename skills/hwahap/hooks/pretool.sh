#!/bin/bash
# Deny codex exec calls that cross the fixed template or build gates.
set -euo pipefail
digest() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; } # MUTATION-IGNORE equivalent digest providers
[ "${HWAHAP_DISABLE_HOOKS:-}" = 1 ] && exit 0; template='codex exec -C <path> -s <mode> --ignore-user-config -m <model> -c model_reasoning_effort=<effort> --ephemeral; worker also requires --json -o <file> and the three fixed -c flags'
deny() {
  reason=$1; printf 'hwahap pretool: %s\ncorrect template: %s\n' "$reason" "$template" >&2
  jq -nc --arg reason "$reason. Correct template: $template" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
  exit 0
}
payload=$(</dev/stdin)
printf '%s' "$payload" | jq -e . >/dev/null 2>&1 || { printf 'hwahap pretool: invalid hook payload\n' >&2; exit 1; }
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty')
command=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')
[ -n "$cwd" ] || exit 0
cd "$cwd" || exit 0
[ -f .hwahap/goal.json ] || exit 0
case "$command" in codex\ exec\ *) ;; *) exit 0 ;; esac
skill=$(cd "$(dirname "$0")/.." && pwd)
workdir=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-C"){print $(i+1); exit}}')
sandbox=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-s"){print $(i+1); exit}}'); output=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-o"){print $(i+1); exit}}')
for required in ' --ignore-user-config ' ' -m ' ' -c model_reasoning_effort=' ' --ephemeral'; do case "$command" in *"$required"*) ;; *) deny 'required codex exec flags are missing' ;; esac; done
if [ "$workdir" = . ]; then
  [ "$sandbox" = read-only ] || deny 'fact and cold review require -s read-only'
  case "$output" in .hwahap/facts/F*.md|.hwahap/out/review/cold.md) ;; *) deny 'fact or cold review output path is invalid' ;; esac
  exit 0
fi
case "$workdir" in .hwahap/wt/U*|.hwahap/wt/P*|.hwahap/wt/integration) ;; *) deny 'unknown worktree path' ;; esac; unit=${workdir##*/}
if [ "$sandbox" = read-only ]; then
  [ "$output" = ".hwahap/out/review/$unit.md" ] || deny 'reviewer output path is invalid'; rounds=0; [ ! -f ".hwahap/out/review/$unit.attempt" ] || rounds=$(<".hwahap/out/review/$unit.attempt")
  [ "$rounds" -lt 2 ] || deny 'reviewer retry limit reached'; exit 0
fi
[ "$sandbox" = workspace-write ] || deny 'worker requires -s workspace-write'
for required in ' --json ' ' -o ' ' -c model_verbosity=low ' ' -c model_reasoning_summary=none ' ' -c web_search=disabled '; do
  case "$command" in *"$required"*) ;; *) deny 'worker flags are incomplete' ;; esac
done
jq -e --arg unit "$unit" 'any(.units[]; .id==$unit)' .hwahap/goal.json >/dev/null || deny 'unknown worker unit'
probe=$(jq -r --arg unit "$unit" '.units[] | select(.id==$unit) | .probe' .hwahap/goal.json)
if [ "$probe" = false ]; then
  jq -e -f "$skill/jq/check.jq" .hwahap/goal.json >/dev/null 2>&1 || deny 'goal contract is invalid'
  repo=$(git rev-parse --show-toplevel)
  repo_id=$(printf '%s' "$repo" | digest | awk '{print $1}' | cut -c1-16)
  outside="${CODEX_HOME:-$HOME/.codex}/hwahap/$repo_id/answers.jsonl"
  [ -f .hwahap/answers.jsonl ] || deny 'workspace answer ledger is missing'
  [ -f "$outside" ] || deny 'outside answer ledger is missing'
  while IFS= read -r line; do grep -Fqx "$line" "$outside" || deny 'answer ledger copies differ'; done <.hwahap/answers.jsonl
  jq -e --slurpfile a .hwahap/answers.jsonl 'all(.choices[] | select(.answer!=null); . as $c | any($a[]; .key==$c.id and .text==$c.answer.text and .bound_sha256==$c.answer.choice_sha256)) and all(.surfaces.not_applicable | to_entries[]; . as $s | any($a[]; .key==$s.key and .text==$s.value.answer.text and .bound_sha256==$s.value.answer.hash)) and all(.rounds[] | select((.n%4)==0); . as $r | any($a[]; .key==("CP"+(($r.n/4)|tostring)) and .text==$r.checkpoint.answer.text and .bound_sha256==$r.checkpoint.answer.hash)) and (.confirm as $c | any($a[]; .key=="CONFIRM" and .bound_sha256==$c.goal_sha256 and .render_sha256==$c.render_sha256))' .hwahap/goal.json >/dev/null || deny 'goal answers are not bound to the user ledger'
  goal_hash=$(jq -S -c 'del(.review,.confirm)' .hwahap/goal.json | digest | awk '{print "sha256:" $1}')
  [ "$(jq -r '.review.cold.goal_sha256 // empty' .hwahap/goal.json)" = "$goal_hash" ] || deny 'cold review is stale'
  [ "$(jq -r '.confirm.goal_sha256 // empty' .hwahap/goal.json)" = "$goal_hash" ] || deny 'confirmation goal hash is stale'
  jq -e '.confirm.revision==.revision' .hwahap/goal.json >/dev/null || deny 'confirmation revision is stale'
  render_hash=$(jq -r -f "$skill/jq/render.jq" .hwahap/goal.json | digest | awk '{print "sha256:" $1}')
  [ "$(jq -r '.confirm.render_sha256 // empty' .hwahap/goal.json)" = "$render_hash" ] || deny 'confirmed render is stale'
  jq -e 'any(.open_items[]; .status=="open") | not' .hwahap/goal.json >/dev/null || deny 'open items remain'
fi
brief=.hwahap/out/$unit.brief.md
[ -f "$brief" ] || deny 'worker brief is missing'
cmp -s "$brief" <(jq -r --rawfile head "$skill/data/brief.head.md" --arg mode worker --arg unit "$unit" --arg patch '' --arg question '' -f "$skill/jq/brief.jq" .hwahap/goal.json) || deny 'worker brief differs from goal'
brief_hash=$(digest "$brief" | awk '{print "sha256:" $1}')
if [ "${HWAHAP_NO_CACHE:-}" != 1 ]; then if [ -f ".hwahap/out/$unit.patch" ]; then
  if [ "$(tail -n 1 ".hwahap/out/$unit.test.txt" 2>/dev/null)" = 'exit 0' ]; then
    if [ "$(head -n 1 ".hwahap/out/review/$unit.md" 2>/dev/null)" = 'verdict: pass' ]; then
      if [ -f ".hwahap/out/$unit.brief.sha256" ]; then if [ "$(<".hwahap/out/$unit.brief.sha256")" = "$brief_hash" ]; then : >".hwahap/out/$unit.cached"; deny 'cached'; fi; fi
    fi
  fi
fi; fi
compgen -G '.hwahap/out/*.needs_decision' >/dev/null && deny 'a worker decision is unresolved'
used=0; usage_files=(.hwahap/out/*.usage.[0-9]*.json)
if [ -e "${usage_files[0]}" ]; then used=$(jq -s '[.[] | .input_tokens + .output_tokens] | add // 0' "${usage_files[@]}"); fi
budget=$(jq '.budget.tokens' .hwahap/goal.json)
if [ "$budget" -eq 0 ]; then deny 'token budget is exhausted'; fi
[ "$used" -lt "$budget" ] || deny 'token budget is exhausted'
attempt=0; [ ! -f ".hwahap/out/$unit.attempt" ] || attempt=$(<".hwahap/out/$unit.attempt")
[ "$attempt" -lt 2 ] || deny 'worker retry limit reached'
if [ "$attempt" -eq 0 ]; then while IFS= read -r dep; do
    git -C "$workdir" apply --check "../../out/$dep.patch" || deny "dependency $dep does not apply"
    git -C "$workdir" apply "../../out/$dep.patch"
  done < <(jq -r --arg unit "$unit" '.units[] | select(.id==$unit) | .depends_on[]' .hwahap/goal.json)
  git -C "$workdir" add -A; git -C "$workdir" write-tree >".hwahap/out/$unit.base-tree"; git -C "$workdir" reset >/dev/null
fi

#!/bin/bash
# Require every non-exempt shell and jq decision mutation to fail its focused suite.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-mutate.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
killed=0 total=0
target_tests() {
  case "$1" in
    prompt.sh) printf 'prompt.sh fuzz/answers.sh' ;;
    pretool.sh) printf 'pretool-posttool.sh fuzz/command.sh integrate.sh' ;;
    posttool.sh) printf 'capture-posttool.sh pretool-posttool.sh integrate.sh' ;;
    gate.sh) printf 'gate.sh' ;;
    capture.sh) printf 'capture-posttool.sh integrate.sh' ;;
    integrate.sh) printf 'integrate.sh fuzz/patch.sh' ;;
    deliver.sh) printf 'deliver.sh' ;;
    improve.sh) printf 'improve.sh' ;;
  esac
}
while IFS=: read -r file line _; do
  sed -n "${line}p" "$file" | grep -Fq 'MUTATION-IGNORE' && continue
  rm -rf "$tmp/skill"; cp -R "$root" "$tmp/skill"
  relative=${file#"$root/"}; mutant="$tmp/skill/$relative"
  awk -v n="$line" 'NR==n {if($0~/if ! /)sub(/if ! /,"if ");else sub(/if /,"if ! ")} {print}' "$mutant" >"$tmp/file"
  mv "$tmp/file" "$mutant"; chmod +x "$mutant"
  survived=0
  for test_file in $(target_tests "${file##*/}"); do if bash "$tmp/skill/tests/$test_file" >/dev/null 2>&1; then :; else survived=1; break; fi; done
  total=$((total+1)); if [ "$survived" -eq 1 ]; then killed=$((killed+1)); else printf 'survived shell mutant: %s:%s\n' "$relative" "$line" >&2; exit 1; fi
done < <(grep -nH -E '(^[[:space:]]*|[;{][[:space:]]*)if[[:space:]]+(![[:space:]]+)?(\[|\[\[|command|git|jq|grep)' "$root"/hooks/*.sh "$root"/hooks/lib/*.sh)
while IFS=: read -r file line _; do
  rm -rf "$tmp/skill"; cp -R "$root" "$tmp/skill"
  mutant="$tmp/skill/jq/check.jq"; sed "${line}d" "$mutant" >"$tmp/file"; mv "$tmp/file" "$mutant"
  total=$((total+1)); if bash "$tmp/skill/tests/check.sh" >/dev/null 2>&1 && bash "$tmp/skill/tests/fuzz/goal.sh" >/dev/null 2>&1; then printf 'survived jq mutant: check.jq:%s\n' "$line" >&2; exit 1; else killed=$((killed+1)); fi
done < <(grep -nH '| req' "$root/jq/check.jq")
test "$killed" -eq "$total"
printf 'mutation killed=%s total=%s score=100%%\n' "$killed" "$total"

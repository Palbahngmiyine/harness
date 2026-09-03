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
    usage.sh) printf 'brief-usage.sh capture-posttool.sh e2e.sh gate.sh pretool-posttool.sh templates.sh' ;;
    improve-gate.sh) printf 'improve-gate.sh' ;;
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
while IFS=: read -r file line occurrence; do
  sed -n "${line}p" "$file" | grep -Fq 'MUTATION-IGNORE' && continue
  rm -rf "$tmp/skill"; cp -R "$root" "$tmp/skill"
  relative=${file#"$root/"}; mutant="$tmp/skill/$relative"
  awk -v n="$line" -v wanted="$occurrence" '
    NR==n {
      rest=$0; offset=0; seen=0
      while(match(rest,/\|\|[[:space:]]*(deny|fail|exit|\{)/)) {
        seen++; marker=offset+RSTART
        if(seen==wanted) {
          before=substr($0,1,marker-1); start=1
          for(i=length(before);i>0;i--) if(substr(before,i,1)==";"){start=i+1;break}
          segment=substr(before,start); match(segment,/^[[:space:]]*/); insert=start+RLENGTH
          keyword=substr(before,insert)
          if(keyword~/^(do|then)[[:space:]]+/){match(keyword,/^(do|then)[[:space:]]+/);insert+=RLENGTH}
          $0=substr($0,1,insert-1) "! " substr($0,insert); break
        }
        consumed=RSTART+RLENGTH-1; offset+=consumed; rest=substr(rest,consumed+1)
      }
    }
    {print}' "$mutant" >"$tmp/file"
  mv "$tmp/file" "$mutant"; chmod +x "$mutant"
  survived=0
  for test_file in $(target_tests "${file##*/}"); do if bash "$tmp/skill/tests/$test_file" >/dev/null 2>&1; then :; else survived=1; break; fi; done
  total=$((total+1)); if [ "$survived" -eq 1 ]; then killed=$((killed+1)); else printf 'survived guard mutant: %s:%s:%s\n' "$relative" "$line" "$occurrence" >&2; exit 1; fi
done < <(awk '{text=$0; n=0; while(match(text,/\|\|[[:space:]]*(deny|fail|exit|\{)/)){n++; print FILENAME ":" FNR ":" n; text=substr(text,RSTART+RLENGTH)}}' "$root"/hooks/*.sh "$root"/hooks/lib/*.sh)
while IFS=: read -r file line _; do
  rm -rf "$tmp/skill"; cp -R "$root" "$tmp/skill"
  mutant="$tmp/skill/jq/check.jq"; sed "${line}d" "$mutant" >"$tmp/file"; mv "$tmp/file" "$mutant"
  total=$((total+1)); if bash "$tmp/skill/tests/check.sh" >/dev/null 2>&1 && bash "$tmp/skill/tests/fuzz/goal.sh" >/dev/null 2>&1; then printf 'survived jq mutant: check.jq:%s\n' "$line" >&2; exit 1; else killed=$((killed+1)); fi
done < <(grep -nH '| req' "$root/jq/check.jq")
test "$killed" -eq "$total"
test "$total" -gt 95
printf 'mutation killed=%s total=%s\n' "$killed" "$total"

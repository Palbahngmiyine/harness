#!/bin/bash
# Enforce line limits, artifact counts, strict modes, and single conditions.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
status=0
while IFS= read -r file; do
  lines=$(wc -l <"$file"); if [ "$lines" -gt 80 ]; then printf '%s exceeds 80 lines\n' "$file" >&2; status=1; fi
  sed -n '2,4p' "$file" | grep -Fq 'set -euo pipefail' || { printf '%s lacks strict mode\n' "$file" >&2; status=1; }
  if awk '/if .*(&&|\|\|).*then|\[[^]]*(&&|\|\|)[^]]*\]/{print FNR ":" $0; bad=1} END{exit bad}' "$file"; then :; else status=1; fi
done < <(find "$root/hooks" -type f -name '*.sh' -print | sort)
test "$(find "$root/hooks" -maxdepth 1 -type f -name '*.sh' | wc -l)" -le 4 || status=1
test "$(find "$root/hooks/lib" -type f -name '*.sh' | wc -l)" -le 4 || status=1
test "$(find "$root/jq" -type f -name '*.jq' | wc -l)" -le 4 || status=1
test "$(wc -l <"$root/SKILL.md")" -le 100 || status=1
test "$(wc -l <"$root/SURFACES.md")" -le 40 || status=1
exit "$status"

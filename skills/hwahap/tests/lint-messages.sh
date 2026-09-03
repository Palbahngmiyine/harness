#!/bin/bash
# Require every normalized hook deny and fail message to appear in a fixture.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
status=0
while IFS= read -r literal; do
  normalized=$(printf '%s\n' "$literal" | awk '{out=""; for(i=1;i<=NF;i++) if($i!~/^\$/) out=out (out==""?"":" ") $i; print out}')
  [ -n "$normalized" ] || continue
  if ! rg -F -q -- "$normalized" "$root/tests"; then printf 'untested hook message: %s\n' "$normalized" >&2; status=1; fi
done < <(awk '
  {
    text=$0
    while (match(text, /(deny|fail)[[:space:]]+["\047]/)) {
      quote=substr(text,RSTART+RLENGTH-1,1); rest=substr(text,RSTART+RLENGTH)
      stop=index(rest,quote); if(stop==0) break
      print substr(rest,1,stop-1); text=substr(rest,stop+1)
    }
  }' "$root"/hooks/*.sh "$root"/hooks/lib/*.sh)
exit "$status"

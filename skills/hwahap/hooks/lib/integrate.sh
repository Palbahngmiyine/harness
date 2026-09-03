#!/bin/bash
# Apply accepted unit patches in dependency order and run the full suite once.
set -euo pipefail
goal=.hwahap/goal.json
out=.hwahap/out/integration.test.txt
[ -f "$goal" ] || { printf 'hwahap integrate: goal.json is missing\n' >&2; exit 1; }
[ ! -f "$out" ] || exit 3
while IFS= read -r unit; do
  [ ! -f ".hwahap/out/$unit.skipped" ] || continue
  [ -f ".hwahap/out/$unit.patch" ] || exit 3
  [ "$(tail -n 1 ".hwahap/out/$unit.test.txt" 2>/dev/null)" = 'exit 0' ] || exit 3
  [ "$(head -n 1 ".hwahap/out/review/$unit.md" 2>/dev/null)" = 'verdict: pass' ] || exit 3
done < <(jq -r '.units[] | select(.probe|not) | .id' "$goal")
: >"$out"
mkdir -p .hwahap/wt
if [ ! -d .hwahap/wt/integration ]; then
  set +e; git worktree add -q --detach .hwahap/wt/integration HEAD >>"$out" 2>&1; rc=$?; set -e
  if [ "$rc" -ne 0 ]; then printf 'exit %s\n' "$rc" >>"$out"; exit "$rc"; fi
fi
order=$(jq -r 'def topo($left;$done): if ($left|length)==0 then $done else [$left[] as $id | select([.units[] | select(.id==$id) | .depends_on[]] as $deps | all($deps[]; . as $dep | $done | index($dep)!=null)) | $id] as $ready | if ($ready|length)==0 then error("dependency cycle") else topo([$left[] | select(. as $id | $ready | index($id)==null)]; $done+$ready) end end; . as $g | topo([.units[] | select(.probe|not) | .id];[])[]' "$goal")
set +e
for unit in $order; do
  [ ! -f ".hwahap/out/$unit.skipped" ] || continue
  [ ! -s ".hwahap/out/$unit.patch" ] || git -C .hwahap/wt/integration apply --check "../../out/$unit.patch" >>"$out" 2>&1
  rc=$?
  if [ "$rc" -ne 0 ]; then printf 'exit %s\n' "$rc" >>"$out"; exit "$rc"; fi
  [ ! -s ".hwahap/out/$unit.patch" ] || git -C .hwahap/wt/integration apply "../../out/$unit.patch" >>"$out" 2>&1
  rc=$?
  if [ "$rc" -ne 0 ]; then printf 'exit %s\n' "$rc" >>"$out"; exit "$rc"; fi
done
suite=$(jq -r '.full_suite' "$goal")
(cd .hwahap/wt/integration && /bin/bash -lc "$suite") >>"$out" 2>&1
rc=$?
set -e
printf 'exit %s\n' "$rc" >>"$out"
exit "$rc"

#!/bin/bash
# Detect worktree, process, and local-branch leaks around the full suite.
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
tests="$root/skills/hwahap/tests"
before_worktrees=$(git -C "$root" worktree list --porcelain)
before_processes=$(pgrep -f 'codex exec' 2>/dev/null | sort || true)
before_branches=$(git -C "$root" for-each-ref --format='%(refname)' refs/heads | sort)
bash "$tests/all.sh"
after_worktrees=$(git -C "$root" worktree list --porcelain)
after_processes=$(pgrep -f 'codex exec' 2>/dev/null | sort || true)
after_branches=$(git -C "$root" for-each-ref --format='%(refname)' refs/heads | sort)
test "$before_worktrees" = "$after_worktrees"
test "$before_processes" = "$after_processes"
test "$before_branches" = "$after_branches"
printf 'resources worktrees processes branches stable\n'

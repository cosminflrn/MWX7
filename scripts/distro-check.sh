#!/bin/bash
# Fast syntax check of the distro's Python and shell code, run by `npm test` (so CI catches a broken file from any
# PR before it ships in an update). Needs only python3 and bash.
set -e
cd "$(dirname "$0")/.."
fail=0
while IFS= read -r -d '' f; do
  python3 - "$f" <<'PY' || fail=1
import sys, ast
src = open(sys.argv[1], encoding='utf-8').read()
try:
    ast.parse(src, sys.argv[1])
except SyntaxError as e:
    print(f'{sys.argv[1]}:{e.lineno}: {e.msg}'); sys.exit(1)
PY
done < <(find distro/desktop -path '*/out/*' -prune -o -type f \( -name '*.py' -o -exec sh -c 'head -c 40 "$1" | grep -q "^#!.*python"' _ {} \; \) -print0)
while IFS= read -r -d '' f; do
  bash -n "$f" || fail=1
done < <(find distro/desktop -path '*/out/*' -prune -o -type f -exec sh -c 'head -c 40 "$1" | grep -qE "^#!.*(ba)?sh"' _ {} \; -print0)
[ $fail = 0 ] && echo "distro-check: ok" || { echo "distro-check: FAILED"; exit 1; }

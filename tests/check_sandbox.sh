#!/usr/bin/env bash
# Self-check for bin/sandbox-run: the container reaches no network, the source folder stays unchanged and /work is
# a git repository. Needs Docker and the image (SANDBOX_IMAGE, default pr-sandbox:py312).
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
src=$(mktemp -d "${TMPDIR:-/tmp}/sandbox-check.XXXXXX")
trap 'rm -rf "$src"' EXIT
echo original > "$src/file.txt"
out=$("$here/bin/sandbox-run" "$src" '
  python3 -c "import socket; socket.create_connection((\"1.1.1.1\", 53), 2)" 2>/dev/null && echo NET=yes || echo NET=no
  echo changed > file.txt && cat file.txt
  git rev-parse --is-inside-work-tree' 2>&1)
grep -qx 'NET=no' <<<"$out" || { echo "FAIL: the container reached the network"; exit 1; }
grep -qx 'changed' <<<"$out" || { echo "FAIL: /work is not writable"; exit 1; }
grep -qx 'true' <<<"$out" || { echo "FAIL: /work is not a git repository"; exit 1; }
[[ $(cat "$src/file.txt") == original ]] || { echo "FAIL: the source folder changed"; exit 1; }
echo "OK: no network, source folder unchanged, /work is a git repository"
"$here/merge-sweep/merge-bisect" --self-check
python3 "$here/merge-sweep/train.py" --self-check

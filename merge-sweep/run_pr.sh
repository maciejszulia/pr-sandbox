#!/usr/bin/env bash
# Container side of merge-sweep (runs with --network none). Reads a tar of the tree to test on stdin, extracts it to
# /work and runs each test file named in $TESTS. Prints one line per file:
#   RESULT <exit code> <file> <first failure line>
# Test selection follows the CI of ItsNotRexed/Leonida: a file with `import pytest`, `HAVE_NUMPY =` or no
# __main__ block runs under pytest; tests/semantic/* runs under unittest discover; every other file runs as
# `python -I <file>`. Change this block for a repository with another rule.
set -u
tar -x -C /work || exit 125
cd /work || exit 125
# Tests that list tracked files need a repository; build a throwaway one only when a test mentions git.
for t in $TESTS; do
  if [ -f "$t" ] && grep -q git "$t"; then
    export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'
    git init -q . && git add -A && git -c user.name=sweep -c user.email=sweep@localhost commit -qm snapshot
    break
  fi
done
markers='^import pytest|^ *HAVE_NUMPY ='
for t in $TESTS; do
  if [ ! -f "$t" ]; then echo "RESULT 404 $t missing"; continue; fi
  case $t in
    tests/semantic/*) timeout 240 python -m unittest discover -s tests/semantic -p "$(basename "$t")" > /tmp/out.log 2>&1; rc=$? ;;
    *) if grep -Eq "$markers" "$t" || ! grep -q '__main__' "$t"; then
         timeout 240 python -m pytest -q -p no:cacheprovider "$t" > /tmp/out.log 2>&1; rc=$?
       else
         timeout 240 python -I "$t" > /tmp/out.log 2>&1; rc=$?
       fi ;;
  esac
  echo "RESULT $rc $t $(grep -m1 -E '^(FAIL|ERROR)[: ]|^E +|Error:|FAILED ' /tmp/out.log | head -c 220 | tr '\n' ' ')"
done

# ADR 0004: The test runner follows the target repository's CI rule

## Status

Accepted. Introduced in commit `04542f1`.

## Context

A test file can pass under one runner and fail under another. A result only counts when the file runs the way the
target repository's CI runs it.

## Decision

The container picks the runner by the CI rule of `ItsNotRexed/Leonida`: `pytest` for a file with `import pytest`,
`HAVE_NUMPY =` or no `__main__` block; `python -m unittest discover` for `tests/semantic/*`; `python -I <file>` for
every other file.

## Consequences

- Results match the target repository's CI.
- Another target repository needs this block changed in `merge-sweep/run_pr.sh` and in `merge-sweep/merge-check`.

## Evidence

- `merge-sweep/run_pr.sh`
- `merge-sweep/merge-check`
- `README.md`, section "Limits"

# ADR 0002: Merge with `git merge-tree` and stream the tree with `git archive`

## Status

Accepted. Introduced in commit `04542f1`.

## Context

The sweep checks more than a thousand open pull requests against 1 `main` snapshot. A checkout and a merge in a
working tree per pull request would be slow and would leave state behind between pull requests.

## Decision

Each pull request head is fetched to `refs/sweep/<pr>`, merged into the `main` snapshot with
`git merge-tree --write-tree --no-messages`, and the resulting tree is streamed into the container with
`git archive --format=tar`. Exit code 1 of `git merge-tree` is recorded as a merge conflict.

## Consequences

- No working tree is touched; parallel workers can share 1 clone.
- Git 2.38 or newer is required.
- The same 3-way merge serves `merge-check`, `merge-bisect` and `train.py`.
- `git merge-tree` and `git archive` read untrusted objects on the host.

## Evidence

- `run()` and `docker()` in `merge-sweep/sweep.py`
- `merge-sweep/merge-check`
- `merged_rc()` in `merge-sweep/merge-bisect`
- `README.md`, sections "Quick start" and "How it works"
- commit `04542f1`

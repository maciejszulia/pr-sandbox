# ADR 0003: The merge train is local and pushes nothing

## Status

Accepted. Introduced in commit `59ad2d2`.

## Context

A maintainer wants to land many pull requests at once. Each merge can break a test that passes on every pull
request alone.

## Decision

`train.py` builds the train locally: `git merge-tree` merges each head onto the tip and `git commit-tree` makes a
merge commit with 2 parents. The test files of every merged pull request run once on the tip. Each test that fails
only on the train is bisected over the train; the pull request that broke it is dropped and the train is rebuilt,
for at most `ROUNDS` rounds (default 3). The script writes `train.json` and prints the push command; it pushes
nothing.

## Consequences

- The maintainer decides about the push. 1 push of the tip puts the whole train on `main`.
- A conflicting pull request is skipped, not resolved.
- The train is tested once per round instead of once per pull request.

## Evidence

- `merge-sweep/train.py`
- `self_check()` in `merge-sweep/train.py`
- `README.md`, section "How it works", step 5
- commit `59ad2d2`

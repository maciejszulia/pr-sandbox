# ADR 0001: Run pull request code in a container without network

## Status

Accepted. Introduced in commit `04542f1`.

## Context

The tools run tests from pull requests by unknown authors. Running that code on the host gives it the host's
network, files and credentials.

## Decision

Every test run uses a throwaway Docker container started with `--rm --network none --cap-drop ALL
--security-opt no-new-privileges --pids-limit 512`, a memory limit, a CPU limit and the host user's UID and GID.
The code reaches the container only as a read-only mount copied into a tmpfs (`bin/sandbox-run`) or as a tar
stream from `git archive` extracted into a tmpfs (`merge-sweep/run_pr.sh`, `merge-sweep/merge-check`).
`bin/sandbox-run` refuses a folder outside `SANDBOX_ROOTS`.

## Consequences

- Untrusted code reaches no network and cannot change files on the host.
- The test image must contain every test package in advance, because containers cannot install packages.
- The container shares the host kernel, so the sandbox is no boundary against code that attacks Docker or the
  kernel.

## Evidence

- `bin/sandbox-run`
- `docker()` in `merge-sweep/sweep.py`
- `merge-sweep/merge-check`
- `tests/check_sandbox.sh`
- `README.md`, section "Limits"
- commit `04542f1`

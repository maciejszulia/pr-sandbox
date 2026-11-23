# pr-sandbox

Runs untrusted repository code, and checks open pull requests against the current `main`, inside throwaway Docker
containers that have no network and cannot change the files on the host.

## Demo

`merge-check` runs one test file of a pull request three times: on `main`, on `main` merged with the PR (the same
3-way merge GitHub does) and on the PR head alone. This PR passes on its own head and breaks once merged:

```
$ merge-sweep/merge-check 4734 tests/test_find_hash_lookup.py
===== main snapshot (dde82f27e994337094afc476ded0b1426f6e87e2)
Ran 5 tests in 0.895s
OK
exit=0
===== main + PR #4734 head 40ac5f600 (845a9f72676e53cffaa5cfc4daee6e80af35ff55)
Ran 6 tests in 1.616s
FAILED (failures=3)
exit=1
===== PR #4734 head (40ac5f6000fd3d20c17eb5159d8b26954f1720b0)
Ran 5 tests in 0.851s
OK
exit=0
```

## Results

First run on [ItsNotRexed/Leonida](https://github.com/ItsNotRexed/Leonida) on 2026-11-23 (ThinkPad T470p,
i7-7700HQ, Docker 29.10.0). Full numbers and the machine: [results/2026-11-23-leonida.md](results/2026-11-23-leonida.md).

| What | Count |
|---|---|
| standard-library test files failing on `main` (of 438) | 16 |
| open PRs with Python changes and tests | 1,670 |
| PRs merge-checked in the first 20 minutes | 236 |
| candidates: a test fails only after the merge | 6 |

## Quick start

Needs Linux, Docker, git and the GitHub CLI (`gh`) for the sweep.

```sh
git clone git@github.com:maciejszulia/pr-sandbox.git && cd pr-sandbox
cp <target repo>/tests/requirements.txt image/requirements.txt   # optional: the target's test packages
docker build -t pr-sandbox:py312 image
tests/check_sandbox.sh                                           # no network, source unchanged, git in /work
bin/sandbox-run ~/lab/<repo> 'python -I tests/test_something.py'
```

Sweep the open pull requests of one repository:

```sh
git clone https://github.com/<owner>/<repo>.git ~/lab/<repo>-sweep
export SWEEP_REPO=<owner>/<repo> SWEEP_CLONE=~/lab/<repo>-sweep SWEEP_DIR=~/lab/<repo>-state
merge-sweep/sweep.py prepare       # fetch main, list the PRs to check
merge-sweep/sweep.py run           # results.jsonl, candidates.jsonl, baseline.json in SWEEP_DIR
merge-sweep/merge-check <pr> <test file>
```

## How it works

1. `bin/sandbox-run` mounts the folder read-only, copies it into a tmpfs and runs the command with
   `--network none`, `--cap-drop ALL`, `no-new-privileges`, a non-root user and memory, CPU and process limits.
   `/work` becomes a throwaway git repository, so tests that list tracked files work.
2. `merge-sweep/sweep.py run` fetches each PR head, merges it into one `main` snapshot with
   `git merge-tree --write-tree` (no working tree), streams the merged tree into the container with `git archive`
   and runs the test files the PR touches. A failing file is run once more on `main`; a candidate is a file that
   passes on `main` (or is new) and fails merged.
3. `merge-sweep/merge-check` shows the full output of one candidate on `main`, merged and on the PR head.

## Limits

- The container shares the host kernel. It keeps the code off the network and off the host files; it is a review
  sandbox, not a boundary against code that attacks Docker or the kernel.
- `git merge-tree`, `git archive` and `gh` run on the host and read the untrusted objects, as any clone does.
- Test selection in `merge-sweep/run_pr.sh` follows the CI rule of ItsNotRexed/Leonida (pytest for files with
  `import pytest` or no `__main__` block, `python -I` for the rest). Another repository needs that block changed.
- The sweep checks only PRs that change `.py` and `.md` files and touch `tests/`. Tests that need a GPU, Windows or
  files outside the repository are not covered.

## License and author

MIT. Maciej Szulia.

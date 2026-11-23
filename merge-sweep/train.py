#!/usr/bin/env python3
"""Merge train: merge many pull requests into main locally, test the train once, drop each PR that breaks a test.

    train.py <pr> [<pr> ...]     pull request numbers in merge order
    train.py --self-check

For each PR in order, `git merge-tree` merges its head onto the train tip; a conflict skips the PR, otherwise
`git commit-tree` makes a merge commit with the tip and the PR head as parents. The test files that the merged PRs
touch (sweep.tests_for) then run once on the train tip in the sandbox container. Each test that fails there and
passes on main (or is new) is bisected over the train; the PR whose merge first breaks it is dropped and the train
is rebuilt, for at most ROUNDS rounds (default 3).
Nothing is pushed. `git push origin <tip>:main` puts the whole train on main in 1 push; GitHub marks every PR whose
head reaches main as merged, so a bulk merge needs no API call per PR.
Env: SWEEP_CLONE, SWEEP_DIR (main.sha and open-prs.json from `sweep.py prepare`), SANDBOX_IMAGE, ROUNDS.
Writes SWEEP_DIR/train.json.
"""
import json
import os
import subprocess
import sys
import tempfile

import sweep


def fetch(pr):
    ref = "refs/sweep/%d" % pr
    ok = sweep.git("fetch", "-q", "--no-write-fetch-head", "origin", "+refs/pull/%d/head:%s" % (pr, ref)).returncode == 0
    return ref if ok else None


def build(base, prs, ref_of=fetch):
    """Merge each PR onto the tip in order. Return (tip, [(pr, merge commit)], [(pr, reason)])."""
    tip, merged, skipped = base, [], []
    for pr in prs:
        ref = ref_of(pr)
        merge = sweep.git("merge-tree", "--write-tree", "--no-messages", tip, ref, text=True) if ref else None
        if merge is None or merge.returncode != 0:
            skipped.append((pr, "conflict" if merge is not None and merge.returncode == 1 else "fetch or merge error"))
            continue
        commit = sweep.git("commit-tree", merge.stdout.split()[0], "-p", tip, "-p", ref,
                           "-m", "Merge pull request #%d (merge train)" % pr, text=True)
        if commit.returncode != 0:
            skipped.append((pr, "commit-tree: " + commit.stderr.strip()[:80]))
            continue
        tip = commit.stdout.strip()
        merged.append((pr, tip))
    return tip, merged, skipped


def failing(tests, tree):
    """{test file: first failure line} for each test that fails on tree. A file the tree lacks is no failure."""
    _, res = sweep.parse(sweep.docker(tests, tree))
    return {test: line for rc, test, line in res if rc not in (0, 404)}


def run(prs):
    rounds = int(os.environ.get("ROUNDS", "3"))
    main = sweep.MAIN_SHA = open(os.path.join(sweep.HERE, "main.sha"), encoding="utf-8").read().strip()
    files = {p["number"]: p["files"] for p in json.load(open(os.path.join(sweep.HERE, "open-prs.json")))}
    dropped, broken_on_main = [], {}
    for rnd in range(1, rounds + 1):
        tip, merged, skipped = build(main, [p for p in prs if p not in {d["pr"] for d in dropped}])
        tests = sorted({t for pr, _ in merged for t in sweep.tests_for(files.get(pr, []))})
        fails = failing(tests, tip) if tests else {}
        broken_on_main = failing([t for t in fails if sweep.on_main(t)], main) if fails else {}
        new = {t: line for t, line in fails.items() if t not in broken_on_main}
        print("round %d: %d merged, %d skipped, %d test files, %d fail only on the train"
              % (rnd, len(merged), len(skipped), len(tests), len(new)), flush=True)
        if not new:
            break
        for test, line in new.items():
            lo, hi, _ = sweep.bisect([c for _, c in merged], lambda c: 1 if test in failing([test], c) else 0)
            culprit = merged[hi][0]
            print("  %s: first fails after PR #%d" % (test, culprit), flush=True)
            if culprit not in {d["pr"] for d in dropped}:
                dropped.append({"pr": culprit, "test": test, "line": line, "round": rnd})
    report = {"main": main, "tip": tip, "green": not new, "merged": [pr for pr, _ in merged],
              "skipped": [{"pr": pr, "reason": why} for pr, why in skipped], "dropped": dropped,
              "fail_on_main_too": broken_on_main}
    with open(os.path.join(sweep.HERE, "train.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, indent=1)
    print("tip %s: %d merged, %d skipped, %d dropped, %s" % (tip[:9], len(merged), len(skipped), len(dropped),
          "green" if not new else "NOT green after %d rounds" % rounds))
    if not new:
        print("push the train: git -C %s push origin %s:main" % (sweep.CLONE, tip))


def self_check():
    """build() on a throwaway repository: 2 PRs merge, 1 conflicts, the tip has both changes and 2 parents."""
    with tempfile.TemporaryDirectory() as repo:
        def g(*args):
            return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@localhost", *args],
                                  capture_output=True, text=True, check=True).stdout.strip()
        g("init", "-q", "-b", "main")
        for name, text in (("a.txt", "a\n"), ("b.txt", "b\n")):
            open(os.path.join(repo, name), "w").write(text)
        g("add", "."), g("commit", "-qm", "base")
        base = g("rev-parse", "HEAD")
        for pr, name, text in ((1, "a.txt", "a1\n"), (2, "c.txt", "c\n"), (3, "a.txt", "a3\n")):
            g("checkout", "-q", "-b", "pr%d" % pr, base)
            open(os.path.join(repo, name), "w").write(text)
            g("add", "."), g("commit", "-qm", "pr%d" % pr)
        sweep.CLONE = repo
        env = {k: os.environ.get(k) for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")}
        os.environ.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@localhost", GIT_COMMITTER_NAME="t",
                          GIT_COMMITTER_EMAIL="t@localhost")
        try:
            tip, merged, skipped = build(base, [1, 2, 3], ref_of=lambda pr: "refs/heads/pr%d" % pr)
        finally:
            for k, v in env.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        assert [pr for pr, _ in merged] == [1, 2] and skipped == [(3, "conflict")], (merged, skipped)
        assert g("show", "%s:a.txt" % tip) == "a1" and g("show", "%s:c.txt" % tip) == "c"
        assert len(g("rev-list", "--parents", "-n", "1", tip).split()) == 3  # the commit and its 2 parents
    print("self-check OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        self_check()
    elif sys.argv[1:] and all(a.isdigit() for a in sys.argv[1:]) and sweep.CLONE:
        run([int(a) for a in sys.argv[1:]])
    else:
        sys.exit("usage: SWEEP_CLONE=<full clone> SWEEP_DIR=<state> train.py <pr> [<pr> ...] | --self-check")

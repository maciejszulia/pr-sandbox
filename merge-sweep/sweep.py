#!/usr/bin/env python3
"""Merge-check sweep for the open pull requests of one GitHub repository.

  sweep.py prepare   fetch main into SWEEP_CLONE, record its SHA, list the open PRs that change only .py and .md
                     files and touch tests/ (gh pr list)
  sweep.py run       for each listed PR, newest first: merge its head into the main snapshot with
                     `git merge-tree` (the 3-way merge GitHub does), stream the merged tree into a container
                     without network and run the test files the PR touches; compare each failure with the same
                     file on main (cached baseline)

Env: SWEEP_REPO (owner/name), SWEEP_CLONE (a full clone of it), SWEEP_DIR (state, default ./sweep-state),
     SANDBOX_IMAGE (default pr-sandbox:py312), WORKERS (parallel containers, default 3).
Writes in SWEEP_DIR:
  results.jsonl     one record per PR: {"pr", "applied", "head", "tests": [[rc, file, first failure line], ...]}
  candidates.jsonl  one record per suspect: the test passes on main (or is new) and fails with the PR merged
  baseline.json     main snapshot results per test file
Stop early: touch SWEEP_DIR/STOP. A rerun resumes after the PRs already in results.jsonl.
"""
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.abspath(os.environ.get("SWEEP_DIR", "sweep-state"))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.environ.get("SANDBOX_IMAGE", "pr-sandbox:py312")
REPO = os.environ.get("SWEEP_REPO", "")
WORKERS = int(os.environ.get("WORKERS", "3"))
LOCK = threading.Lock()


CLONE = os.environ.get("SWEEP_CLONE", "")
MAIN_SHA = ""  # set in run() from SWEEP_DIR/main.sha


def git(*args, **kw):
    return subprocess.run(["git", "-C", CLONE, *args], capture_output=True, **kw)


def docker(tests, tree):
    """Run the tests on `tree` (a tree or commit in CLONE), streamed into the container with git archive."""
    archive = subprocess.Popen(["git", "-C", CLONE, "archive", "--format=tar", tree], stdout=subprocess.PIPE)
    cmd = ["docker", "run", "-i", "--rm", "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--pids-limit", "512", "--memory", "2g", "--cpus", "2", "--user", "%d:%d" % (os.getuid(), os.getgid()),
           "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "TESTS=" + " ".join(tests),
           "-v", os.path.join(SCRIPT_DIR, "run_pr.sh") + ":/run_pr.sh:ro",
           "--tmpfs", "/work:exec,size=3g,mode=1777", "--tmpfs", "/tmp:exec,size=1g,mode=1777",
           IMAGE, "bash", "/run_pr.sh"]
    try:
        out = subprocess.run(cmd, stdin=archive.stdout, capture_output=True, text=True, timeout=1500).stdout
    except subprocess.TimeoutExpired:
        out = "TIMEOUT"
    archive.stdout.close()
    archive.wait()
    return out


def parse(out):
    applied, results = True, []
    for line in out.splitlines():
        if line.startswith("APPLY_FAILED"):
            applied = False
        elif line.startswith("RESULT "):
            parts = line.split(" ", 3)
            results.append([int(parts[1]), parts[2], parts[3] if len(parts) > 3 else ""])
    if out == "TIMEOUT":
        applied = None
    return applied, results


def tests_for(files):
    """Test files a PR touches: its own tests/ files plus tests/test_<tool>.py for each tool it changes."""
    paths = [f["path"] for f in files]
    tests = [p for p in paths if p.startswith("tests/") and os.path.basename(p).startswith("test_") and p.endswith(".py")]
    for p in paths:
        if p.startswith(("tools/", "scripts/")) and p.endswith(".py"):
            guess = "tests/test_%s" % os.path.basename(p)
            if guess not in tests and (on_main(guess) or guess in paths):
                tests.append(guess)
    return tests[:5]


def on_main(path):
    return git("cat-file", "-e", "%s:%s" % (MAIN_SHA, path)).returncode == 0


def prepare():
    os.makedirs(HERE, exist_ok=True)
    subprocess.run(["git", "-C", CLONE, "fetch", "-q", "origin", "main"], check=True)
    sha = git("rev-parse", "FETCH_HEAD", text=True).stdout.strip()
    listing = subprocess.run(["gh", "pr", "list", "-R", REPO, "--state", "open", "--limit", "5000",
                              "--json", "number,title,files,isDraft"], capture_output=True, text=True, check=True)
    prs = json.loads(listing.stdout)
    keep = sorted(p["number"] for p in prs if not p["isDraft"] and p["files"]
                  and all(f["path"].endswith((".py", ".md")) for f in p["files"])
                  and any(f["path"].startswith("tests/") for f in p["files"]))
    for name, value in (("main.sha", sha + "\n"), ("open-prs.json", json.dumps(prs)), ("py-prs.json", json.dumps(keep))):
        with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(value)
    print("main", sha[:9], "| open PRs:", len(prs), "| to check:", len(keep))


def run():
    global MAIN_SHA
    MAIN_SHA = open(os.path.join(HERE, "main.sha"), encoding="utf-8").read().strip()
    prs = json.load(open(os.path.join(HERE, "open-prs.json")))
    by_number = {p["number"]: p for p in prs}
    order = sorted(json.load(open(os.environ.get("PRS_FILE", os.path.join(HERE, "py-prs.json")))), reverse=True)
    done = set()
    results_path = os.path.join(HERE, "results.jsonl")
    if os.path.exists(results_path):
        for line in open(results_path, encoding="utf-8"):
            done.add(json.loads(line)["pr"])
    baseline_path = os.path.join(HERE, "baseline.json")
    baseline = json.load(open(baseline_path)) if os.path.exists(baseline_path) else {}

    def base(test):
        with LOCK:
            if test in baseline:
                return baseline[test]
        _, res = parse(docker([test], MAIN_SHA))
        value = res[0] if res else [999, test, "no result"]
        with LOCK:
            baseline[test] = value
            with open(baseline_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(baseline, fh)
        return value

    def one(number):
        if os.path.exists(os.path.join(HERE, "STOP")):
            return
        tests = tests_for(by_number[number]["files"])
        if not tests:
            return
        ref = "refs/sweep/%d" % number
        fetch = git("fetch", "-q", "--no-write-fetch-head", "origin", "+refs/pull/%d/head:%s" % (number, ref), text=True)
        merge = git("merge-tree", "--write-tree", "--no-messages", MAIN_SHA, ref, text=True) if fetch.returncode == 0 else None
        if merge is None or merge.returncode not in (0, 1):
            err = (fetch.stderr if merge is None else merge.stderr).strip()[:200]
            record = {"pr": number, "applied": None, "error": err, "tests": []}
        elif merge.returncode == 1:  # merge conflict with the main snapshot
            record = {"pr": number, "applied": False, "head": git("rev-parse", ref, text=True).stdout.strip(), "tests": []}
        else:
            tree = merge.stdout.split()[0]
            applied, res = parse(docker(tests, tree))
            record = {"pr": number, "applied": applied, "head": git("rev-parse", ref, text=True).stdout.strip(),
                      "tests": res}
            for rc, test, line in res if applied else []:
                if rc == 0:
                    continue
                exists = on_main(test)
                b = base(test) if exists else None
                if b is None or b[0] == 0:
                    cand = {"pr": number, "test": test, "rc": rc, "line": line, "new_file": not exists,
                            "main_rc": None if b is None else b[0], "title": by_number[number]["title"]}
                    with LOCK, open(os.path.join(HERE, "candidates.jsonl"), "a", encoding="utf-8", newline="\n") as fh:
                        fh.write(json.dumps(cand) + "\n")
        with LOCK, open(results_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record) + "\n")

    todo = [n for n in order if n not in done and n in by_number]
    print("todo:", len(todo), "workers:", WORKERS, flush=True)
    with ThreadPoolExecutor(WORKERS) as pool:
        for i, _ in enumerate(pool.map(one, todo), 1):
            if i % 25 == 0:
                print("processed", i, flush=True)
    print("finished", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("prepare", "run") or not REPO or not CLONE:
        sys.exit("usage: SWEEP_REPO=owner/name SWEEP_CLONE=<full clone> sweep.py prepare|run")
    sys.exit(prepare() if sys.argv[1] == "prepare" else run())

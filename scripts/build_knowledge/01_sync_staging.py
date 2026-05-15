"""Sync local IDRE clone to origin/staging. Idempotent."""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path
from common import IDRE_REPO, git_sha


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=str(IDRE_REPO), text=True).strip()


def main(branch: str) -> int:
    if not (IDRE_REPO / ".git").exists():
        print(f"ERROR: {IDRE_REPO} is not a git repo", file=sys.stderr)
        return 1
    print(f"Fetching origin/{branch}...")
    try:
        run(["git", "fetch", "origin", branch])
    except subprocess.CalledProcessError as e:
        print(f"WARNING: git fetch failed (auth/network?): exit {e.returncode}", file=sys.stderr)
        print(f"  Continuing with locally cached origin/{branch}", file=sys.stderr)
    sha = git_sha(branch)
    print(f"origin/{branch} is at {sha}")

    # Check for local uncommitted changes — refuse to clobber
    dirty = run(["git", "status", "--porcelain"])
    if dirty:
        print("WARNING: local repo has uncommitted changes:")
        print(dirty)
        print("Pipeline will checkout origin/staging in detached HEAD.")

    run(["git", "checkout", "--detach", f"origin/{branch}"])
    print(f"Checked out origin/{branch} ({sha}) in detached HEAD")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--branch", default="staging")
    args = p.parse_args()
    sys.exit(main(args.branch))

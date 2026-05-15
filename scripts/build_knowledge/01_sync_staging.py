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

    # Check for local uncommitted changes
    dirty = run(["git", "status", "--porcelain"])
    stashed = False
    if dirty:
        print("Local repo has uncommitted changes; stashing before checkout:")
        print(dirty)
        # Use -u to also stash untracked files (e.g., app/api/dev/)
        run(["git", "stash", "push", "-u", "-m", f"pipeline-autostash-{sha}"])
        stashed = True

    try:
        run(["git", "checkout", "--detach", f"origin/{branch}"])
        print(f"Checked out origin/{branch} ({sha}) in detached HEAD")
    except subprocess.CalledProcessError:
        if stashed:
            print("Checkout failed; restoring stash", file=sys.stderr)
            run(["git", "stash", "pop"])
        raise
    finally:
        if stashed:
            # Write a marker so a subsequent restore script can pop the stash later.
            # We don't auto-pop here because the pipeline still reads the working tree.
            marker = IDRE_REPO / ".pipeline_stash_marker"
            marker.write_text(f"pipeline-autostash-{sha}\n")
            print(f"Stash created; pop it manually with `git stash pop` after pipeline run", file=sys.stderr)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--branch", default="staging")
    args = p.parse_args()
    sys.exit(main(args.branch))

"""Run all pipeline steps, then atomically swap v10_pending/ -> v10/."""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from common import PENDING_DIR, LIVE_DIR


STEPS = [
    "01_sync_staging.py",
    "02_extract_reference_cards.py",
    "03_extract_schema.py",
    "04_extract_enums.py",
    "05_extract_business_logic.py",
]
HERE = Path(__file__).parent
PYTHON = "C:/Users/anand/AppData/Local/Programs/Python/Python311/python.exe"


def run_step(name: str, branch: str) -> int:
    cmd = [PYTHON, str(HERE / name)]
    if name == "01_sync_staging.py":
        cmd += ["--branch", branch]
    print(f"\n=== {name} ===")
    return subprocess.call(cmd, cwd=str(HERE))


def main(branch: str, execute_sql: bool, skip_clean: bool) -> int:
    # Clear pending unless --skip-clean for resume-after-failure
    if PENDING_DIR.exists() and not skip_clean:
        shutil.rmtree(PENDING_DIR)
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    for step in STEPS:
        code = run_step(step, branch)
        if code != 0:
            print(f"\nABORT: {step} returned {code}", file=sys.stderr)
            return code

    # Validation
    val_cmd = [PYTHON, str(HERE / "06_validate_pipeline.py")]
    if execute_sql:
        val_cmd.append("--execute-sql")
    print("\n=== 06_validate_pipeline.py ===")
    code = subprocess.call(val_cmd, cwd=str(HERE))
    if code != 0:
        print("VALIDATION FAILED — leaving v10_pending/ in place for inspection.", file=sys.stderr)
        return code

    # Atomic swap
    backup = LIVE_DIR.with_suffix(".prev")
    if backup.exists():
        shutil.rmtree(backup)
    if LIVE_DIR.exists():
        LIVE_DIR.rename(backup)
    PENDING_DIR.rename(LIVE_DIR)
    print(f"\nKnowledge live at {LIVE_DIR}")
    print(f"Previous version archived at {backup}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--branch", default="staging")
    p.add_argument("--execute-sql", action="store_true")
    p.add_argument("--skip-clean", action="store_true",
                   help="Don't wipe v10_pending/ — useful for resuming after a step crash")
    args = p.parse_args()
    sys.exit(main(args.branch, args.execute_sql, args.skip_clean))

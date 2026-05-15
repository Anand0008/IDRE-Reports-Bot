"""Shared paths + helpers for the knowledge-build pipeline."""
from __future__ import annotations
import json
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone

IDRE_REPO = Path("C:/Users/anand/Downloads/local/idre")
KNOWLEDGE_ROOT = Path("C:/Users/anand/Downloads/v10_reports_bot/knowledge")
PENDING_DIR = KNOWLEDGE_ROOT / "v10_pending"
LIVE_DIR = KNOWLEDGE_ROOT / "v10"


def ensure_pending() -> Path:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    return PENDING_DIR


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def git_sha(branch: str = "staging") -> str:
    out = subprocess.check_output(
        ["git", "rev-parse", f"origin/{branch}"],
        cwd=str(IDRE_REPO),
        text=True,
    )
    return out.strip()[:12]


def utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

"""Parse idre/prisma/schema.prisma into a schema_catalog.json.
Each table gets: name, columns (name, type, optional, attributes), relations.
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
from common import IDRE_REPO, ensure_pending, write_json, git_sha

SCHEMA_FILE = IDRE_REPO / "prisma" / "schema.prisma"

MODEL_BLOCK = re.compile(r"^model\s+(\w+)\s*\{([^}]*)\}", re.MULTILINE | re.DOTALL)
ENUM_BLOCK = re.compile(r"^enum\s+(\w+)\s*\{([^}]*)\}", re.MULTILINE | re.DOTALL)
FIELD_LINE = re.compile(
    r"^\s*(\w+)\s+(\w+)(\?)?(\s*\[\])?\s*(.*)$"
)


def parse_models(text: str) -> list[dict]:
    models = []
    for name, body in MODEL_BLOCK.findall(text):
        columns = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("@@"):
                continue
            m = FIELD_LINE.match(line)
            if not m:
                continue
            col_name, col_type, opt, is_list, attrs = m.groups()
            columns.append({
                "name": col_name,
                "type": col_type,
                "optional": opt == "?",
                "is_list": bool(is_list),
                "attributes": attrs.strip(),
            })
        # Convention: table_name matches @@map() if present, else lowercased model name
        table_map = re.search(r"@@map\(\"([^\"]+)\"\)", body)
        models.append({
            "model": name,
            "table_name": table_map.group(1) if table_map else _camel_to_snake(name),
            "columns": columns,
        })
    return models


def parse_enums(text: str) -> list[dict]:
    enums = []
    for name, body in ENUM_BLOCK.findall(text):
        values = [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("//")]
        enums.append({"name": name, "values": values})
    return enums


def _camel_to_snake(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return s


def main() -> int:
    if not SCHEMA_FILE.exists():
        print(f"ERROR: {SCHEMA_FILE} not found (did 01_sync_staging.py run?)", file=sys.stderr)
        return 1
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    models = parse_models(text)
    enums = parse_enums(text)
    out = ensure_pending() / "schema_catalog.json"
    write_json(out, {
        "idre_git_sha": git_sha(),
        "models": models,
        "enums_inline": enums,
        "model_count": len(models),
        "enum_count": len(enums),
    })
    print(f"Wrote {len(models)} models + {len(enums)} enums -> {out}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.parse_args()
    sys.exit(main())

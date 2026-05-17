"""Apply covering indexes to local docker `idre` DB. Idempotent.

Run: py311 .snapshots/apply_indexes.py
"""
from pathlib import Path

import pymysql
import pymysql.err

HERE = Path(__file__).parent
SQL_FILE = HERE / "add_indexes.sql"


def main():
    sql = SQL_FILE.read_text(encoding="utf-8")
    conn = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="idrelocal",
        database="idre",
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as c:
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if not stmt or stmt.startswith("--"):
                    continue
                # Strip leading comment lines from multi-line statements
                lines = [
                    line for line in stmt.splitlines()
                    if not line.strip().startswith("--")
                ]
                cleaned = "\n".join(lines).strip()
                if not cleaned:
                    continue
                try:
                    c.execute(cleaned)
                    print(f"[OK]   {cleaned.splitlines()[0]}")
                except pymysql.err.OperationalError as e:
                    if e.args[0] == 1061:  # Duplicate key name
                        print(f"[SKIP] {cleaned.splitlines()[0]} (already exists)")
                        continue
                    raise
        print()
        # Verify
        with conn.cursor() as c:
            c.execute(
                """SELECT table_name, index_name FROM information_schema.STATISTICS
                   WHERE table_schema='idre' AND index_name LIKE '%_v10'
                   GROUP BY table_name, index_name ORDER BY table_name, index_name"""
            )
            print("v10 indexes in `idre`:")
            for row in c.fetchall():
                print(f"  {row[0]}.{row[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

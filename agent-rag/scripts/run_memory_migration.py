from __future__ import annotations

import os
from pathlib import Path

import api.env  # noqa: F401 — load .env
import pymysql
from db.config import get_mysql_password


def main() -> None:
    host = os.environ.get("MYSQL_HOST", "localhost")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ.get("MYSQL_USER", "root")
    password = get_mysql_password()
    database = os.environ.get("MYSQL_DATABASE", "appdb")

    sql_path = Path(__file__).resolve().parents[1] / "db" / "migrations" / "001_memory_upgrade.sql"
    raw = sql_path.read_text(encoding="utf-8")
    statements: list[str] = []
    buf: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt.endswith(";"):
                stmt = stmt[:-1].strip()
            if stmt:
                statements.append(stmt)
            buf = []
    if buf:
        tail = "\n".join(buf).strip()
        if tail:
            statements.append(tail.rstrip(";").strip())

    print(f"Connecting to {host}:{port}/{database} as {user}")
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            for stmt in statements:
                head = stmt.split("\n", 1)[0][:80]
                try:
                    cur.execute(stmt)
                    print(f"OK: {head}")
                except pymysql.err.OperationalError as exc:
                    code = exc.args[0]
                    if code in (1060, 1050):
                        print(f"SKIP (already applied): {head}")
                    else:
                        raise
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM conversations LIKE 'summary'")
            print("verify summary column:", cur.fetchone())
            cur.execute("SHOW TABLES LIKE 'tenant_profiles'")
            print("verify tenant_profiles:", cur.fetchone())
    finally:
        conn.close()

    print("Migration finished.")


if __name__ == "__main__":
    main()

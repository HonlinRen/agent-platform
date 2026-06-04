"""Quick MySQL connectivity check for agent-rag conversation persistence."""

from __future__ import annotations

import logging
import os
import sys

import api.env  # noqa: F401 — load .env
from db.config import get_database_url, get_mysql_password
from db.session import ping_db
from rag.logging_config import configure_logging
from sqlalchemy import create_engine, inspect, text

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    host = os.environ.get("MYSQL_HOST", "localhost")
    port = os.environ.get("MYSQL_PORT", "3306")
    user = os.environ.get("MYSQL_USER", "root")
    database = os.environ.get("MYSQL_DATABASE", "appdb")

    logger.info("MySQL connection test")
    logger.info("  host=%s port=%s user=%s database=%s", host, port, user, database)
    logger.info("  password_set=%s", bool(get_mysql_password()))

    if not get_mysql_password():
        logger.error("FAIL: MySql_Password is not set (check agent-rag/.env)")
        return 1

    if not ping_db():
        logger.error("FAIL: cannot connect to MySQL")
        return 1

    engine = create_engine(get_database_url(), pool_pre_ping=True)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar_one()
        logger.info("  server_version=%s", version)

        tables = inspect(engine).get_table_names()
        expected = {"conversations", "chat_messages", "chat_feedback"}
        missing = expected - set(tables)
        logger.info("  tables=%s", sorted(tables) or "(none)")
        if missing:
            logger.warning(
                "  missing tables %s — run: mysql -u root -p appdb < db/schema.sql",
                sorted(missing),
            )

    logger.info("OK: MySQL connection successful")
    return 0


if __name__ == "__main__":
    sys.exit(main())

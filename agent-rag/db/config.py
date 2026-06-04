from __future__ import annotations

import os
from urllib.parse import quote_plus


def get_mysql_password() -> str:
    return os.environ.get("MySql_Password") or os.environ.get("MYSQL_PASSWORD") or ""


def get_database_url() -> str:
    host = os.environ.get("MYSQL_HOST", "localhost")
    port = os.environ.get("MYSQL_PORT", "3306")
    user = os.environ.get("MYSQL_USER", "root")
    password = get_mysql_password()
    database = os.environ.get("MYSQL_DATABASE", "appdb")
    encoded_password = quote_plus(password)
    return f"mysql+pymysql://{user}:{encoded_password}@{host}:{port}/{database}?charset=utf8mb4"

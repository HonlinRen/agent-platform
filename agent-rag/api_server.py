from __future__ import annotations

import api.env  # noqa: F401 — load .env before app imports

import os

os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import uvicorn

from rag.logging_config import configure_logging
from api.main import API_HOST, API_PORT, app


def main() -> None:
    configure_logging()
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=os.environ.get("API_RELOAD", "false").lower() in {"1", "true", "yes"},
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import api.env  # noqa: F401 — load .env before app imports

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

# #region agent log
def _debug_startup_log(message: str, data: dict, hypothesis_id: str) -> None:
    payload = {
        "sessionId": "45f6cc",
        "timestamp": int(time.time() * 1000),
        "location": "api_server.py:startup",
        "message": message,
        "data": data,
        "hypothesisId": hypothesis_id,
    }
    with open("debug-45f6cc.log", "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")


_project_root = Path(__file__).resolve().parent
_venv_python = _project_root / ".venv" / "Scripts" / "python.exe"
_debug_startup_log(
    "python environment probe",
    {
        "executable": sys.executable,
        "version": sys.version,
        "prefix": sys.prefix,
        "base_prefix": getattr(sys, "base_prefix", ""),
        "in_venv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
        "chromadb_spec": str(importlib.util.find_spec("chromadb")),
        "venv_python_exists": _venv_python.exists(),
        "venv_python": str(_venv_python),
        "cwd": os.getcwd(),
    },
    "H1",
)
# #endregion


def _ensure_project_python() -> None:
    if importlib.util.find_spec("chromadb") is not None:
        return

    if _venv_python.exists() and Path(sys.executable).resolve() != _venv_python.resolve():
        raise SystemExit(
            "Missing dependency 'chromadb' in the active Python interpreter.\n"
            f"Current: {sys.executable}\n"
            "This project installs dependencies in .venv.\n"
            f"Run: {_venv_python} api_server.py\n"
            "Or activate the venv first: .venv\\Scripts\\Activate.ps1"
        )

    raise SystemExit(
        "Missing dependency 'chromadb'. Install project dependencies first:\n"
        "  python -m venv .venv\n"
        "  .venv\\Scripts\\pip install -r requirements.txt"
    )


_ensure_project_python()

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

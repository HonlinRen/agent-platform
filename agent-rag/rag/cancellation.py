from __future__ import annotations

import threading

_lock = threading.Lock()
_active: dict[tuple[str, str], bool] = {}
_cancelled: set[tuple[str, str]] = set()


def _key(tenant_id: str, thread_id: str) -> tuple[str, str]:
    return tenant_id, thread_id


def begin_run(tenant_id: str, thread_id: str) -> None:
    key = _key(tenant_id, thread_id)
    with _lock:
        _active[key] = True
        _cancelled.discard(key)


def request_cancel(tenant_id: str, thread_id: str) -> bool:
    key = _key(tenant_id, thread_id)
    with _lock:
        if key not in _active:
            return False
        _cancelled.add(key)
        return True


def is_cancelled(tenant_id: str, thread_id: str) -> bool:
    key = _key(tenant_id, thread_id)
    with _lock:
        return key in _cancelled


def end_run(tenant_id: str, thread_id: str) -> None:
    key = _key(tenant_id, thread_id)
    with _lock:
        _active.pop(key, None)
        _cancelled.discard(key)

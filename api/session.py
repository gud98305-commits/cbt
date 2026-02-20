"""
api/session.py — 멀티유저 인메모리 세션 (쿠키 기반)

각 사용자에게 UUID 세션 ID를 발급하고, 세션별로 독립된 상태를 유지.
TTL(기본 1시간) 경과 시 자동 만료.
"""

import threading
import time
import uuid
from typing import Any

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}
_timestamps: dict[str, float] = {}

SESSION_TTL = 3600  # 1시간


def _new_state() -> dict[str, Any]:
    return {
        "api_key": "",
        "parsed_questions": [],
        "parsed_answers": [],
        "questions": [],
        "exam_state": None,
        "final_score": 0.0,
        "incorrect_questions": [],
    }


def create_session() -> str:
    """새 세션을 생성하고 세션 ID를 반환."""
    sid = uuid.uuid4().hex
    with _lock:
        _sessions[sid] = _new_state()
        _timestamps[sid] = time.time()
    return sid


def get_session(sid: str) -> dict[str, Any] | None:
    """세션 ID로 세션 데이터를 가져옴. 만료되었거나 없으면 None."""
    with _lock:
        if sid not in _sessions:
            return None
        if time.time() - _timestamps[sid] > SESSION_TTL:
            del _sessions[sid]
            del _timestamps[sid]
            return None
        _timestamps[sid] = time.time()  # 접근 시 갱신
        return _sessions[sid]


def get(sid: str, key: str, default=None):
    """세션에서 값 읽기."""
    session = get_session(sid)
    if session is None:
        return default
    return session.get(key, default)


def put(sid: str, key: str, value) -> None:
    """세션에 값 쓰기."""
    with _lock:
        if sid in _sessions:
            _sessions[sid][key] = value
            _timestamps[sid] = time.time()


def reset(sid: str) -> None:
    """세션 초기화 (API 키는 유지)."""
    with _lock:
        if sid in _sessions:
            saved_key = _sessions[sid].get("api_key", "")
            _sessions[sid] = _new_state()
            _sessions[sid]["api_key"] = saved_key
            _timestamps[sid] = time.time()


def cleanup_expired() -> int:
    """만료된 세션을 정리. 제거된 수 반환."""
    now = time.time()
    removed = 0
    with _lock:
        expired = [sid for sid, ts in _timestamps.items() if now - ts > SESSION_TTL]
        for sid in expired:
            del _sessions[sid]
            del _timestamps[sid]
            removed += 1
    return removed

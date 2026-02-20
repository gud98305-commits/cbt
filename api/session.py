"""
api/session.py — 인메모리 세션 상태 (단일 사용자 로컬 앱)

asyncio.to_thread로 인한 동시성 보호를 위해 threading.Lock 사용.
"""

import threading
from typing import Any

_lock = threading.Lock()
_state: dict[str, Any] = {
    "api_key": "",
    "parsed_questions": [],   # List[Question]
    "parsed_answers": [],     # List[dict]
    "questions": [],          # List[Question] (exam용)
    "exam_state": None,       # ExamState | None
    "final_score": 0.0,
    "incorrect_questions": [],
}


def get(key: str, default=None):
    with _lock:
        return _state.get(key, default)


def put(key: str, value) -> None:
    with _lock:
        _state[key] = value


def reset() -> None:
    with _lock:
        saved_key = _state.get("api_key", "")
        _state.clear()
        _state.update({
            "api_key": saved_key,
            "parsed_questions": [],
            "parsed_answers": [],
            "questions": [],
            "exam_state": None,
            "final_score": 0.0,
            "incorrect_questions": [],
        })

"""
api/session.py — 인메모리 세션 상태 (단일 사용자 로컬 앱)
"""

from typing import List, Optional, Any

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
    return _state.get(key, default)


def put(key: str, value) -> None:
    _state[key] = value


def reset() -> None:
    global _state
    _state = {
        "api_key": _state.get("api_key", ""),
        "parsed_questions": [],
        "parsed_answers": [],
        "questions": [],
        "exam_state": None,
        "final_score": 0.0,
        "incorrect_questions": [],
    }

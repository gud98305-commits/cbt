"""
models/session_state.py

시험 진행 상태를 담는 OMR 카드 모델.
Pydantic BaseModel 기반 — 직렬화/역직렬화 및 타입 안전성 확보.
UI 코드 없음.
"""

import time
from typing import Dict

from pydantic import BaseModel, Field


class ExamState(BaseModel):
    """
    사용자의 시험 세션 전체 상태를 표현하는 모델.

    Attributes:
        current_quest_index: 현재 풀고 있는 문제의 인덱스 (0-based).
        user_answers:        사용자 답안지. {question.id: 선택한 보기 문자열}
        is_submitted:        최종 제출 여부. True이면 채점 가능 상태.
        start_time:          시험 시작 시각 (time.time() 기준 Unix timestamp).
                             기본값은 모델 생성 시점의 현재 시각.
    """

    current_quest_index: int = Field(
        default=0,
        ge=0,
        description="현재 풀고 있는 문제 인덱스 (0-based)"
    )
    user_answers: Dict[int, str] = Field(
        default_factory=dict,
        description="사용자 답안지. key: question.id, value: 선택한 보기 문자열"
    )
    is_submitted: bool = Field(
        default=False,
        description="최종 제출 완료 여부"
    )
    start_time: float = Field(
        default_factory=time.time,
        description="시험 시작 시각 (Unix timestamp, time.time() 기준)"
    )

    model_config = {"arbitrary_types_allowed": True}

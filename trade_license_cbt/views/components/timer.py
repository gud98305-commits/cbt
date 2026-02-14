"""
views/components/timer.py

남은 시험 시간을 계산하여 렌더링하는 컴포넌트.
시험 제한 시간: 기본 90분 (5400초).
타이머는 사용자 상호작용 시(버튼 클릭 등) 갱신된다.
"""

import time

import streamlit as st

_EXAM_DURATION_SECONDS = 5400  # 90분


def render(start_time: float, duration: int = _EXAM_DURATION_SECONDS) -> bool:
    """
    남은 시간 표시.

    Args:
        start_time: ExamState.start_time (Unix timestamp)
        duration:   시험 제한 시간 (초, 기본 90분)

    Returns:
        True  — 시간이 남아 있음
        False — 시간 초과
    """
    elapsed = time.time() - start_time
    remaining = max(0.0, duration - elapsed)

    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    time_str = f"{minutes:02d}:{seconds:02d}"

    is_warning = remaining < 600  # 10분 미만이면 빨간색 경고

    css_class = "timer-display timer-warning" if is_warning else "timer-display"
    icon = "⚠️ " if is_warning else "⏱ "

    st.markdown(
        f'<div class="{css_class}">{icon}{time_str}</div>',
        unsafe_allow_html=True,
    )

    if remaining == 0:
        st.warning("⏰ 시험 시간이 종료되었습니다.")
        return False
    return True

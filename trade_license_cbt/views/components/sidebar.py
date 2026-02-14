"""
views/components/sidebar.py

문제 번호 네비게이션 그리드 컴포넌트.
각 번호를 클릭하면 해당 문제로 바로 이동한다.
"""

from __future__ import annotations

import streamlit as st

from models.question_model import Question
from models.session_state import ExamState


def render(questions: list[Question], exam_state: ExamState) -> None:
    """
    사이드바에 문제 번호 버튼 그리드와 진행 현황을 렌더링한다.

    색상 코딩:
      - 현재 문제: 짙은 남색 배경
      - 답한 문제: 파란색 배경
      - 미답 문제: 흰색 배경 + 테두리
    """
    total = len(questions)
    answered = len(exam_state.user_answers)
    current_idx = exam_state.current_quest_index

    # ── 진행 현황 ──────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between;
                        font-size:0.8rem; color:#6b7280; margin-bottom:4px;">
                <span>진행률</span>
                <span><b>{answered}</b> / {total}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(answered / total if total > 0 else 0)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── 문제 번호 그리드 (5열) ─────────────────────────────────────────────
    st.markdown(
        "<p style='font-size:0.78rem; color:#9ca3af; font-weight:600; "
        "letter-spacing:0.05em; margin-bottom:8px;'>문제 번호</p>",
        unsafe_allow_html=True,
    )

    cols_per_row = 5

    for row_start in range(0, total, cols_per_row):
        row_qs = questions[row_start : row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col_idx, q in enumerate(row_qs):
            q_idx = row_start + col_idx
            is_current = q_idx == current_idx
            is_answered = q.id in exam_state.user_answers

            with cols[col_idx]:
                if st.button(
                    str(q.id),
                    key=f"nav_{q_idx}",
                    help=f"문제 {q.id}번으로 이동",
                ):
                    exam_state.current_quest_index = q_idx
                    st.rerun()

    # ── 범례 ──────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="margin-top:16px; font-size:0.75rem; color:#9ca3af; line-height:1.9;">
            <span style="display:inline-block; width:10px; height:10px;
                         background:#1a1a2e; border-radius:2px; margin-right:5px;"></span>현재<br>
            <span style="display:inline-block; width:10px; height:10px;
                         background:#4a7fcb; border-radius:2px; margin-right:5px;"></span>답함<br>
            <span style="display:inline-block; width:10px; height:10px;
                         background:white; border:1.5px solid #d1d9e6;
                         border-radius:2px; margin-right:5px;"></span>미답
        </div>
        """,
        unsafe_allow_html=True,
    )

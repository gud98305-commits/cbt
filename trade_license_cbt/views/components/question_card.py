"""
views/components/question_card.py

단일 문제(Question)를 카드 형태로 렌더링하고
사용자의 선택을 반환하는 컴포넌트.
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from models.question_model import Question


def render(
    question: Question,
    question_number: int,
    total: int,
    saved_answer: Optional[str] = None,
) -> Optional[str]:
    """
    문제 카드를 렌더링하고 사용자가 선택한 보기를 반환한다.

    Args:
        question:        렌더링할 Question 객체
        question_number: 전체 문제 중 몇 번째 문제인지 (1-based 표시용)
        total:           전체 문제 수
        saved_answer:    이미 저장된 이전 선택 (없으면 None)

    Returns:
        선택된 보기 문자열, 아무것도 선택하지 않은 경우 None
    """

    # ── 문제 헤더 ──────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
            <span class="question-number-badge">문제 {question_number} / {total}</span>
            <span style="font-size:0.8rem; color:#9ca3af;">{question.subject}</span>
            <span style="font-size:0.75rem; color:#c0ccd8; margin-left:auto;">
                p.{question.page_number}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 지문(context) 박스 ─────────────────────────────────────────────────
    if question.context:
        st.markdown(
            f'<div class="context-box"><b>[지문]</b><br>{question.context}</div>',
            unsafe_allow_html=True,
        )

    # ── 문제 본문 ──────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="question-card">
            <p style="font-size:1.05rem; font-weight:600; color:#1a1a2e;
                      line-height:1.7; margin:0;">
                {question.question_text}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 보기 선택 (Radio) ─────────────────────────────────────────────────
    radio_key = f"radio_{question.id}"

    # 위젯 키가 없을 때만 saved_answer로 초기화 (재렌더 시 기존 값 유지)
    if radio_key not in st.session_state and saved_answer in question.options:
        st.session_state[radio_key] = saved_answer

    # index 계산: 이미 세션에 값이 있으면 그 값을 우선
    current_val = st.session_state.get(radio_key, saved_answer)
    if current_val in question.options:
        default_index = question.options.index(current_val)
    else:
        default_index = None  # Streamlit: None → 아무것도 선택 안 됨

    selected = st.radio(
        "보기를 선택하세요",
        options=question.options,
        index=default_index,
        key=radio_key,
        label_visibility="collapsed",
    )

    return selected

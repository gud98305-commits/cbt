"""
views/exam_view.py — 시험 풀기 화면

레이아웃:
  - st.sidebar : 문제 번호 네비게이터 + 타이머
  - 메인 영역  : 현재 문제 카드 + 이전/다음 + 최종 제출

상태 관리:
  - st.session_state.exam_state   (ExamState)
  - st.session_state.questions    (List[Question])
  - 답안은 radio 위젯 ↔ exam_state.user_answers 양방향 동기화
"""

from __future__ import annotations

import streamlit as st

from trade_license_cbt.models.session_state import ExamState
from trade_license_cbt.services.exam_service import calculate_score, get_incorrect_questions
from trade_license_cbt.views.components import question_card as qcard
from trade_license_cbt.views.components import sidebar as nav
from trade_license_cbt.views.components import timer as tmr


def _go_to_result() -> None:
    """채점 후 결과 페이지로 이동."""
    exam_state: ExamState = st.session_state.exam_state
    questions = st.session_state.questions

    exam_state.is_submitted = True
    score = calculate_score(questions, exam_state.user_answers)
    incorrect = get_incorrect_questions(questions, exam_state.user_answers)

    st.session_state.final_score = score
    st.session_state.incorrect_questions = incorrect
    st.session_state.page = "result"
    st.rerun()


def _save_current_answer(exam_state: ExamState, question_id: int) -> None:
    """현재 라디오 위젯 값을 exam_state.user_answers에 동기화."""
    radio_key = f"radio_{question_id}"
    if radio_key in st.session_state and st.session_state[radio_key]:
        exam_state.user_answers[question_id] = st.session_state[radio_key]


def render() -> None:
    """시험 화면 렌더링."""

    # ── 세션 가드 ──────────────────────────────────────────────────────────
    if not st.session_state.get("exam_state") or not st.session_state.get("questions"):
        st.warning("시험 정보가 없습니다. 홈 화면으로 돌아가세요.")
        if st.button("홈으로", type="primary"):
            st.session_state.page = "home"
            st.rerun()
        return

    exam_state: ExamState = st.session_state.exam_state
    questions = st.session_state.questions
    total = len(questions)

    # 인덱스 범위 보정
    exam_state.current_quest_index = max(
        0, min(exam_state.current_quest_index, total - 1)
    )
    current_idx = exam_state.current_quest_index
    current_q = questions[current_idx]

    # ── 사이드바 ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            "<h3 style='font-size:1rem; font-weight:700; "
            "color:#1a1a2e; margin-bottom:16px;'>📋 문제 목록</h3>",
            unsafe_allow_html=True,
        )

        # 타이머
        tmr.render(exam_state.start_time)

        st.markdown('<hr class="cbt-divider">', unsafe_allow_html=True)

        # 문제 번호 네비게이터
        nav.render(questions, exam_state)

        st.markdown('<hr class="cbt-divider">', unsafe_allow_html=True)

        # 제출 버튼 (사이드바 하단)
        answered_count = len(exam_state.user_answers)
        unanswered = total - answered_count

        if unanswered > 0:
            st.markdown(
                f"<p style='font-size:0.8rem; color:#f59e0b; margin-bottom:8px;'>"
                f"⚠️ 미응답 문제: {unanswered}개</p>",
                unsafe_allow_html=True,
            )

        if st.button("최종 제출", key="submit_sidebar", type="primary"):
            _save_current_answer(exam_state, current_q.id)
            if unanswered > 0:
                st.session_state["confirm_submit"] = True
                st.rerun()
            else:
                _go_to_result()

        # 미응답 상태에서 제출 확인 다이얼로그
        if st.session_state.get("confirm_submit"):
            st.warning(f"미응답 문제 {unanswered}개가 있습니다. 그래도 제출하시겠습니까?")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("제출", key="confirm_yes", type="primary"):
                    st.session_state["confirm_submit"] = False
                    _go_to_result()
            with col_no:
                if st.button("취소", key="confirm_no"):
                    st.session_state["confirm_submit"] = False
                    st.rerun()

    # ── 메인 영역 헤더 ─────────────────────────────────────────────────────
    header_col, spacer = st.columns([3, 1])
    with header_col:
        st.markdown(
            "<h2 style='font-size:1.3rem; font-weight:700; color:#1a1a2e; "
            "margin-bottom:4px;'>국제무역사 1급 CBT</h2>",
            unsafe_allow_html=True,
        )
    with spacer:
        # 헤더 우측 제출 버튼 (빠른 접근)
        if st.button("제출 →", key="submit_header", type="primary"):
            _save_current_answer(exam_state, current_q.id)
            _go_to_result()

    st.markdown('<hr class="cbt-divider">', unsafe_allow_html=True)

    # ── 문제 카드 ─────────────────────────────────────────────────────────
    saved = exam_state.user_answers.get(current_q.id)
    selected = qcard.render(
        question=current_q,
        question_number=current_idx + 1,
        total=total,
        saved_answer=saved,
    )

    # 선택한 답을 즉시 exam_state에 저장
    if selected:
        exam_state.user_answers[current_q.id] = selected

    # ── 이전 / 다음 네비게이션 ────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    nav_left, nav_center, nav_right = st.columns([1, 2, 1])

    with nav_left:
        if current_idx > 0:
            if st.button("← 이전 문제", key="prev_btn", use_container_width=True):
                _save_current_answer(exam_state, current_q.id)
                exam_state.current_quest_index -= 1
                st.rerun()

    with nav_center:
        # 현재 위치 표시
        st.markdown(
            f"<p style='text-align:center; font-size:0.85rem; color:#9ca3af; "
            f"padding-top:8px;'>{current_idx + 1} / {total}</p>",
            unsafe_allow_html=True,
        )

    with nav_right:
        if current_idx < total - 1:
            if st.button("다음 문제 →", key="next_btn",
                         type="primary", use_container_width=True):
                _save_current_answer(exam_state, current_q.id)
                exam_state.current_quest_index += 1
                st.rerun()
        else:
            # 마지막 문제에서 제출 버튼
            if st.button("제출하기 →", key="submit_last",
                         type="primary", use_container_width=True):
                _save_current_answer(exam_state, current_q.id)
                _go_to_result()

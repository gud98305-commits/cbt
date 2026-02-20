"""
views/result_view.py — 시험 결과 화면

표시 내용:
  - 최종 점수 (100점 만점 환산, 대형 숫자)
  - 합격 / 불합격 배지
  - 통계 요약 (정답 수, 오답 수, 미응답 수)
  - 과목별 점수 분석
  - 오답 노트 (오답 문제 목록 + 정답 + 해설)
  - 다시 시험 보기 / 홈으로 버튼
"""

from __future__ import annotations

import streamlit as st

from trade_license_cbt.models.question_model import Question
from trade_license_cbt.models.session_state import ExamState
from trade_license_cbt.services.exam_service import is_passed, calculate_subject_scores


def _restart_exam() -> None:
    """현재 문제 세트로 시험을 다시 시작."""
    questions = st.session_state.questions
    st.session_state.exam_state = ExamState()
    st.session_state.final_score = 0.0
    st.session_state.incorrect_questions = []
    # 이전 라디오 위젯 상태 초기화
    for q in questions:
        radio_key = f"radio_{q.id}"
        if radio_key in st.session_state:
            del st.session_state[radio_key]
    st.session_state.page = "exam"
    st.rerun()


def _go_home() -> None:
    """홈 화면으로 이동하며 세션 초기화."""
    for key in ["questions", "exam_state", "final_score", "incorrect_questions", "confirm_submit"]:
        if key in st.session_state:
            del st.session_state[key]
    # 라디오 키도 정리
    radio_keys = [k for k in st.session_state if k.startswith("radio_")]
    for k in radio_keys:
        del st.session_state[k]
    st.session_state.page = "home"
    st.rerun()


def render() -> None:
    """결과 화면 렌더링."""

    # ── 세션 가드 ──────────────────────────────────────────────────────────
    score: float = st.session_state.get("final_score", 0.0)
    questions: list[Question] = st.session_state.get("questions", [])
    incorrect: list[Question] = st.session_state.get("incorrect_questions", [])
    exam_state: ExamState | None = st.session_state.get("exam_state")

    if not questions or exam_state is None:
        st.warning("결과 정보가 없습니다.")
        if st.button("홈으로", type="primary"):
            _go_home()
        return

    passed = is_passed(score)
    total = len(questions)
    answered = len(exam_state.user_answers)
    correct_count = total - len(incorrect)
    unanswered_count = total - answered

    # ── 중앙 3열 레이아웃 ──────────────────────────────────────────────────
    _, col, _ = st.columns([0.8, 2.5, 0.8])

    with col:
        # ── 결과 카드 ─────────────────────────────────────────────────────
        st.markdown('<div class="cbt-card">', unsafe_allow_html=True)

        # 점수 대형 숫자
        score_color = "#10b981" if passed else "#ef4444"
        st.markdown(
            f'<p class="score-big" style="color:{score_color};">{score:.1f}</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center; font-size:0.9rem; color:#9ca3af; "
            "margin-top:-8px; margin-bottom:16px;'>/ 100점</p>",
            unsafe_allow_html=True,
        )

        # 합격/불합격 배지
        badge_class = "pass" if passed else "fail"
        badge_text = "합격" if passed else "불합격"
        st.markdown(
            f"<div style='text-align:center; margin-bottom:24px;'>"
            f"<span class='pass-badge {badge_class}'>{badge_text}</span></div>",
            unsafe_allow_html=True,
        )

        # ── 통계 3분할 ────────────────────────────────────────────────────
        s1, s2, s3 = st.columns(3)
        _stat_card(s1, "정답", str(correct_count), "#10b981")
        _stat_card(s2, "오답", str(len(incorrect)), "#ef4444")
        _stat_card(s3, "미응답", str(unanswered_count), "#f59e0b")

        st.markdown('<hr class="cbt-divider">', unsafe_allow_html=True)

        # ── 버튼 행 ──────────────────────────────────────────────────────
        btn_left, btn_right = st.columns(2)
        with btn_left:
            st.button(
                "다시 풀기",
                key="retry_btn",
                use_container_width=True,
                on_click=_restart_exam,
            )
        with btn_right:
            st.button(
                "홈으로",
                key="home_btn",
                type="primary",
                use_container_width=True,
                on_click=_go_home,
            )

        st.markdown("</div>", unsafe_allow_html=True)  # cbt-card 닫기

    # ── 과목별 점수 + 오답 노트 (탭) ─────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)

    subject_scores = calculate_subject_scores(questions, exam_state.user_answers)
    has_multiple_subjects = len(subject_scores) > 1

    if has_multiple_subjects:
        tab_labels = ["과목별 점수", f"오답 노트 ({len(incorrect)})"]
    else:
        tab_labels = [f"오답 노트 ({len(incorrect)})"]

    tabs = st.tabs(tab_labels)

    tab_idx = 0

    # ── 과목별 점수 탭 ───────────────────────────────────────────────────
    if has_multiple_subjects:
        with tabs[tab_idx]:
            _render_subject_scores(subject_scores)
        tab_idx += 1

    # ── 오답 노트 탭 ────────────────────────────────────────────────────
    with tabs[tab_idx]:
        _render_wrong_answers(incorrect, exam_state, has_multiple_subjects)


def _render_subject_scores(subject_scores: list[dict]) -> None:
    """과목별 점수 분석 섹션."""
    st.markdown(
        "<h3 style='font-size:1.1rem; font-weight:700; color:#1a1a2e; "
        "margin-bottom:16px;'>과목별 성적 분석</h3>",
        unsafe_allow_html=True,
    )

    for ss in subject_scores:
        subj = ss["subject"]
        subj_score = ss["score"]
        correct = ss["correct"]
        total = ss["total"]
        incorrect = ss["incorrect"]
        unanswered = ss["unanswered"]
        passed = subj_score >= 60.0

        bar_color = "#10b981" if passed else "#ef4444"
        bar_width = max(subj_score, 2)  # 최소 너비
        badge = "합격" if passed else "과락"
        badge_bg = "#d1fae5" if passed else "#fee2e2"
        badge_color = "#065f46" if passed else "#991b1b"

        st.markdown(
            f"""
            <div style="background:#ffffff; border-radius:12px; padding:16px 20px;
                        margin-bottom:12px; border:1px solid #e5eaf2;">
                <div style="display:flex; justify-content:space-between; align-items:center;
                            margin-bottom:8px;">
                    <span style="font-size:0.95rem; font-weight:600; color:#1a1a2e;">
                        {subj}
                    </span>
                    <span style="font-size:0.75rem; padding:2px 10px; border-radius:12px;
                                 background:{badge_bg}; color:{badge_color}; font-weight:600;">
                        {badge}
                    </span>
                </div>
                <div style="background:#e5eaf2; border-radius:6px; height:12px;
                            overflow:hidden; margin-bottom:8px;">
                    <div style="background:{bar_color}; width:{bar_width}%; height:100%;
                                border-radius:6px; transition:width 0.5s;"></div>
                </div>
                <div style="display:flex; justify-content:space-between;
                            font-size:0.78rem; color:#6b7280;">
                    <span>{subj_score:.1f}점</span>
                    <span>정답 {correct} / 오답 {incorrect} / 미응답 {unanswered} (총 {total})</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_wrong_answers(
    incorrect: list[Question],
    exam_state: ExamState,
    has_multiple_subjects: bool,
) -> None:
    """오답 노트 섹션."""
    if not incorrect:
        st.success("모든 문제를 맞혔습니다!")
        return

    # 과목별 필터 (과목이 2개 이상일 때)
    if has_multiple_subjects:
        subjects = sorted(set(q.subject for q in incorrect if q.subject))
        if len(subjects) > 1:
            selected = st.multiselect(
                "과목 필터",
                options=["전체"] + subjects,
                default=["전체"],
                key="wrong_subject_filter",
            )
            if "전체" not in selected and selected:
                incorrect = [q for q in incorrect if q.subject in selected]

    st.markdown(
        f"<p style='font-size:0.85rem; color:#6b7280; margin-bottom:16px;'>"
        f"총 {len(incorrect)}개 오답</p>",
        unsafe_allow_html=True,
    )

    for q in incorrect:
        user_ans = exam_state.user_answers.get(q.id, "미응답")
        with st.expander(
            f"문제 {q.id} | {q.subject} | "
            f"내 답: {user_ans}  →  정답: {q.answer}",
            expanded=False,
        ):
            # 지문
            if q.context:
                st.markdown(
                    f'<div class="context-box"><b>[지문]</b><br>{q.context}</div>',
                    unsafe_allow_html=True,
                )

            # 문제 본문
            st.markdown(
                f'<div class="question-card">'
                f'<p style="font-size:1rem; font-weight:600; color:#1a1a2e; '
                f'line-height:1.7; margin:0;">{q.question_text}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # 보기 목록 (정답 강조)
            for opt in q.options:
                is_correct = opt == q.answer
                is_user = opt == user_ans
                if is_correct:
                    prefix = "O "
                    style = "color:#065f46; font-weight:600; background:#d1fae5; " \
                            "border-radius:6px; padding:4px 10px;"
                elif is_user:
                    prefix = "X "
                    style = "color:#991b1b; background:#fee2e2; " \
                            "border-radius:6px; padding:4px 10px;"
                else:
                    prefix = "    "
                    style = "color:#374151; padding:4px 10px;"
                st.markdown(
                    f"<p style='margin:4px 0; font-size:0.93rem; {style}'>"
                    f"{prefix}{opt}</p>",
                    unsafe_allow_html=True,
                )

            # 해설
            if q.explanation:
                st.markdown(
                    f"<div style='margin-top:12px; padding:12px 16px; "
                    f"background:#f0f4fb; border-radius:8px; "
                    f"font-size:0.88rem; color:#374151; line-height:1.6;'>"
                    f"<b>해설</b>: {q.explanation}</div>",
                    unsafe_allow_html=True,
                )


def _stat_card(col, label: str, value: str, color: str) -> None:
    """통계 수치를 카드 형태로 렌더링하는 헬퍼."""
    with col:
        st.markdown(
            f"""
            <div style="text-align:center; background:#f7fafd; border-radius:12px;
                        padding:16px 8px; border-top:3px solid {color};">
                <p style="font-size:1.8rem; font-weight:800; color:{color};
                           margin:0 0 4px 0;">{value}</p>
                <p style="font-size:0.78rem; color:#9ca3af; margin:0;">{label}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

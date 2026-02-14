"""
views/home_view.py — 홈 / 시작 화면

기능:
  - 문제 PDF + 답지 PDF 분리 업로드 (2열 레이아웃)
  - 파싱 완료 후 "시험 시작" 버튼 표시
  - 샘플 시험 시작 버튼
"""

from __future__ import annotations

import os

import streamlit as st

from models.question_model import Question
from models.session_state import ExamState
from services.pdf_parser import parse_pdf, parse_answer_pdf, merge_answers, reset_client

# ── 샘플 문제 ────────────────────────────────────────────────────────────────
_SAMPLE_QUESTIONS: list[Question] = [
    Question(
        id=1, subject="무역규범",
        question_text="무역계약에서 청약(Offer)의 효력이 소멸되는 경우가 아닌 것은?",
        options=["① 청약의 철회", "② 청약의 거절", "③ 반대청약", "④ 청약의 공시"],
        answer="④ 청약의 공시",
        explanation="청약 효력 소멸 사유는 철회, 거절, 반대청약, 기간만료 등이며 '공시'는 해당되지 않습니다.",
        page_number=1,
    ),
    Question(
        id=2, subject="무역규범",
        question_text="인코텀즈(Incoterms) 2020에서 매도인의 위험 부담이 가장 큰 조건은?",
        options=["① EXW", "② FCA", "③ CIF", "④ DDP"],
        answer="④ DDP",
        explanation="DDP(Delivered Duty Paid)는 목적지까지의 모든 비용과 위험을 매도인이 부담하는 조건입니다.",
        page_number=1,
    ),
    Question(
        id=3, subject="무역결제",
        question_text="신용장(L/C)에서 일람출급(Sight) 어음을 사용할 때 대금 지급 시기는?",
        options=["① 선적 후 30일", "② 서류 제시 즉시", "③ 만기일", "④ 선적일"],
        answer="② 서류 제시 즉시",
        explanation="일람출급 어음은 제시와 동시에 지급이 이루어집니다.",
        page_number=2,
    ),
    Question(
        id=4, subject="무역결제",
        question_text="추심결제(Collection) 방식 중 D/P(Documents against Payment)에 대한 설명으로 옳은 것은?",
        options=["① 인수 후 서류 인도", "② 지급 후 서류 인도", "③ 신용장 개설 필요", "④ 은행 지급 보증"],
        answer="② 지급 후 서류 인도",
        explanation="D/P는 수입상이 대금을 지급해야만 선적서류를 인도받을 수 있는 방식입니다.",
        page_number=2,
    ),
    Question(
        id=5, subject="무역물류",
        question_text="해상화물운송장(Sea Waybill)과 선하증권(B/L)의 차이점으로 옳은 것은?",
        options=["① 해상화물운송장은 유통성 있음", "② 선하증권은 권리증권임", "③ 해상화물운송장 원본 3통 발행", "④ 선하증권은 지시식 불가"],
        answer="② 선하증권은 권리증권임",
        explanation="선하증권(B/L)은 유통성 있는 권리증권이며, 해상화물운송장은 비유통성 서류입니다.",
        page_number=3,
    ),
    Question(
        id=6, subject="무역물류",
        question_text="컨테이너 운송에서 FCL(Full Container Load)에 대한 설명으로 옳은 것은?",
        options=["① 혼재화물 운송", "② 단일 화주가 컨테이너 전체 사용", "③ 소량 화물 전용", "④ 항공 전용 용어"],
        answer="② 단일 화주가 컨테이너 전체 사용",
        explanation="FCL은 한 화주가 컨테이너 하나를 전용으로 사용하는 방식입니다.",
        page_number=3,
    ),
    Question(
        id=7, subject="무역규범",
        question_text="WTO 분쟁해결기구(DSB)의 패널 보고서 채택 방식은?",
        options=["① 만장일치", "② 역전컨센서스(Negative Consensus)", "③ 단순다수결", "④ 의장 단독 결정"],
        answer="② 역전컨센서스(Negative Consensus)",
        explanation="WTO DSB는 보고서에 반대하는 전원 합의가 없으면 자동 채택되는 역전컨센서스 방식을 사용합니다.",
        page_number=4,
    ),
    Question(
        id=8, subject="무역영어",
        question_text="무역 서신에서 'We acknowledge receipt of your letter dated ~'의 의미로 옳은 것은?",
        options=["① 서신 발송 확인", "② 서신 수신 확인", "③ 주문 취소 통보", "④ 대금 청구"],
        answer="② 서신 수신 확인",
        explanation="'acknowledge receipt of'는 '~를 수령했음을 확인한다'는 뜻입니다.",
        page_number=4,
    ),
    Question(
        id=9, subject="무역결제",
        question_text="무역금융에서 포페이팅(Forfaiting)의 특징으로 옳은 것은?",
        options=["① 소구권(Recourse) 있음", "② 단기 금융(90일 이내)", "③ 무소구권(Without Recourse)", "④ 국내 거래 전용"],
        answer="③ 무소구권(Without Recourse)",
        explanation="포페이팅은 수출채권을 무소구 방식으로 매입하는 중장기 무역금융입니다.",
        page_number=5,
    ),
    Question(
        id=10, subject="무역물류",
        question_text="항공화물운송장(AWB)의 성격으로 옳은 것은?",
        options=["① 유통증권", "② 권리증권", "③ 비유통성 화물수취증", "④ 보험증권"],
        answer="③ 비유통성 화물수취증",
        explanation="AWB는 선하증권과 달리 유통성이 없으며 단순한 화물수취증 겸 운송계약서입니다.",
        page_number=5,
    ),
]


def _start_exam(questions: list[Question]) -> None:
    """세션 초기화 후 exam 페이지로 이동."""
    st.session_state.questions = questions
    st.session_state.exam_state = ExamState()
    st.session_state.final_score = 0.0
    st.session_state.incorrect_questions = []
    st.session_state.page = "exam"


def render() -> None:
    """홈 화면 렌더링."""

    parsed_q = st.session_state.parsed_questions
    parsed_a = st.session_state.parsed_answers

    # 3열 레이아웃으로 중앙 카드 집중
    _, col, _ = st.columns([1, 2.2, 1])

    with col:
        # ── 카드 시작 ─────────────────────────────────────────────────────
        st.markdown('<div class="cbt-card">', unsafe_allow_html=True)

        # 아이콘 원형 배경
        st.markdown(
            '<div class="icon-circle">📄</div>',
            unsafe_allow_html=True,
        )

        # 제목 / 부제목
        st.markdown('<p class="cbt-title">CBT Mock Test</p>', unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════════
        # API 키 입력
        # ══════════════════════════════════════════════════════════════════
        has_key = bool(st.session_state.api_key)

        if not has_key:
            st.markdown(
                "<p style='text-align:center; font-size:0.85rem; color:#6b7280; margin-bottom:4px;'>"
                "PDF 분석을 위해 OpenAI API 키가 필요합니다</p>",
                unsafe_allow_html=True,
            )

        input_key = st.text_input(
            "OpenAI API Key",
            value=st.session_state.api_key,
            type="password",
            placeholder="sk-...",
            label_visibility="collapsed",
            key="api_key_input",
        )

        # 키가 변경되면 저장 + 클라이언트 리셋
        if input_key != st.session_state.api_key:
            st.session_state.api_key = input_key
            os.environ["OPENAI_API_KEY"] = input_key
            reset_client()
            st.rerun()

        if has_key:
            st.markdown(
                "<p style='text-align:center; font-size:0.75rem; color:#10b981; margin-top:-8px; margin-bottom:16px;'>"
                "API 키 설정 완료</p>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown("<br>", unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════════
        # 파싱 완료 → 결과 + 시험 시작 화면
        # ══════════════════════════════════════════════════════════════════
        if parsed_q:
            st.markdown(
                '<p class="cbt-subtitle">문제 분석이 완료되었습니다</p>',
                unsafe_allow_html=True,
            )

            # ── 결과 요약 카드 ───────────────────────────────────────────
            status_left, status_right = st.columns(2)
            with status_left:
                st.success(f"📋 {len(parsed_q)}개 문제 추출 완료")
            with status_right:
                if parsed_a:
                    st.success(f"📝 {len(parsed_a)}개 답안 추출 완료")
                else:
                    st.info("📝 답지 없음 (채점 불가)")

            # ── 답 병합 ────────────────────────────────────────────────
            if parsed_a:
                final_questions = merge_answers(parsed_q, parsed_a)
            else:
                final_questions = parsed_q

            # ── 과목 선택 ──────────────────────────────────────────────
            subjects = sorted(set(q.subject for q in final_questions if q.subject))

            if len(subjects) > 1:
                st.markdown(
                    "<p style='text-align:center; font-size:0.85rem; color:#6b7280; "
                    "margin:16px 0 8px 0;'>응시할 과목을 선택하세요</p>",
                    unsafe_allow_html=True,
                )
                # 과목별 문제 수 계산
                subj_counts = {}
                for q in final_questions:
                    subj_counts[q.subject] = subj_counts.get(q.subject, 0) + 1

                selected = st.multiselect(
                    "과목 선택",
                    options=subjects,
                    default=subjects,
                    format_func=lambda s: f"{s} ({subj_counts.get(s, 0)}문제)",
                    label_visibility="collapsed",
                    key="subject_selector",
                )
            else:
                selected = subjects

            # 선택된 과목의 문제만 필터
            if selected:
                filtered = [q for q in final_questions if q.subject in selected]
            else:
                filtered = final_questions

            st.markdown("<br>", unsafe_allow_html=True)

            # ── 시험 시작 버튼 ───────────────────────────────────────────
            has_answers = sum(1 for q in filtered if q.answer)
            if has_answers:
                label = f"시험 시작 → ({len(filtered)}문제, {has_answers}개 답 매칭)"
            else:
                label = f"시험 시작 → ({len(filtered)}문제)"

            st.button(
                label,
                key="start_pdf_exam",
                type="primary",
                on_click=_start_exam,
                args=(filtered,),
                disabled=len(filtered) == 0,
            )

            # ── 답지 추가 업로드 (문제만 있고 답지 아직 없을 때) ─────────
            if not parsed_a:
                st.markdown('<hr class="cbt-divider">', unsafe_allow_html=True)
                st.markdown(
                    "<p style='text-align:center; font-size:0.85rem; color:#9ca3af; margin-bottom:10px;'>"
                    "채점을 원하시면 답지 PDF를 추가해 주세요</p>",
                    unsafe_allow_html=True,
                )
                answer_file_late = st.file_uploader(
                    "답지 PDF 업로드",
                    type=["pdf"],
                    label_visibility="collapsed",
                    key="answer_pdf_late_uploader",
                )
                if answer_file_late is not None and not parsed_a:
                    with st.spinner("📝 AI가 답지를 분석하고 있습니다..."):
                        answers = parse_answer_pdf(answer_file_late.read())
                    if answers:
                        st.session_state.parsed_answers = answers
                        st.rerun()
                    else:
                        st.error("❌ 답안을 추출하지 못했습니다.")

            # ── 다시 업로드 버튼 ─────────────────────────────────────────
            def _reset_uploads():
                st.session_state.parsed_questions = []
                st.session_state.parsed_answers = []
            st.button(
                "🔄 다시 업로드",
                key="reset_uploads",
                on_click=_reset_uploads,
            )

        # ══════════════════════════════════════════════════════════════════
        # 파싱 전 → 업로드 화면
        # ══════════════════════════════════════════════════════════════════
        else:
            st.markdown(
                '<p class="cbt-subtitle">문제 PDF와 답지 PDF를 업로드하여 시험을 시작하세요</p>',
                unsafe_allow_html=True,
            )

            # ── 2열 업로드 영역 ──────────────────────────────────────────
            upload_left, upload_right = st.columns(2)

            with upload_left:
                st.markdown(
                    '<div class="upload-zone" style="padding:28px 20px;">'
                    '<div style="font-size:1.8rem; margin-bottom:8px;">📋</div>'
                    '<p style="font-size:0.9rem; color:#374151; font-weight:600; margin-bottom:4px;">'
                    '문제 PDF</p>'
                    '<p style="font-size:0.8rem; color:#9ca3af; margin-bottom:10px;">'
                    '시험 문제 파일</p>',
                    unsafe_allow_html=True,
                )
                question_file = st.file_uploader(
                    "문제 PDF 업로드",
                    type=["pdf"],
                    label_visibility="collapsed",
                    key="question_pdf_uploader",
                )
                st.markdown("</div>", unsafe_allow_html=True)

            with upload_right:
                st.markdown(
                    '<div class="upload-zone" style="padding:28px 20px;">'
                    '<div style="font-size:1.8rem; margin-bottom:8px;">📝</div>'
                    '<p style="font-size:0.9rem; color:#374151; font-weight:600; margin-bottom:4px;">'
                    '답지 PDF</p>'
                    '<p style="font-size:0.8rem; color:#9ca3af; margin-bottom:10px;">'
                    '정답 및 해설 파일 (선택)</p>',
                    unsafe_allow_html=True,
                )
                answer_file = st.file_uploader(
                    "답지 PDF 업로드",
                    type=["pdf"],
                    label_visibility="collapsed",
                    key="answer_pdf_uploader",
                )
                st.markdown("</div>", unsafe_allow_html=True)

            # ── 파싱 처리 ────────────────────────────────────────────────
            if question_file is not None:
                if not has_key:
                    st.warning("API 키를 먼저 입력해 주세요.")
                else:
                    with st.spinner("📖 AI가 문제 PDF를 분석하고 있습니다..."):
                        questions = parse_pdf(question_file.read())

                    if not questions:
                        st.error(
                            "❌ 문제를 추출하지 못했습니다.  \n"
                            "API 키가 유효한지, PDF에 텍스트가 포함되어 있는지 확인해 주세요.",
                        )
                    else:
                        st.session_state.parsed_questions = questions

                        # 답지도 함께 업로드된 경우 연속 파싱
                        if answer_file is not None:
                            with st.spinner("📝 AI가 답지 PDF를 분석하고 있습니다..."):
                                answers = parse_answer_pdf(answer_file.read())
                            if answers:
                                st.session_state.parsed_answers = answers

                        st.rerun()

        # ── 구분선 + 샘플 시험 ───────────────────────────────────────────
        st.markdown('<hr class="cbt-divider">', unsafe_allow_html=True)
        st.markdown(
            "<p style='text-align:center; font-size:0.85rem; color:#9ca3af; margin-bottom:14px;'>"
            "PDF가 없으신가요? 샘플 시험을 체험해 보세요</p>",
            unsafe_allow_html=True,
        )

        st.button(
            "Start Sample Test",
            key="start_sample",
            type="primary",
            on_click=_start_exam,
            args=(_SAMPLE_QUESTIONS,),
        )

        st.markdown("</div>", unsafe_allow_html=True)  # cbt-card 닫기

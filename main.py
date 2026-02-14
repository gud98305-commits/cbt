"""
main.py — 앱 진입점

역할:
  1. trade_license_cbt 패키지 경로 등록
  2. st.set_page_config (최초 1회 실행 보장)
  3. 전역 CSS 주입
  4. session_state 초기화
  5. 페이지 라우팅 (home → exam → result)
"""

import os
import sys

# ── trade_license_cbt를 모듈 검색 경로에 추가 ────────────────────────────────
_APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_license_cbt")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import streamlit as st

# ── 반드시 최상단에 위치해야 함 ──────────────────────────────────────────────
st.set_page_config(
    page_title="CBT Mock Test",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 전역 CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── 기본 레이아웃 ── */
    #MainMenu, footer, header { visibility: hidden; }

    .stApp {
        background: linear-gradient(150deg, #d6e8f7 0%, #eaf2fb 45%, #f4f8fd 100%);
        min-height: 100vh;
    }
    .block-container {
        padding: 2rem 1.5rem 2rem 1.5rem !important;
        max-width: 100% !important;
    }

    /* ── 카드 컨테이너 ── */
    .cbt-card {
        background: #ffffff;
        border-radius: 20px;
        padding: 48px 44px;
        box-shadow: 0 4px 32px rgba(74, 127, 203, 0.10);
    }

    /* ── 업로드 영역 ── */
    .upload-zone {
        border: 2px dashed #b8cfe8;
        border-radius: 14px;
        padding: 52px 32px;
        text-align: center;
        background: #f7fafd;
        transition: border-color 0.2s;
    }
    .upload-zone:hover { border-color: #4a7fcb; }

    /* ── 아이콘 원형 배경 ── */
    .icon-circle {
        width: 72px; height: 72px;
        background: #e8f0fe;
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        margin: 0 auto 20px auto;
        font-size: 32px;
    }

    /* ── 타이틀 ── */
    .cbt-title {
        font-size: 2rem; font-weight: 700;
        color: #1a1a2e; text-align: center;
        margin-bottom: 6px;
    }
    .cbt-subtitle {
        font-size: 0.95rem; color: #6b7280;
        text-align: center; margin-bottom: 32px;
    }

    /* ── Streamlit 기본 버튼 오버라이드 ── */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: #0d0d0d !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.65rem 1.6rem !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        width: 100%;
        transition: background 0.2s !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: #2a2a2a !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"] {
        background: #ffffff !important;
        color: #1a1a2e !important;
        border: 1.5px solid #d1d9e6 !important;
        border-radius: 10px !important;
        padding: 0.55rem 1.4rem !important;
        font-size: 0.9rem !important;
        font-weight: 500 !important;
        transition: border-color 0.2s !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"]:hover {
        border-color: #4a7fcb !important;
        color: #4a7fcb !important;
    }

    /* ── 파일 업로더 스타일 ── */
    [data-testid="stFileUploader"] {
        background: transparent !important;
    }
    [data-testid="stFileUploadDropzone"] {
        border: none !important;
        background: transparent !important;
        padding: 0 !important;
    }

    /* ── 문제 카드 ── */
    .question-card {
        background: #f7fafd;
        border-radius: 14px;
        padding: 28px 32px;
        margin-bottom: 20px;
        border-left: 4px solid #4a7fcb;
    }
    .context-box {
        background: #eef4fb;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 16px;
        font-size: 0.9rem;
        color: #374151;
        line-height: 1.7;
    }
    .question-number-badge {
        display: inline-block;
        background: #4a7fcb;
        color: white;
        border-radius: 8px;
        padding: 2px 12px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-bottom: 12px;
    }

    /* ── 사이드바 문제 번호 버튼 ── */
    .nav-btn-answered {
        background: #4a7fcb !important;
        color: white !important;
        border-radius: 8px !important;
        border: none !important;
    }
    .nav-btn-current {
        background: #1a1a2e !important;
        color: white !important;
        border-radius: 8px !important;
    }

    /* ── 점수 결과 카드 ── */
    .score-big {
        font-size: 5rem; font-weight: 800;
        text-align: center; line-height: 1;
    }
    .pass-badge {
        display: inline-block;
        border-radius: 24px;
        padding: 6px 24px;
        font-size: 1.1rem;
        font-weight: 700;
        margin: 0 auto;
    }
    .pass-badge.pass   { background: #d1fae5; color: #065f46; }
    .pass-badge.fail   { background: #fee2e2; color: #991b1b; }

    /* ── 구분선 ── */
    hr.cbt-divider {
        border: none;
        border-top: 1px solid #e5eaf2;
        margin: 24px 0;
    }

    /* ── 라디오 버튼 스타일 ── */
    [data-testid="stRadio"] label {
        font-size: 0.95rem !important;
        padding: 4px 0 !important;
    }

    /* ── 진행 바 ── */
    [data-testid="stProgress"] > div > div {
        background: #4a7fcb !important;
    }

    /* ── 타이머 ── */
    .timer-display {
        font-size: 1.5rem;
        font-weight: 700;
        text-align: center;
        color: #1a1a2e;
        letter-spacing: 2px;
        background: #f0f4fb;
        border-radius: 10px;
        padding: 10px 0;
        margin-bottom: 16px;
    }
    .timer-warning { color: #dc2626 !important; background: #fee2e2 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session State 초기화 ──────────────────────────────────────────────────────
def _init_session() -> None:
    defaults = {
        "page": "home",          # "home" | "exam" | "result"
        "questions": [],         # List[Question]
        "exam_state": None,      # ExamState | None
        "final_score": 0.0,
        "incorrect_questions": [],
        "parsed_questions": [],  # 문제 PDF 파싱 결과 (답 병합 전)
        "parsed_answers": [],    # 답지 PDF 파싱 결과
        "api_key": "",           # 사용자 입력 OpenAI API 키
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

_init_session()

# ── 라우팅 ────────────────────────────────────────────────────────────────────
page = st.session_state.page

if page == "home":
    from views.home_view import render
    render()
elif page == "exam":
    from views.exam_view import render
    render()
elif page == "result":
    from views.result_view import render
    render()

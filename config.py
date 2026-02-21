import os

# 기본 디렉토리 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 경로 설정
STATIC_DIR = os.path.join(BASE_DIR, "static")
LOG_FILE = os.path.join(BASE_DIR, "launch.log")

# 서버 설정
DEFAULT_HOST = os.getenv("HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("PORT", "8000"))

# OpenAI 설정
MODEL_NAME = "gpt-4o"

# PDF 파싱 설정
MAX_PDF_PAGES = 200
VISION_DPI = 200        # 페이지 이미지 해상도
PAGES_PER_GROUP = 3     # 비전 API 호출당 페이지 수

# 텍스트 우선 파싱 설정
MIN_CHARS_PER_PAGE = 100    # 페이지당 최소 문자 수 (이하이면 스캔 PDF로 판단 → 비전 폴백)
MAX_SECTION_CHARS = 80000   # 텍스트 청크 최대 문자 수
TEXT_PAGES_PER_GROUP = 5    # 텍스트 파싱 시 그룹당 페이지 수 (비전보다 넉넉)

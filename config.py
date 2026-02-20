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

import os
import sys

# 기본 디렉토리 설정
IF_FROZEN = getattr(sys, "frozen", False)
BASE_DIR = sys._MEIPASS if IF_FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 경로 설정
STATIC_DIR = os.path.join(BASE_DIR, "static")
APP_DIR = os.path.join(BASE_DIR, "trade_license_cbt")
LOG_FILE = os.path.join(BASE_DIR, "launch.log")

# 서버 설정
DEFAULT_HOST = "127.0.0.1"
DEFAULT_TIMEOUT = 15.0

# OpenAI 설정
MODEL_NAME = "gpt-4o-mini"

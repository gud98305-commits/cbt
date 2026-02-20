"""
main.py — CBT 웹 앱 진입점
"""

import os
import sys
import logging

# ── 패키지 경로 설정 ──────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from config import BASE_DIR, LOG_FILE, DEFAULT_HOST, DEFAULT_PORT

# ── 로깅 설정 ────────────────────────────────────────────────────────────────
try:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
except (PermissionError, OSError):
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# ── 메인 실행 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from api.app import create_app

    logger.info("=== CBT Mock Test Application Started ===")
    os.chdir(BASE_DIR)

    app = create_app()
    logger.info(f"서버 시작: http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT, log_level="info")

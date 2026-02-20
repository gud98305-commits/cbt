"""
main.py — CBT 데스크톱 앱 진입점
"""

import os
import socket
import subprocess
import sys
import time
import threading
import logging
import traceback

# ── 패키지 경로 설정 (반드시 최상단) ──────────────────────────────────────────
# 실행 경로를 BASE_DIR로 설정하고 trade_license_cbt를 모듈 경로에 추가합니다.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from config import BASE_DIR, LOG_FILE, DEFAULT_HOST

# ── 로깅 설정 ────────────────────────────────────────────────────────────────
class DummyStream:
    def write(self, data): pass
    def flush(self): pass
    def isatty(self): return False
    def close(self): pass

if sys.stdout is None: sys.stdout = DummyStream()
if sys.stderr is None: sys.stderr = DummyStream()

try:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
except PermissionError:
    # 로그 파일 점유 시 콘솔 출력만 사용
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# ── 서버 및 네트워크 유틸 ───────────────────────────────────────────────────

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((DEFAULT_HOST, 0))
        return s.getsockname()[1]

def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((DEFAULT_HOST, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False

def _open_browser(url: str) -> None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    flags = [f"--app={url}", "--no-first-run", "--window-size=1280,800"]
    
    for path in candidates:
        if os.path.exists(path):
            logger.info(f"브라우저 실행 시도: {path}")
            subprocess.Popen([path] + flags)
            return
            
    import webbrowser
    webbrowser.open(url)

def _start_server(port: int) -> None:
    try:
        import uvicorn
        from api.app import create_app
        logger.info(f"Uvicorn 서버 시작 - Port: {port}")
        # uvicorn 실행 시 factory=True가 필요할 수 있으므로 app 인스턴스 직접 생성
        app = create_app()
        uvicorn.run(app, host=DEFAULT_HOST, port=port, log_level="error")
    except Exception:
        logger.error(f"서버 오류 발생:\n{traceback.format_exc()}")

# ── 메인 실행 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("=== CBT Mock Test Application Started ===")
    os.chdir(BASE_DIR)

    port = _find_free_port()
    server_thread = threading.Thread(target=_start_server, args=(port,), daemon=True)
    server_thread.start()

    if _wait_for_server(port):
        logger.info("서버 준비 완료. 브라우저를 엽니다.")
        _open_browser(f"http://{DEFAULT_HOST}:{port}")
        
        # 메인 스레드 유지
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            logger.info("사용자에 의해 종료되었습니다.")
    else:
        logger.error("서버 시작 제한 시간을 초과했습니다. 작업 관리자에서 기존 프로세스를 종료해 보세요.")
        sys.exit(1)

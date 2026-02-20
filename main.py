"""
main.py — CBT 데스크톱 앱 진입점
"""

import os
import socket
import subprocess
import sys
import time
import threading
import traceback

# pythonw.exe는 stdout/stderr가 None — uvicorn 로깅 크래시 방지
class DummyStream:
    def write(self, data): pass
    def flush(self): pass
    def isatty(self): return False
    def close(self): pass

if sys.stdout is None:
    sys.stdout = DummyStream()
if sys.stderr is None:
    sys.stderr = DummyStream()

# PyInstaller 번들 환경에서 static 경로 보정
if getattr(sys, "frozen", False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(_BASE_DIR)

# 로그 파일 (항상 기록)
_LOG = os.path.join(_BASE_DIR, "launch.log")

def log(msg: str) -> None:
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


try:
    from api.app import create_app
    log("api.app import OK")
except Exception as e:
    log(f"IMPORT ERROR: {traceback.format_exc()}")
    sys.exit(1)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _open_browser(url: str) -> None:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    flags = ["--app=" + url, "--no-first-run", "--no-default-browser-check",
             "--window-size=1280,800"]
    for path in candidates:
        if os.path.exists(path):
            log(f"Opening browser: {path}")
            subprocess.Popen([path] + flags)
            return
    log("No Edge/Chrome found, using default browser")
    import webbrowser
    webbrowser.open(url)


def _start_server(port: int) -> None:
    try:
        import uvicorn
        log(f"uvicorn starting on port {port}")
        uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="error")
    except Exception as e:
        log(f"SERVER ERROR: {traceback.format_exc()}")


if __name__ == "__main__":
    log("=== main.py started ===")
    log(f"BASE_DIR: {_BASE_DIR}")
    log(f"sys.path: {sys.path[:3]}")

    port = _find_free_port()
    log(f"Port selected: {port}")

    server_thread = threading.Thread(target=_start_server, args=(port,), daemon=True)
    server_thread.start()

    log("Waiting for server...")
    if not _wait_for_server(port, timeout=15.0):
        log("ERROR: Server did not start within 15 seconds")
        sys.exit(1)

    log("Server is up. Opening browser...")
    _open_browser(f"http://127.0.0.1:{port}")

    log("Keeping server alive...")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log("Stopped by user")

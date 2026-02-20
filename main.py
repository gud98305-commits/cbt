"""
main.py — CBT 데스크톱 앱 진입점

FastAPI 서버를 백그라운드 스레드에서 실행하고,
PyWebView로 네이티브 창을 열어 앱을 표시한다.
"""

import threading
import time
import sys
import os

# PyInstaller 번들 환경에서 static 경로 보정
if getattr(sys, "frozen", False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(_BASE_DIR)

from api.app import create_app


def start_server(port: int) -> None:
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="error")


if __name__ == "__main__":
    port = 18765

    t = threading.Thread(target=start_server, args=(port,), daemon=True)
    t.start()

    # 서버 기동 대기
    time.sleep(1.5)

    import webview
    window = webview.create_window(
        "CBT Mock Test",
        f"http://127.0.0.1:{port}",
        width=1280,
        height=800,
        min_size=(800, 600),
    )
    webview.start()

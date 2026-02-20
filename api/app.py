"""
api/app.py — FastAPI 앱 인스턴스 + 세션 미들웨어 + static 파일 서빙
"""

import logging
import os
import threading
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import STATIC_DIR
from api.routes import router
import api.session as session

SESSION_COOKIE = "cbt_session"


def create_app() -> FastAPI:
    app = FastAPI(title="CBT Mock Test", docs_url=None, redoc_url=None)

    # CORS (모바일 브라우저 등 다양한 출처 허용)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 세션 미들웨어: 쿠키에서 세션 ID를 읽고, 없으면 새로 발급
    @app.middleware("http")
    async def session_middleware(request: Request, call_next):
        sid = request.cookies.get(SESSION_COOKIE)
        if not sid or session.get_session(sid) is None:
            sid = session.create_session()

        request.state.session_id = sid
        response: Response = await call_next(request)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=sid,
            httponly=True,
            samesite="lax",
            max_age=session.SESSION_TTL,
        )
        return response

    app.include_router(router)

    # static 파일 마운트
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # 루트 → index.html
    @app.get("/")
    async def serve_index():
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "index.html not found"}

    # 만료 세션 주기적 정리 (5분마다)
    def _cleanup_loop():
        while True:
            time.sleep(300)
            removed = session.cleanup_expired()
            if removed:
                logging.getLogger(__name__).info(f"만료 세션 {removed}개 정리")

    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()

    return app

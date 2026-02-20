"""
api/app.py — FastAPI 앱 인스턴스 + static 파일 서빙
"""

import os
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routes import router

_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def create_app() -> FastAPI:
    app = FastAPI(title="CBT Mock Test", docs_url=None, redoc_url=None)

    app.include_router(router)

    # static 파일 마운트 (/static 경로)
    if os.path.isdir(_STATIC_DIR):
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    # 루트 → index.html
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

    return app

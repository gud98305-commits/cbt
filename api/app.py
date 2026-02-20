"""
api/app.py — FastAPI 앱 인스턴스 + static 파일 서빙
"""

import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.config import STATIC_DIR
from api.routes import router

def create_app() -> FastAPI:
    app = FastAPI(title="CBT Mock Test", docs_url=None, redoc_url=None)

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

    return app

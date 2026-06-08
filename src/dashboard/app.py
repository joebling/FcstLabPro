"""FastAPI app 工厂 — 装配路由 + 模板 + 静态资源."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.dashboard.config import STATIC_DIR, TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app() -> FastAPI:
    app = FastAPI(title="FcstLabPro Performance Dashboard", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    from src.dashboard.routes import pages
    app.include_router(pages.router)
    return app


app = create_app()

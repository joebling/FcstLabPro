"""整页路由 — GET /."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.dashboard import data_access

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, model: str | None = None):
    from src.dashboard.app import templates

    models = data_access.list_models()
    active = model if model in models else (models[0] if models else None)

    ctx = {
        "request": request,
        "models": models,
        "active_model": active,
        "batches": data_access.load_batches(active) if active else {"rows": [], "reason": "no_data"},
        "summary": data_access.load_summary(active) if active else {},
    }
    return templates.TemplateResponse(request, "index.html", ctx)

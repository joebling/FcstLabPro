"""HTMX 局部路由 — 模型切换时只换表格/KPI 区, 不整页刷新."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.dashboard import data_access

router = APIRouter()


@router.get("/partial/model", response_class=HTMLResponse)
def model_partial(request: Request, model: str):
    """切模型: 同时换 KPI + 表格 (一个 fragment 包两块)."""
    from src.dashboard.app import templates

    ctx = {
        "request": request,
        "active_model": model,
        "batches": data_access.load_batches(model),
        "summary": data_access.load_summary(model),
    }
    return templates.TemplateResponse(request, "partials/model_view.html", ctx)

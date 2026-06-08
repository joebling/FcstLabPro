"""整页路由 — 6 页 (总览/信号/市场/顶部/模型/实盘).

每页共享 base context (侧边栏导航 + 模型选择)。
具体卡片/图表数据在各 partial 路由或页面 context builder 里取。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.dashboard import data_access

router = APIRouter()


def _base_ctx(request: Request, active_page: str, model: str | None) -> dict:
    """侧边栏共享 context: 导航高亮 + 模型列表/选中."""
    models = data_access.list_models()
    active = model if model in models else (models[0] if models else None)
    return {
        "request": request,
        "active_page": active_page,
        "models": models,
        "active_model": active,
    }


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, model: str | None = None):
    from src.dashboard.app import templates
    from src.dashboard.pages import overview as page
    ctx = _base_ctx(request, "overview", model)
    ctx.update(page.build(ctx["active_model"]))
    return templates.TemplateResponse(request, "pages/overview.html", ctx)


@router.get("/signals", response_class=HTMLResponse)
def signals(request: Request, model: str | None = None):
    from src.dashboard.app import templates
    from src.dashboard.pages import signals as page
    ctx = _base_ctx(request, "signals", model)
    ctx.update(page.build(ctx["active_model"]))
    return templates.TemplateResponse(request, "pages/signals.html", ctx)


@router.get("/market", response_class=HTMLResponse)
def market(request: Request, model: str | None = None):
    from src.dashboard.app import templates
    from src.dashboard.pages import market as page
    ctx = _base_ctx(request, "market", model)
    ctx.update(page.build())
    return templates.TemplateResponse(request, "pages/market.html", ctx)


@router.get("/models", response_class=HTMLResponse)
def models(request: Request, model: str | None = None):
    from src.dashboard.app import templates
    from src.dashboard.pages import models as page
    ctx = _base_ctx(request, "models", model)
    ctx.update(page.build())
    return templates.TemplateResponse(request, "pages/models.html", ctx)


@router.get("/topping", response_class=HTMLResponse)
def topping(request: Request, model: str | None = None):
    from src.dashboard.app import templates
    from src.dashboard.pages import topping as page
    ctx = _base_ctx(request, "topping", model)
    ctx.update(page.build())
    return templates.TemplateResponse(request, "pages/topping.html", ctx)


@router.get("/perfmon", response_class=HTMLResponse)
def perfmon(request: Request, model: str | None = None):
    from src.dashboard.app import templates
    from src.dashboard.pages import perfmon as page
    ctx = _base_ctx(request, "perfmon", model)
    ctx.update(page.build(ctx["active_model"]))
    return templates.TemplateResponse(request, "pages/perfmon.html", ctx)

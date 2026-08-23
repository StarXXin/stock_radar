"""页面路由(Jinja2 服务端渲染):仪表盘 / 历史 / 配置 / 运行。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query, Request
from starlette.templating import Jinja2Templates

from exceptions import StorageError
from store import Store
from webapp.envfile import mask_secret, read_env
from webapp.routers.deps import get_env_path, get_runner, get_store
from webapp.schemas import FORM_FIELDS

router = APIRouter()

_SECRET_KEYS = ("DEEPSEEK_API_KEY", "PUSHPLUS_TOKEN")


@router.get("/")
def dashboard(request: Request) -> object:
    """仪表盘:统计卡片 + 最近记录 + 密钥配置状态。"""
    templates: Jinja2Templates = request.app.state.templates
    store: Store = get_store(request)
    runner = get_runner(request)

    total = 0
    stats: dict[str, int] = {}
    recent: list = []
    recent_pushed_at = None
    error_msg = None
    try:
        total = store.count_pushed()
        stats = store.stats_by_importance(days=7)
        recent = store.list_pushed(limit=8)
        recent_pushed_at = store.recent_pushed_at()
    except StorageError as e:
        error_msg = f"读取本地存储失败: {e}"

    env = read_env(get_env_path(request))
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "total": total,
            "stats": stats,
            "recent": recent,
            "recent_pushed_at": recent_pushed_at,
            "error": error_msg,
            "run_status": runner.status()["status"],
            "secrets": {key: mask_secret(env.get(key, "")) for key in _SECRET_KEYS},
        },
    )


@router.get("/history")
def history(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> object:
    """已推送公告历史(分页)。"""
    templates: Jinja2Templates = request.app.state.templates
    store: Store = get_store(request)
    records: list = []
    total = 0
    error_msg = None
    try:
        records = store.list_pushed(limit=limit, offset=offset)
        total = store.count_pushed()
    except StorageError as e:
        error_msg = f"读取历史失败: {e}"
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "records": records,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_prev": offset > 0,
            "has_next": offset + limit < total,
            "error": error_msg,
        },
    )


@router.get("/config")
def config_page(request: Request, saved: int = 0) -> object:
    """配置编辑页:表单由 schemas.FORM_FIELDS 驱动;密钥只显掩码不可改。"""
    templates: Jinja2Templates = request.app.state.templates
    env_path: Path = get_env_path(request)

    values = read_env(env_path)
    fields = []
    for f in FORM_FIELDS:
        raw = values.get(f.key, "")
        checked = raw.strip().lower() in {"1", "true", "yes", "on"}
        fields.append({
            "f": f,
            "value": "" if f.ftype == "bool" else raw,
            "checked": checked,
        })
    secrets = {key: mask_secret(values.get(key, "")) for key in _SECRET_KEYS}
    return templates.TemplateResponse(
        request,
        "config.html",
        {"fields": fields, "secrets": secrets, "saved": bool(saved)},
    )


@router.get("/run")
def run_page(request: Request) -> object:
    """手动触发运行页。"""
    templates: Jinja2Templates = request.app.state.templates
    runner = get_runner(request)
    _, total_lines = runner.lines_since(-1)
    return templates.TemplateResponse(
        request,
        "run.html",
        {"run": runner.status(), "total_lines": total_lines},
    )

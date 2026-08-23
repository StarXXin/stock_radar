"""JSON API 路由:触发运行、轮询状态、保存配置、日志尾部。"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from exceptions import ConfigError
from webapp.envfile import update_env
from webapp.routers.deps import get_env_path, get_runner
from webapp.schemas import FORM_FIELDS, validate_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/run/start")
def start_run(request: Request, body: dict | None = None) -> object:
    """触发一轮运行;已在跑返回 409。body: {"dry_run": bool}。"""
    runner = get_runner(request)
    dry_run = bool((body or {}).get("dry_run", False))
    if not runner.start(dry_run=dry_run):
        return JSONResponse(
            {"started": False, "reason": "已有运行在进行中"}, status_code=409
        )
    return {"started": True, "dry_run": dry_run}


@router.get("/run/status")
def run_status(request: Request, offset: int = Query(-1)) -> object:
    """增量轮询:返回 offset 之后的新行与最新行号。"""
    runner = get_runner(request)
    lines, next_offset = runner.lines_since(offset)
    return {**runner.status(), "lines": lines, "next_offset": next_offset}


@router.post("/config")
async def save_config(request: Request) -> object:
    """保存表单到 .env:先全量校验,任一非法返回 422;成功重定向回配置页。"""
    env_path: Path = get_env_path(request)
    form = await request.form()

    updates: dict[str, str] = {}
    errors: list[str] = []
    for f in FORM_FIELDS:
        raw = form.get(f.key)
        value = raw if isinstance(raw, str) else ""
        try:
            updates[f.key] = validate_field(f, value)
        except ConfigError as e:
            errors.append(str(e))

    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=422)

    update_env(env_path, updates, validate=validate_by_key)
    return RedirectResponse("/config?saved=1", status_code=303)


def validate_by_key(key: str, value: str) -> None:
    """envfile 写盘前的最终校验回调(按键名查字段定义)。"""
    field_def = next((f for f in FORM_FIELDS if f.key == key), None)
    if field_def is not None:
        validate_field(field_def, value)


@router.get("/logtail")
def log_tail(request: Request, n: int = Query(100, ge=1, le=500)) -> object:
    """读运行日志最后 n 行(展示用;损坏/缺失容错)。"""
    log_path: Path = request.app.state.project_root / "data" / "stock_radar.log"
    try:
        if not log_path.exists():
            return {"lines": []}
        text = log_path.read_text(encoding="utf-8", errors="replace")
        return {"lines": text.splitlines()[-n:]}
    except OSError as e:
        logger.warning("读取日志失败: %s", e)
        return JSONResponse({"error": f"读取日志失败: {e}"}, status_code=500)

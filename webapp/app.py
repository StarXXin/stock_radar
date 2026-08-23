"""FastAPI 应用工厂:挂 Store / RunManager / 模板环境,注册页面与 API 路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

import config
from store import Store
from webapp.routers import api, pages
from webapp.runner import RunManager

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PKG_DIR = Path(__file__).resolve().parent


def create_app(
    db_path: Path | None = None,
    env_path: Path | None = None,
    project_root: Path | None = None,
) -> FastAPI:
    """构造 webapp。db_path/env_path 可注入便于测试(默认用 config 的真实路径)。"""
    root = project_root or _PROJECT_ROOT
    app = FastAPI(title="stock_radar 控制台", docs_url=None, redoc_url=None)

    app.state.store = Store(db_path) if db_path is not None else Store()
    app.state.env_path = env_path or (root / ".env")
    app.state.project_root = root
    app.state.templates = Jinja2Templates(directory=str(_PKG_DIR / "templates"))

    app.state.runner = RunManager(root)

    app.mount("/static", StaticFiles(directory=str(_PKG_DIR / "static")), name="static")
    app.include_router(pages.router)
    app.include_router(api.router)
    return app


def get_store(request: Request) -> object:
    return request.app.state.store


def log_file() -> Path:
    return Path(config.LOG_FILE)

"""路由依赖:从 app.state 取共享组件(Annotated 风格规避 ruff B008)。"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from starlette.templating import Jinja2Templates

from store import Store
from webapp.runner import RunManager


def get_store(request: Request) -> Store:
    store: Store = request.app.state.store
    return store


def get_runner(request: Request) -> RunManager:
    runner: RunManager = request.app.state.runner
    return runner


def get_templates(request: Request) -> Jinja2Templates:
    templates: Jinja2Templates = request.app.state.templates
    return templates


def get_env_path(request: Request) -> Path:
    env_path: Path = request.app.state.env_path
    return env_path

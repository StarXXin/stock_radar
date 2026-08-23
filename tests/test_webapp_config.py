"""webapp 配置页/保存接口测试:TestClient + 注入 tmp .env,绝不碰真实 .env。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webapp.app import create_app
from webapp.envfile import read_env


@pytest.fixture
def env_path(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text(
        "# 头注释保留\n"
        "DEEPSEEK_API_KEY=sk-xxx\n"
        "WATCHLIST=600519,000001\n"
        "LOOKBACK_DAYS=3\n",
        encoding="utf-8",
    )
    return env


@pytest.fixture
def client(env_path: Path, db_path) -> TestClient:
    app = create_app(db_path=db_path, env_path=env_path)
    return TestClient(app)


def test_config_page_renders_form(client: TestClient):
    resp = client.get("/config")
    assert resp.status_code == 200
    body = resp.text
    assert "WATCHLIST" in body
    assert "LOOKBACK_DAYS" in body
    # 密钥只显掩码,不显原文
    assert "sk-xxx" not in body
    assert "已配置" in body or "****" in body


def test_save_config_writes_env_and_preserves_comments(client: TestClient, env_path: Path):
    resp = client.post(
        "/api/config",
        data={
            "WATCHLIST": "600519=低,300750",
            "LOOKBACK_DAYS": "7",
            "DATA_SOURCE": "cninfo",
            "FETCH_CONTENT": "on",
            "KEYWORDS": "",
            "PUSH_MIN_IMPORTANCE": "中",
            "ROUTINE_TITLE_FILTER": "on",
            "ENRICH_CONCURRENCY": "2",
            "PUSH_MAX_PER_MESSAGE": "8",
            "ALERT_ON_ERROR": "",  # 未勾选
            "HEARTBEAT_DAYS": "0",
            "RETENTION_DAYS": "90",
            "LOG_LEVEL": "INFO",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    data = read_env(env_path)
    assert data["WATCHLIST"] == "600519=低,300750"
    assert data["LOOKBACK_DAYS"] == "7"
    assert data["DATA_SOURCE"] == "cninfo"
    assert data["FETCH_CONTENT"] == "true"
    assert data["ALERT_ON_ERROR"] == "false"
    # 非托管键与注释原样
    text = env_path.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-xxx" in text
    assert text.startswith("# 头注释保留")


def test_save_config_invalid_returns_422_without_write(client: TestClient, env_path: Path):
    before = env_path.read_text(encoding="utf-8")
    resp = client.post(
        "/api/config",
        data={
            "WATCHLIST": "非法代码!",
            "LOOKBACK_DAYS": "3",
            "PUSH_MIN_IMPORTANCE": "中",
            "ENRICH_CONCURRENCY": "2",
            "PUSH_MAX_PER_MESSAGE": "8",
            "RETENTION_DAYS": "90",
        },
    )
    assert resp.status_code == 422
    errors = resp.json()["errors"]
    assert any("WATCHLIST" in e for e in errors)
    assert env_path.read_text(encoding="utf-8") == before


def test_dashboard_page(client: TestClient, db_path):
    from models import Notice
    from store import Store

    store = Store(db_path)
    n = Notice(code="600519", name="贵州茅台", title="回购公告",
               date="2026-08-20", url="https://example.com/x")
    store.mark_pushed(n)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "600519" in resp.text


def test_history_pagination(client: TestClient, db_path):
    from models import Notice
    from store import Store

    store = Store(db_path)
    for i in range(3):
        n = Notice(code="600519", name="茅台", title=f"公告{i}",
                   date="2026-08-20", url=f"https://example.com/{i}")
        store.mark_pushed(n)

    resp = client.get("/history?limit=2")
    assert resp.status_code == 200
    assert "下一页" in resp.text

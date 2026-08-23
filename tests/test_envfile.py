"""envfile(.env 回写工具)测试:round-trip 保注释/顺序/非托管键、原子性、校验前置。"""

from pathlib import Path

import pytest

from exceptions import ConfigError
from webapp.envfile import read_env, update_env

SAMPLE = """# 头部注释,必须保留
DEEPSEEK_API_KEY=sk-secret-123  # 密钥行,非托管,原样保留

# ===== 常用 =====
LOOKBACK_DAYS=3
DATA_SOURCE=eastmoney,cninfo
WATCHLIST="600519,000001"   # 行内注释也要保留
PUSHPLUS_TOKEN=
"""


def _write_sample(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text(SAMPLE, encoding="utf-8")
    return env


def test_read_env_parses_values_and_quotes(tmp_path):
    env = _write_sample(tmp_path)
    data = read_env(env)
    assert data["LOOKBACK_DAYS"] == "3"
    assert data["WATCHLIST"] == "600519,000001"
    assert data["PUSHPLUS_TOKEN"] == ""
    assert data["DEEPSEEK_API_KEY"] == "sk-secret-123"
    assert "DATA_SOURCE" in data


def test_read_env_missing_file(tmp_path):
    assert read_env(tmp_path / "nope.env") == {}


def test_update_preserves_comments_order_and_unmanaged_keys(tmp_path):
    env = _write_sample(tmp_path)
    update_env(env, {"LOOKBACK_DAYS": "7", "PUSH_MIN_IMPORTANCE": "高"})
    text = env.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 注释与顺序保留
    assert lines[0] == "# 头部注释,必须保留"
    assert "# ===== 常用 =====" in text
    # 非托管键原样(含密钥与行内注释)
    assert "DEEPSEEK_API_KEY=sk-secret-123  # 密钥行,非托管,原样保留" in text
    assert 'WATCHLIST="600519,000001"   # 行内注释也要保留' in text
    # 托管键已替换
    assert "LOOKBACK_DAYS=7" in text
    assert "LOOKBACK_DAYS=3" not in text
    # 新键追加到末尾
    assert lines[-1] == "PUSH_MIN_IMPORTANCE=高"


def test_update_value_quoting_roundtrip(tmp_path):
    env = _write_sample(tmp_path)
    update_env(env, {"WATCHLIST": "600519=低,000001"})
    data = read_env(env)
    assert data["WATCHLIST"] == "600519=低,000001"


def test_update_value_with_space_gets_quoted(tmp_path):
    env = _write_sample(tmp_path)
    update_env(env, {"KEYWORDS": "中标, 合同"})  # 含空格,写回须加引号
    text = env.read_text(encoding="utf-8")
    assert 'KEYWORDS="中标, 合同"' in text
    assert read_env(env)["KEYWORDS"] == "中标, 合同"


def test_update_creates_missing_file(tmp_path):
    env = tmp_path / ".env"
    update_env(env, {"LOOKBACK_DAYS": "5"})
    assert env.read_text(encoding="utf-8") == "LOOKBACK_DAYS=5\n"


def test_update_backup_created(tmp_path):
    env = _write_sample(tmp_path)
    update_env(env, {"LOOKBACK_DAYS": "7"})
    backup = env.with_name(".env.bak")
    assert backup.exists()
    assert "LOOKBACK_DAYS=3" in backup.read_text(encoding="utf-8")


def test_invalid_value_aborts_entire_write(tmp_path):
    env = _write_sample(tmp_path)
    before = env.read_text(encoding="utf-8")

    def reject_watchlist(key: str, value: str) -> None:
        if key == "WATCHLIST" and "坏值" in value:
            raise ConfigError("非法 WATCHLIST")

    with pytest.raises(ConfigError):
        update_env(env, {"LOOKBACK_DAYS": "9", "WATCHLIST": "坏值"}, validate=reject_watchlist)
    # 整体未写:原文件不变,无备份产生
    assert env.read_text(encoding="utf-8") == before
    assert not env.with_name(".env.bak").exists()


def test_update_empty_updates_is_noop_write(tmp_path):
    env = _write_sample(tmp_path)
    update_env(env, {})
    assert env.read_text(encoding="utf-8") == SAMPLE

"""schemas(配置表单字段声明与校验)测试。"""

import pytest

from exceptions import ConfigError
from webapp.schemas import FORM_FIELDS, validate_field


def _field(key: str):
    return next(f for f in FORM_FIELDS if f.key == key)


def test_form_fields_cover_expected_keys():
    keys = {f.key for f in FORM_FIELDS}
    assert {"WATCHLIST", "LOOKBACK_DAYS", "DATA_SOURCE", "FETCH_CONTENT", "KEYWORDS",
            "PUSH_MIN_IMPORTANCE", "ENRICH_CONCURRENCY", "LOG_LEVEL"} <= keys
    # 密钥类绝不进表单
    assert "DEEPSEEK_API_KEY" not in keys
    assert "PUSHPLUS_TOKEN" not in keys


def test_watchlist_valid_with_threshold_override():
    out = validate_field(_field("WATCHLIST"), "600519=低, 000001 , 300750")
    assert out == "600519=低,000001,300750"


def test_watchlist_invalid_item():
    with pytest.raises(ConfigError, match="非法项"):
        validate_field(_field("WATCHLIST"), "60051,abc")


def test_int_range():
    assert validate_field(_field("LOOKBACK_DAYS"), "10") == "10"
    with pytest.raises(ConfigError, match="需在"):
        validate_field(_field("LOOKBACK_DAYS"), "0")
    with pytest.raises(ConfigError, match="需为整数"):
        validate_field(_field("LOOKBACK_DAYS"), "abc")
    # 0 合法(HEARTBEAT_DAYS/RETENTION_DAYS 的"关"语义)
    assert validate_field(_field("HEARTBEAT_DAYS"), "0") == "0"


def test_choice():
    assert validate_field(_field("PUSH_MIN_IMPORTANCE"), "中") == "中"
    with pytest.raises(ConfigError):
        validate_field(_field("PUSH_MIN_IMPORTANCE"), "特高")


def test_bool_serialization():
    for raw in ("on", "true", "1", "yes"):
        assert validate_field(_field("FETCH_CONTENT"), raw) == "true"
    assert validate_field(_field("FETCH_CONTENT"), "") == "false"
    assert validate_field(_field("FETCH_CONTENT"), "false") == "false"


def test_csv_sources_validated():
    assert validate_field(_field("DATA_SOURCE"), "eastmoney,cninfo") == "eastmoney,cninfo"
    with pytest.raises(ConfigError, match="含非法值"):
        validate_field(_field("DATA_SOURCE"), "eastmoney,sina")


def test_keywords_optional_empty_means_default():
    assert validate_field(_field("KEYWORDS"), "") == ""
    assert validate_field(_field("KEYWORDS"), "中标, 回购") == "中标,回购"


def test_required_field_rejects_empty():
    with pytest.raises(ConfigError, match="不能为空"):
        validate_field(_field("WATCHLIST"), "")

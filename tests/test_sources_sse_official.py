"""sse_official 数据源测试:全 mock HTTP,覆盖 JSONP 解析/去重/失败语义。"""

import json

import pytest

from exceptions import DataSourceError
from sources.sse_official import SseOfficialNoticeSource


def _resp(mocker, items):
    resp = mocker.Mock()
    resp.status_code = 200
    resp.raise_for_status = mocker.Mock()
    resp.text = f'jsonpCallback1({{"result": {json.dumps(items, ensure_ascii=False)}}})'
    return resp


def test_parses_jsonp_and_builds_notices(mocker):
    items = [
        {
            "TITLE": "股票交易异常波动公告",
            "SSEDATE": "2026-08-14",
            "URL": "/disclosure/listedinfo/announcement/c/new/2026-08-14/x.pdf",
            "SECURITY_NAME_ABBR": "太阳实业",
        }
    ]
    src = SseOfficialNoticeSource()
    mocker.patch.object(src._session, "get", return_value=_resp(mocker, items))

    out = src.fetch_recent(["600667"], lookback_days=3)

    assert len(out) == 1
    n = out[0]
    assert n.code == "600667"
    assert n.name == "太阳实业"
    assert n.date == "2026-08-14"
    assert n.url.startswith("https://static.sse.com.cn/")
    # 必须带 sse.com.cn Referer(防盗链,Session 级统一设置)
    assert "sse.com.cn" in src._session.headers["Referer"]


def test_dedup_within_window(mocker):
    items = [{"TITLE": "公告A", "SSEDATE": "2026-08-14", "URL": "/a.pdf"}]
    src = SseOfficialNoticeSource()
    mocker.patch.object(src._session, "get", return_value=_resp(mocker, items))
    out = src.fetch_recent(["600667"], lookback_days=2)  # 多天同数据
    assert len(out) == 1


def test_empty_result_is_ok(mocker):
    src = SseOfficialNoticeSource()
    mocker.patch.object(src._session, "get", return_value=_resp(mocker, []))
    assert src.fetch_recent(["600667"], lookback_days=3) == []


def test_all_failure_raises(mocker):
    import requests

    src = SseOfficialNoticeSource()
    mocker.patch.object(
        src._session, "get", side_effect=requests.RequestException("boom")
    )
    with pytest.raises(DataSourceError):
        src.fetch_recent(["600667"], lookback_days=3)


def test_partial_failure_continues(mocker):
    import requests

    src = SseOfficialNoticeSource()
    ok_resp = _resp(
        mocker,
        [{"TITLE": "公告A", "SSEDATE": "2026-08-14", "URL": "/a.pdf"}],
    )
    mocker.patch.object(
        src._session,
        "get",
        side_effect=[requests.RequestException("boom"), ok_resp],
    )
    out = src.fetch_recent(["600667", "601127"], lookback_days=3)
    assert len(out) == 1


def test_registered_in_registry():
    from sources import get_source

    src = get_source("sse_official")
    assert isinstance(src, SseOfficialNoticeSource)

import pandas as pd
import pytest

from exceptions import ConfigError
from sources import get_source
from sources.cninfo import CninfoNoticeSource
from sources.eastmoney import EastMoneyNoticeSource

_COLS = ["代码", "简称", "公告标题", "公告时间", "公告链接"]


def _df(rows):
    return pd.DataFrame(rows, columns=_COLS)


def test_registry_resolves_sources():
    assert isinstance(get_source("cninfo"), CninfoNoticeSource)
    assert isinstance(get_source("eastmoney"), EastMoneyNoticeSource)


def test_registry_unknown_raises():
    with pytest.raises(ConfigError):
        get_source("nope")


def test_fetch_maps_columns(mocker):
    df = _df(
        [
            [
                "601127",
                "赛力斯",
                "关于股份回购进展公告",
                "2026-07-02",
                "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=601127&announcementId=1",
            ]
        ]
    )
    m = mocker.patch(
        "sources.cninfo.ak.stock_zh_a_disclosure_report_cninfo", return_value=df
    )
    out = CninfoNoticeSource().fetch_recent(["601127"], lookback_days=7)
    assert len(out) == 1
    n = out[0]
    assert n.code == "601127"
    assert n.name == "赛力斯"
    assert n.title == "关于股份回购进展公告"
    assert n.date == "2026-07-02"
    assert "cninfo.com.cn" in n.url
    m.assert_called_once()  # 按代码逐只查询


def test_fetch_multiple_codes_and_dedup(mocker):
    df1 = _df([["600563", "法拉电子", "公告A", "2026-07-10", "http://x/1"]])
    df2 = _df(
        [
            ["601127", "赛力斯", "公告B", "2026-07-09", "http://x/2"],
            ["601127", "赛力斯", "公告B", "2026-07-09", "http://x/2"],  # 同一条应去重
        ]
    )
    mocker.patch(
        "sources.cninfo.ak.stock_zh_a_disclosure_report_cninfo", side_effect=[df1, df2]
    )
    out = CninfoNoticeSource().fetch_recent(["600563", "601127"], lookback_days=7)
    assert len(out) == 2


def test_all_symbols_failure_raises(mocker):
    from exceptions import DataSourceError

    mocker.patch(
        "sources.cninfo.ak.stock_zh_a_disclosure_report_cninfo",
        side_effect=Exception("boom"),
    )
    with pytest.raises(DataSourceError):
        CninfoNoticeSource().fetch_recent(["601127"], lookback_days=7)


def test_partial_symbol_failure_continues(mocker):
    df_ok = _df([["600563", "法拉电子", "公告A", "2026-07-10", "http://x/1"]])
    mocker.patch(
        "sources.cninfo.ak.stock_zh_a_disclosure_report_cninfo",
        side_effect=[Exception("boom"), df_ok],
    )
    out = CninfoNoticeSource().fetch_recent(["601127", "600563"], lookback_days=7)
    assert len(out) == 1
    assert out[0].code == "600563"


def test_no_data_keyerror_skipped(mocker):
    # 无公告时 akshare 抛 KeyError,应视作"无数据"而非失败,静默跳过
    mocker.patch(
        "sources.cninfo.ak.stock_zh_a_disclosure_report_cninfo",
        side_effect=KeyError("None of [...] are in the [columns]"),
    )
    out = CninfoNoticeSource().fetch_recent(["600563"], lookback_days=7)
    assert out == []

import pandas as pd
import pytest

from sources.eastmoney import EastMoneyNoticeSource

_COLS = ["代码", "名称", "标题", "类型", "日期", "网址"]


def _df(rows):
    return pd.DataFrame(rows, columns=_COLS)


def test_filters_watchlist(mocker):
    df = _df(
        [
            ["600519", "茅台", "公告A", "类型", "2026-07-10", "http://a/AN1"],
            ["000001", "平安", "公告B", "类型", "2026-07-10", "http://b/AN2"],
        ]
    )
    mocker.patch("sources.eastmoney.ak.stock_notice_report", return_value=df)
    out = EastMoneyNoticeSource().fetch_recent(["600519"], lookback_days=0)
    assert len(out) == 1
    assert out[0].code == "600519"
    assert out[0].title == "公告A"
    assert out[0].url == "http://a/AN1"


def test_dedup_across_days(mocker):
    df = _df([["600519", "茅台", "公告A", "t", "2026-07-10", "http://a/AN1"]])
    mocker.patch("sources.eastmoney.ak.stock_notice_report", return_value=df)
    out = EastMoneyNoticeSource().fetch_recent(["600519"], lookback_days=2)  # 3 天同数据
    assert len(out) == 1


def test_all_days_failure_raises(mocker):
    from exceptions import DataSourceError

    mocker.patch("sources.eastmoney.ak.stock_notice_report", side_effect=Exception("boom"))
    with pytest.raises(DataSourceError):
        EastMoneyNoticeSource().fetch_recent(["600519"], lookback_days=0)


def test_partial_day_failure_continues(mocker):
    df = _df([["600519", "茅台", "公告A", "t", "2026-07-10", "http://a/AN1"]])
    mocker.patch(
        "sources.eastmoney.ak.stock_notice_report",
        side_effect=[Exception("boom"), df, df],
    )
    out = EastMoneyNoticeSource().fetch_recent(["600519"], lookback_days=2)
    assert len(out) == 1
    assert out[0].title == "公告A"


def test_empty_watchlist_matches_nothing(mocker):
    df = _df([["600519", "茅台", "公告A", "t", "2026-07-10", "http://a/AN1"]])
    mocker.patch("sources.eastmoney.ak.stock_notice_report", return_value=df)
    out = EastMoneyNoticeSource().fetch_recent(["000001"], lookback_days=0)
    assert out == []

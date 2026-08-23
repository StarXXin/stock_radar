import config
import title_rules
from models import Summary


def test_routine_title_matches_default():
    assert title_rules.is_routine_title("关于召开2025年年度股东大会的通知")
    assert title_rules.is_routine_title("关于股份回购进展公告")
    assert title_rules.is_routine_title("投资者关系活动记录表")


def test_non_routine_not_matched():
    assert not title_rules.is_routine_title("关于签订重大合同的公告")
    assert not title_rules.is_routine_title("关于控股股东减持股份的公告")
    assert not title_rules.is_routine_title("关于回购公司股份的公告")


def test_try_routine_summary_returns_low(monkeypatch):
    monkeypatch.setattr(config, "ROUTINE_TITLE_FILTER", True)
    s = title_rules.try_routine_summary("关于召开股东大会的通知")
    assert isinstance(s, Summary)
    assert s.importance == "低"
    assert s.content_source == "rule"
    assert "未调用AI" in s.summary


def test_try_routine_summary_disabled(monkeypatch):
    monkeypatch.setattr(config, "ROUTINE_TITLE_FILTER", False)
    assert title_rules.try_routine_summary("关于召开股东大会的通知") is None


def test_try_routine_summary_miss_returns_none(monkeypatch):
    monkeypatch.setattr(config, "ROUTINE_TITLE_FILTER", True)
    assert title_rules.try_routine_summary("关于中标的公告") is None


def test_custom_patterns_override_default():
    assert title_rules.is_routine_title("某某特别提示", patterns=[r"特别提示"])
    assert not title_rules.is_routine_title(
        "关于召开股东大会的通知", patterns=[r"特别提示"]
    )

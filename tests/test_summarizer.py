import json

import pytest

from exceptions import SummarizeError
from models import Summary
from summarizer import Summarizer


def _client_returning(content, mocker):
    client = mocker.Mock()
    message = mocker.Mock()
    message.content = content
    choice = mocker.Mock()
    choice.message = message
    resp = mocker.Mock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp
    return client


def test_summarize_parses_json(mocker, sample_notice):
    payload = json.dumps(
        {
            "importance": "高",
            "sentiment": "利好",
            "summary": "回购公告",
            "key_points": ["回购金额5亿", "用于注销"],
        }
    )
    out = Summarizer(client=_client_returning(payload, mocker)).summarize(sample_notice)
    assert isinstance(out, Summary)
    assert out.importance == "高"
    assert out.sentiment == "利好"
    assert out.summary == "回购公告"
    assert out.key_points == ["回购金额5亿", "用于注销"]
    assert out.content_source == "title"  # sample_notice 无正文


def test_key_points_coerced_when_not_list(mocker, sample_notice):
    payload = json.dumps(
        {"importance": "中", "sentiment": "中性", "summary": "x", "key_points": "单条要点"}
    )
    out = Summarizer(client=_client_returning(payload, mocker)).summarize(sample_notice)
    assert out.key_points == ["单条要点"]


def test_key_points_optional(mocker, sample_notice):
    payload = json.dumps({"importance": "低", "sentiment": "关注", "summary": "x"})
    out = Summarizer(client=_client_returning(payload, mocker)).summarize(sample_notice)
    assert out.key_points == []


def test_marks_content_source(mocker, sample_notice):
    sample_notice.content = "关键正文"
    payload = json.dumps({"importance": "中", "sentiment": "中性", "summary": "x"})
    out = Summarizer(client=_client_returning(payload, mocker)).summarize(sample_notice)
    assert out.content_source == "content"


def test_truncates_content(mocker, sample_notice):
    sample_notice.content = "A" * 5000
    client = _client_returning(
        json.dumps({"importance": "低", "sentiment": "中性", "summary": "x"}), mocker
    )
    Summarizer(client=client).summarize(sample_notice)
    user_msg = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "A" * 3000 in user_msg
    assert "A" * 3001 not in user_msg


def test_bad_json_raises(mocker, sample_notice):
    with pytest.raises(SummarizeError):
        Summarizer(client=_client_returning("not json", mocker)).summarize(sample_notice)


def test_missing_key_raises(mocker, sample_notice):
    payload = json.dumps({"importance": "高"})  # 缺 sentiment/summary
    with pytest.raises(SummarizeError):
        Summarizer(client=_client_returning(payload, mocker)).summarize(sample_notice)


def test_api_error_raises(mocker, sample_notice):
    client = mocker.Mock()
    client.chat.completions.create.side_effect = RuntimeError("boom")
    with pytest.raises(SummarizeError):
        Summarizer(client=client).summarize(sample_notice)


def test_passes_timeout_to_create(mocker, sample_notice):
    client = _client_returning(
        json.dumps({"importance": "低", "sentiment": "中性", "summary": "x"}), mocker
    )
    Summarizer(client=client, timeout=9.5).summarize(sample_notice)
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["timeout"] == 9.5

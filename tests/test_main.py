"""main.run 集成测试:全 mock 外部组件,覆盖六步编排与降级路径。"""


import pytest

import main
from models import Notice, Summary


def _notice(code="600519", title="关于回购公司股份的公告", date="2026-07-10") -> Notice:
    return Notice(
        code=code,
        name="贵州茅台",
        title=title,
        date=date,
        url=f"https://data.eastmoney.com/notices/detail/{code}/AN202607101234567890.html",
    )


@pytest.fixture
def patched_config(mocker, tmp_path):
    """隔离配置:临时目录存储、单股、无正文抓取(简化编排路径)。"""
    mocker.patch.object(main.config, "WATCHLIST_CODES", ["600519"])
    mocker.patch.object(main.config, "DEEPSEEK_API_KEY", "test-key")
    mocker.patch.object(main.config, "DB_PATH", tmp_path / "pushed.db")
    mocker.patch.object(main.config, "FETCH_CONTENT", False)
    mocker.patch.object(main.config, "RETENTION_DAYS", 0)
    mocker.patch.object(main, "setup_logging")


@pytest.fixture
def mock_llm(mocker):
    """Summarizer.summarize 替身为高重要性摘要;返回 mock 以便断言调用。"""
    m = mocker.patch.object(
        main.Summarizer,
        "summarize",
        return_value=Summary(
            importance="高",
            sentiment="利好",
            summary="回购公告",
            key_points=[],
            content_source="title",
        ),
    )
    return m


# --- 正常流程 ---


def test_run_happy_path(patched_config, mocker, mock_llm):
    source = mocker.patch.object(
        main, "get_source"
    ).return_value
    source.fetch_recent.return_value = [_notice()]
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")

    main.run()

    mock_llm.assert_called_once()
    assert notify.call_count == 1
    args = notify.call_args.args
    assert "1 条新公告" in args[0]
    assert "回购" in args[1]
    # 已标记推送
    store = main.Store()
    assert store.is_new(_notice().id) is False


def test_run_no_new_notices(patched_config, mocker, mock_llm):
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = [_notice()]
    # 先标记已处理 → 第二轮无新公告
    main.Store().mark_pushed(_notice())
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")

    main.run()

    mock_llm.assert_not_called()
    notify.assert_not_called()


def test_run_low_importance_filtered_and_marked(patched_config, mocker):
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = [_notice(title="关于召开股东大会的通知")]
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")
    summarize = mocker.patch.object(main.Summarizer, "summarize")

    main.run()  # 例行标题预滤命中 → 低重要性 → 不推送

    summarize.assert_not_called()  # 预滤跳过 AI
    notify.assert_not_called()
    assert main.Store().is_new(_notice(title="关于召开股东大会的通知").id) is False


# --- 降级/失败路径 ---


def test_run_all_sources_fail_exits(patched_config, mocker, mock_llm):
    mocker.patch.object(main, "_fetch_from_sources", side_effect=main.DataSourceError("网络挂了"))
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")

    main.run()

    mock_llm.assert_not_called()
    notify.assert_not_called()


def test_run_push_failure_does_not_mark(patched_config, mocker):
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = [_notice()]
    mocker.patch.object(
        main.Summarizer,
        "summarize",
        return_value=Summary(importance="高", sentiment="利好", summary="x"),
    )
    mocker.patch.object(
        main.PushPlusNotifier, "notify", side_effect=main.NotifyError("推送超时")
    )

    main.run()

    assert main.Store().is_new(_notice().id) is True  # 未标记,下次重试


def test_run_multi_page_partial_failure_marks_only_pushed(patched_config, mocker):
    mocker.patch.object(main.render, "paginate_notices")  # 强制两页
    notices = [_notice(date="2026-07-10"), _notice(date="2026-07-11")]
    main.render.paginate_notices.return_value = [notices[:1], notices[1:]]
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = notices
    mocker.patch.object(
        main.Summarizer,
        "summarize",
        return_value=Summary(importance="高", sentiment="利好", summary="x"),
    )
    # 第 1 页成功,第 2 页失败
    mocker.patch.object(
        main.PushPlusNotifier,
        "notify",
        side_effect=[None, main.NotifyError("第2页失败")],
    )

    main.run()

    store = main.Store()
    assert store.is_new(notices[0].id) is False  # 第1页已标记
    assert store.is_new(notices[1].id) is True   # 第2页未标记


def test_run_summarize_failure_pushes_fallback(patched_config, mocker):
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = [_notice()]
    mocker.patch.object(
        main.Summarizer, "summarize", side_effect=main.SummarizeError("LLM 挂了")
    )
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")

    main.run()

    notify.assert_called_once()  # 兜底'中'仍达阈值,照常推送
    assert "(摘要失败" in notify.call_args.args[1]


def test_run_empty_watchlist_exits(mocker, tmp_path):
    mocker.patch.object(main.config, "WATCHLIST_CODES", [])
    mocker.patch.object(main, "setup_logging")
    get_source = mocker.patch.object(main, "get_source")

    main.run()

    get_source.assert_not_called()


def test_run_missing_api_key_exits(mocker, tmp_path):
    mocker.patch.object(main.config, "WATCHLIST_CODES", ["600519"])
    mocker.patch.object(main.config, "DEEPSEEK_API_KEY", "")
    mocker.patch.object(main, "setup_logging")
    get_source = mocker.patch.object(main, "get_source")

    main.run()

    get_source.assert_not_called()


def test_run_alert_sent_on_fetch_failure(mocker, tmp_path):
    mocker.patch.object(main.config, "WATCHLIST_CODES", ["600519"])
    mocker.patch.object(main.config, "DEEPSEEK_API_KEY", "k")
    mocker.patch.object(main.config, "DB_PATH", tmp_path / "pushed.db")
    mocker.patch.object(main.config, "FETCH_CONTENT", False)
    mocker.patch.object(main.config, "RETENTION_DAYS", 0)
    mocker.patch.object(main.config, "ALERT_ON_ERROR", True)
    mocker.patch.object(main.config, "PUSHPLUS_TOKEN", "tok")
    mocker.patch.object(main, "setup_logging")
    mocker.patch.object(main, "_fetch_from_sources", side_effect=main.DataSourceError("全挂"))
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")

    main.run()

    assert any("告警" in c.args[0] for c in notify.call_args_list)


# --- _fetch_from_sources 多源合并 ---


def test_fetch_from_sources_merges_and_dedups(mocker):
    src_a = mocker.Mock()
    src_a.fetch_recent.return_value = [_notice(), _notice()]  # 同一条重复
    src_b = mocker.Mock()
    other = _notice(code="000001")
    src_b.fetch_recent.return_value = [other]
    mocker.patch.object(main, "get_source", side_effect=[src_a, src_b])
    mocker.patch.object(main.config, "DATA_SOURCE", "eastmoney,cninfo")

    out = main._fetch_from_sources()

    assert len(out) == 2  # (code,date,title) 去重后


def test_fetch_from_sources_partial_failure_continues(mocker):
    ok_src = mocker.Mock()
    ok_src.fetch_recent.return_value = [_notice()]
    bad_src = mocker.Mock()
    bad_src.fetch_recent.side_effect = main.DataSourceError("这个源挂了")
    mocker.patch.object(main, "get_source", side_effect=[bad_src, ok_src])
    mocker.patch.object(main.config, "DATA_SOURCE", "eastmoney,cninfo")

    out = main._fetch_from_sources()

    assert len(out) == 1


def test_fetch_from_sources_all_fail_raises(mocker):
    bad = mocker.Mock()
    bad.fetch_recent.side_effect = main.DataSourceError("挂")
    mocker.patch.object(main, "get_source", side_effect=[bad])
    mocker.patch.object(main.config, "DATA_SOURCE", "eastmoney")

    with pytest.raises(main.DataSourceError):
        main._fetch_from_sources()

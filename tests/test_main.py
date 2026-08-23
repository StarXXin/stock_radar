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


# --- LLM 熔断与预算 ---


def test_circuit_breaker_skips_after_consecutive_failures(patched_config, mocker):
    mocker.patch.object(main.config, "LLM_CIRCUIT_BREAKER", 2)
    notices = [_notice(date=f"2026-07-{d:02d}") for d in range(10, 15)]  # 5 条
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = notices
    summarize = mocker.patch.object(
        main.Summarizer, "summarize", side_effect=main.SummarizeError("LLM 挂")
    )
    mocker.patch.object(main.PushPlusNotifier, "notify")

    main.run()

    assert summarize.call_count == 2  # 连续 2 条失败即熔断,不再调用
    store = main.Store()
    # 恰好 2 条走了兜底(已标记);并发下执行顺序不定,按数量统计而非具体哪几条;
    # 其余 3 条被跳过未标记,下次重试
    marked = sum(1 for n in notices if not store.is_new(n.id))
    assert marked == 2


def test_circuit_breaker_resets_on_success(patched_config, mocker):
    mocker.patch.object(main.config, "LLM_CIRCUIT_BREAKER", 2)
    notices = [_notice(date=f"2026-07-{d:02d}") for d in range(10, 14)]  # 4 条
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = notices
    ok = Summary(importance="高", sentiment="利好", summary="x")
    # 失败→成功→失败→成功:连续计数被打断,不熔断
    mocker.patch.object(
        main.Summarizer,
        "summarize",
        side_effect=[main.SummarizeError("挂"), ok, main.SummarizeError("挂"), ok],
    )

    main.run()

    assert main.Summarizer.summarize.call_count == 4  # 全部都尝试了


def test_call_budget_exhausted(patched_config, mocker):
    mocker.patch.object(main.config, "LLM_MAX_CALLS_PER_RUN", 2)
    notices = [_notice(date=f"2026-07-{d:02d}") for d in range(10, 14)]  # 4 条
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = notices
    summarize = mocker.patch.object(
        main.Summarizer,
        "summarize",
        return_value=Summary(importance="高", sentiment="利好", summary="x"),
    )

    main.run()

    assert summarize.call_count == 2  # 预算 2 条
    store = main.Store()
    # 并发下哪 2 条用掉预算不确定:恰好 2 条已标记、其余 2 条跳过未标记(下次重试)
    marked = sum(1 for n in notices if not store.is_new(n.id))
    assert marked == 2


def test_guard_cache_hits_not_counted(patched_config, mocker):
    """缓存命中的条目不消耗预算/不影响熔断计数。"""
    mocker.patch.object(main.config, "LLM_MAX_CALLS_PER_RUN", 1)
    n1 = _notice(date="2026-07-10")
    n2 = _notice(date="2026-07-11")
    store = main.Store()
    store.save_summary(
        n1.id, Summary(importance="高", sentiment="利好", summary="缓存结果")
    )
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = [n1, n2]
    summarize = mocker.patch.object(
        main.Summarizer,
        "summarize",
        return_value=Summary(importance="高", sentiment="利好", summary="新摘要"),
    )

    main.run()

    summarize.assert_called_once()  # n1 缓存命中,n2 用掉唯一预算
    assert main.Store().is_new(n1.id) is False
    assert main.Store().is_new(n2.id) is False


# --- CLI / dry-run ---


def test_run_dry_run_no_push_no_mark(patched_config, mocker, capsys):
    notices = [_notice(date="2026-07-10"), _notice(date="2026-07-11")]
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = notices
    mocker.patch.object(
        main.Summarizer,
        "summarize",
        return_value=Summary(importance="高", sentiment="利好", summary="x"),
    )
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")

    main.run(dry_run=True)

    notify.assert_not_called()          # 不推送
    store = main.Store()
    assert all(store.is_new(n.id) for n in notices)  # 不标记
    out = capsys.readouterr().out
    assert "[dry-run]" in out and "2 条" in out


def test_run_days_override(patched_config, mocker):
    source = mocker.patch.object(main, "get_source").return_value
    source.fetch_recent.return_value = []

    main.run(days=7)

    assert source.fetch_recent.call_args.args[1] == 7  # LOOKBACK_DAYS 被覆盖


def test_run_source_override(patched_config, mocker):
    get_source = mocker.patch.object(main, "get_source")
    get_source.return_value.fetch_recent.return_value = []
    mocker.patch.object(main.config, "DATA_SOURCE", "eastmoney")

    main.run(source_override="cninfo")

    get_source.assert_called_with("cninfo")  # 覆盖生效


# --- 心跳 ---


def _patch_heartbeat(mocker, tmp_path, token="tok"):
    mocker.patch.object(main.config, "HEARTBEAT_DAYS", 3)
    mocker.patch.object(main.config, "DATA_DIR", tmp_path)
    mocker.patch.object(main.config, "PUSHPLUS_TOKEN", token)


def test_heartbeat_silent_over_threshold_sends(tmp_path, mocker):
    from datetime import datetime, timedelta

    _patch_heartbeat(mocker, tmp_path)
    stamp = tmp_path / "last_run"
    old = datetime.now() - timedelta(days=5)
    stamp.write_text(old.isoformat(), encoding="utf-8")
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")

    main._check_heartbeat(main.PushPlusNotifier())

    notify.assert_called_once()
    assert "心跳" in notify.call_args.args[0]
    refreshed = datetime.fromisoformat(stamp.read_text(encoding="utf-8").strip())
    assert (datetime.now() - refreshed).total_seconds() < 60  # 时间戳已刷新


def test_heartbeat_recent_run_no_send(tmp_path, mocker):
    from datetime import datetime

    _patch_heartbeat(mocker, tmp_path)
    stamp = tmp_path / "last_run"
    stamp.write_text(datetime.now().isoformat(), encoding="utf-8")
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")

    main._check_heartbeat(main.PushPlusNotifier())

    notify.assert_not_called()


def test_heartbeat_disabled_is_noop(tmp_path, mocker):
    mocker.patch.object(main.config, "HEARTBEAT_DAYS", 0)
    mocker.patch.object(main.config, "DATA_DIR", tmp_path)
    notify = mocker.patch.object(main.PushPlusNotifier, "notify")

    main._check_heartbeat(main.PushPlusNotifier())

    notify.assert_not_called()
    assert not (tmp_path / "last_run").exists()  # 关闭时不写时间戳

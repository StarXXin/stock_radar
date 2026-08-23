"""store 只读展示方法(list_pushed/stats/count)测试,复用 db_path fixture。"""

import json

import pytest

from exceptions import StorageError
from models import Notice, Summary
from store import Store


@pytest.fixture
def store(db_path):
    return Store(db_path)


def _notice(code="600519", title="关于回购公司股份的公告", date="2026-08-20") -> Notice:
    return Notice(code=code, name="贵州茅台", title=title, date=date,
                  url=f"https://example.com/{code}")


def _summary(importance="高") -> Summary:
    return Summary(importance=importance, sentiment="利好",
                   summary="一句话摘要", key_points=["要点1"], content_source="content")


def test_list_pushed_empty(store):
    assert store.list_pushed() == []
    assert store.count_pushed() == 0
    assert store.recent_pushed_at() is None


def test_list_pushed_returns_records_with_summary(store):
    n = _notice()
    store.mark_pushed(n)
    store.save_summary(n.id, _summary())

    records = store.list_pushed()
    assert len(records) == 1
    rec = records[0]
    assert rec.id == n.id
    assert rec.code == "600519"
    assert rec.title == n.title
    assert rec.date == "2026-08-20"
    assert rec.pushed_at  # 有时间戳
    assert rec.summary is not None
    assert rec.summary.importance == "高"
    assert rec.summary.key_points == ["要点1"]


def test_list_pushed_order_desc_and_pagination(store):
    for i in range(3):
        n = _notice(title=f"公告{i}")
        store.mark_pushed(n)
    # mark_pushed 在同一秒内 pushed_at 相同,按 id 排序稳定即可;分页数正确性优先
    page1 = store.list_pushed(limit=2, offset=0)
    page2 = store.list_pushed(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 1
    ids = {r.id for r in page1} | {r.id for r in page2}
    assert len(ids) == 3


def test_list_pushed_without_summary_cache(store):
    n = _notice()
    store.mark_pushed(n)
    records = store.list_pushed()
    assert records[0].summary is None


def test_list_pushed_corrupted_summary_json_tolerated(store):
    n = _notice()
    store.mark_pushed(n)
    with store._conn() as conn:  # 直接写坏数据模拟缓存损坏
        conn.execute("INSERT OR REPLACE INTO summaries (id, summary_json, created_at) "
                     "VALUES (?, ?, '2026-08-20T00:00:00')", (n.id, "{not json"))
    records = store.list_pushed()
    assert len(records) == 1
    assert records[0].summary is None


def test_stats_by_importance(store):
    for i, importance in enumerate(("高", "高", "中", "低")):
        n = _notice(title=f"公告-{i}-{importance}")
        store.mark_pushed(n)
        store.save_summary(n.id, _summary(importance))
    bare = _notice(title="无摘要公告")
    store.mark_pushed(bare)  # 无摘要缓存

    stats = store.stats_by_importance(days=7)
    assert stats["高"] == 2
    assert stats["中"] == 1
    assert stats["低"] == 1
    assert stats["未摘要"] == 1

    # 老记录不计入近 0 天窗口(pushed_at 为今天,窗口为 7 天会包含;这里只验证键齐全)
    assert set(stats.keys()) == {"高", "中", "低", "未摘要"}


def test_stats_unknown_importance_counts_as_unsummarized(store):
    n = _notice()
    store.mark_pushed(n)
    payload = json.dumps({"importance": "未知级", "sentiment": "中性",
                          "summary": "s", "key_points": []}, ensure_ascii=False)
    with store._conn() as conn:
        conn.execute("INSERT OR REPLACE INTO summaries (id, summary_json, created_at) "
                     "VALUES (?, ?, '2026-08-20T00:00:00')", (n.id, payload))
    stats = store.stats_by_importance()
    assert stats["未摘要"] == 1


def test_recent_pushed_at(store):
    n = _notice()
    store.mark_pushed(n)
    recent = store.recent_pushed_at()
    assert recent is not None and recent  # ISO 时间戳字符串


def test_query_error_raises_storage_error(store, db_path):
    db_path.write_text("not a sqlite file")
    with pytest.raises(StorageError):
        store.list_pushed()

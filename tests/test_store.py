import json
import sqlite3
from datetime import datetime, timedelta

from models import Summary
from store import Store


def test_new_then_marked(db_path, sample_notice):
    store = Store(db_path=db_path)
    assert store.is_new(sample_notice.id) is True
    store.mark_pushed(sample_notice)
    assert store.is_new(sample_notice.id) is False


def test_mark_idempotent(db_path, sample_notice):
    store = Store(db_path=db_path)
    store.mark_pushed(sample_notice)
    store.mark_pushed(sample_notice)  # INSERT OR IGNORE,不报错
    assert store.is_new(sample_notice.id) is False


def test_indexes_created(db_path, sample_notice):
    store = Store(db_path=db_path)
    store.mark_pushed(sample_notice)
    conn = sqlite3.connect(db_path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    assert "idx_pushed_code" in names
    assert "idx_pushed_date" in names


def _sample_summary() -> Summary:
    return Summary(
        importance="高",
        sentiment="利好",
        summary="中标合同",
        key_points=["合同额5亿", "占营收20%"],
        content_source="content",
    )


def test_summary_roundtrip(db_path, sample_notice):
    store = Store(db_path=db_path)
    assert store.get_summary(sample_notice.id) is None  # 未缓存
    s = _sample_summary()
    store.save_summary(sample_notice.id, s)
    out = store.get_summary(sample_notice.id)
    assert out == s


def test_summary_overwrite(db_path, sample_notice):
    store = Store(db_path=db_path)
    first = Summary(importance="中", sentiment="中性", summary="v1")
    second = _sample_summary()
    store.save_summary(sample_notice.id, first)
    store.save_summary(sample_notice.id, second)
    assert store.get_summary(sample_notice.id) == second


def test_corrupted_cache_returns_none(db_path, sample_notice):
    store = Store(db_path=db_path)
    assert store.get_summary(sample_notice.id) is None  # 触发建表
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO summaries (id, summary_json, created_at) VALUES (?, ?, 'x')",
            (sample_notice.id, "not-json"),
        )
    assert store.get_summary(sample_notice.id) is None


def test_saved_json_shape(db_path, sample_notice):
    store = Store(db_path=db_path)
    store.save_summary(sample_notice.id, _sample_summary())
    with sqlite3.connect(db_path) as conn:
        raw = conn.execute(
            "SELECT summary_json FROM summaries WHERE id = ?", (sample_notice.id,)
        ).fetchone()[0]
    data = json.loads(raw)
    assert data["importance"] == "高"
    assert data["key_points"] == ["合同额5亿", "占营收20%"]
    assert data["content_source"] == "content"


def _backdate(store, notice_id, days):
    old = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with sqlite3.connect(store._db_path) as conn:
        conn.execute("UPDATE pushed SET pushed_at = ? WHERE id = ?", (old, notice_id))
        conn.execute("UPDATE summaries SET created_at = ? WHERE id = ?", (old, notice_id))


def test_cleanup_removes_old_rows_only(db_path, sample_notice):
    store = Store(db_path=db_path)
    store.mark_pushed(sample_notice)
    store.save_summary(sample_notice.id, _sample_summary())
    # 手工把行改成 100 天前
    old = (datetime.now() - timedelta(days=100)).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE pushed SET pushed_at = ?", (old,))
        conn.execute("UPDATE summaries SET created_at = ?", (old,))
    deleted = store.cleanup(retention_days=90)
    assert deleted == 2
    assert store.is_new(sample_notice.id) is True
    assert store.get_summary(sample_notice.id) is None


def test_cleanup_keeps_recent_rows(db_path, sample_notice):
    store = Store(db_path=db_path)
    store.mark_pushed(sample_notice)
    store.save_summary(sample_notice.id, _sample_summary())
    assert store.cleanup(retention_days=90) == 0
    assert store.is_new(sample_notice.id) is False
    assert store.get_summary(sample_notice.id) is not None


def test_cleanup_zero_days_noop(db_path, sample_notice):
    store = Store(db_path=db_path)
    store.mark_pushed(sample_notice)
    assert store.cleanup(retention_days=0) == 0
    assert store.is_new(sample_notice.id) is False


def test_summary_cache_version_mismatch_invalidates(db_path, sample_notice, mocker):
    """版本号变化后旧缓存视为未命中(调 prompt/KEYWORDS 后 +1 即可全量失效)。"""
    store = Store(db_path=db_path)
    store.save_summary(sample_notice.id, _sample_summary())
    assert store.get_summary(sample_notice.id) is not None  # 版本一致命中
    mocker.patch("store.config.SUMMARY_CACHE_VERSION", 2)
    assert store.get_summary(sample_notice.id) is None  # 版本不匹配 → 重新生成
    # 重新保存后再次命中
    store.save_summary(sample_notice.id, _sample_summary())
    assert store.get_summary(sample_notice.id) is not None


def test_summary_cache_legacy_entry_without_version(db_path, sample_notice):
    """无 cache_version 字段的旧记录视为不匹配。"""
    import sqlite3 as sq

    store = Store(db_path=db_path)
    assert store.get_summary(sample_notice.id) is None  # 触发建表
    with sq.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO summaries (id, summary_json, created_at) VALUES (?, ?, 'x')",
            (sample_notice.id, '{"importance":"高","sentiment":"利好","summary":"旧"}'),
        )
    assert store.get_summary(sample_notice.id) is None

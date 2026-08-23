import json
import sqlite3

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

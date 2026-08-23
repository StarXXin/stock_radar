import sqlite3

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

"""本地去重存储(SQLite)。构造可注入 db_path,便于测试隔离。"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import config
from exceptions import StorageError
from models import Notice

logger = logging.getLogger(__name__)


class Store:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else config.DB_PATH

    def _conn(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pushed ("
            "id TEXT PRIMARY KEY, code TEXT, title TEXT, date TEXT, pushed_at TEXT)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pushed_code ON pushed(code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pushed_date ON pushed(date)")
        return conn

    def is_new(self, notice_id: str) -> bool:
        try:
            with self._conn() as conn:
                cur = conn.execute("SELECT 1 FROM pushed WHERE id = ?", (notice_id,))
                return cur.fetchone() is None
        except sqlite3.Error as e:
            raise StorageError(f"查询去重失败: {e}") from e

    def mark_pushed(self, notice: Notice) -> None:
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO pushed (id, code, title, date, pushed_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        notice.id,
                        notice.code,
                        notice.title,
                        notice.date,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
        except sqlite3.Error as e:
            raise StorageError(f"写入已推送记录失败: {e}") from e

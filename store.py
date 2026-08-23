"""本地去重存储(SQLite)。构造可注入 db_path,便于测试隔离。"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import config
from exceptions import StorageError
from models import Notice, PushedRecord, Summary

logger = logging.getLogger(__name__)


class Store:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else config.DB_PATH

    def _conn(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        # webapp 读与 CLI 子进程写可能并发:写锁被占时等待而非立刻报错
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pushed ("
            "id TEXT PRIMARY KEY, code TEXT, title TEXT, date TEXT, pushed_at TEXT)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pushed_code ON pushed(code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pushed_date ON pushed(date)")
        # 摘要缓存:按 notice id 存 AI 结果 JSON,重跑/重试时避免重复调用 LLM
        conn.execute(
            "CREATE TABLE IF NOT EXISTS summaries ("
            "id TEXT PRIMARY KEY, summary_json TEXT NOT NULL, created_at TEXT)"
        )
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

    def get_summary(self, notice_id: str) -> Summary | None:
        """按 id 取缓存的 AI 摘要;无记录/版本不匹配/数据损坏返回 None(重新摘要)。

        版本校验:调 KEYWORDS/prompt 后调 SUMMARY_CACHE_VERSION +1 即可让旧缓存全量失效。
        """
        try:
            with self._conn() as conn:
                cur = conn.execute(
                    "SELECT summary_json FROM summaries WHERE id = ?", (notice_id,)
                )
                row = cur.fetchone()
        except sqlite3.Error as e:
            raise StorageError(f"查询摘要缓存失败: {e}") from e
        if row is None:
            return None
        try:
            data = json.loads(row[0])
            if int(data.get("cache_version") or 0) != config.SUMMARY_CACHE_VERSION:
                logger.info(
                    "摘要缓存版本不匹配(存=%s 现=%s),重新生成 id=%s",
                    data.get("cache_version"), config.SUMMARY_CACHE_VERSION, notice_id,
                )
                return None
            return Summary(
                importance=str(data["importance"]),
                sentiment=str(data["sentiment"]),
                summary=str(data["summary"]),
                key_points=[str(p) for p in data.get("key_points") or []],
                content_source=str(data.get("content_source") or "title"),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("摘要缓存损坏,忽略重新生成 id=%s: %s", notice_id, e)
            return None

    def save_summary(self, notice_id: str, summary: Summary) -> None:
        payload = json.dumps(
            {
                "importance": summary.importance,
                "sentiment": summary.sentiment,
                "summary": summary.summary,
                "key_points": summary.key_points,
                "content_source": summary.content_source,
                "cache_version": config.SUMMARY_CACHE_VERSION,
            },
            ensure_ascii=False,
        )
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO summaries (id, summary_json, created_at) "
                    "VALUES (?, ?, ?)",
                    (
                        notice_id,
                        payload,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
        except sqlite3.Error as e:
            raise StorageError(f"写入摘要缓存失败: {e}") from e

    # ---- 以下只读方法供 webapp 展示使用,不影响 CLI 流程 ----

    @staticmethod
    def _parse_summary_raw(raw: str | None) -> Summary | None:
        """解析摘要缓存原始 JSON(忽略 cache_version,历史可见性优先);损坏返回 None。"""
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return Summary(
                importance=str(data["importance"]),
                sentiment=str(data["sentiment"]),
                summary=str(data["summary"]),
                key_points=[str(p) for p in data.get("key_points") or []],
                content_source=str(data.get("content_source") or "title"),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
            logger.warning("历史摘要数据损坏,展示为空: %s", e)
            return None

    def list_pushed(self, limit: int = 50, offset: int = 0) -> list[PushedRecord]:
        """按 pushed_at 倒序分页取已推送记录,LEFT JOIN 摘要缓存。展示场景容错不抛。"""
        try:
            with self._conn() as conn:
                cur = conn.execute(
                    "SELECT p.id, p.code, p.title, p.date, p.pushed_at, s.summary_json "
                    "FROM pushed p LEFT JOIN summaries s ON p.id = s.id "
                    "ORDER BY p.pushed_at DESC, p.id LIMIT ? OFFSET ?",
                    (limit, offset),
                )
                rows = cur.fetchall()
        except sqlite3.Error as e:
            raise StorageError(f"查询已推送记录失败: {e}") from e
        return [
            PushedRecord(
                id=row[0], code=row[1] or "", title=row[2] or "",
                date=row[3] or "", pushed_at=row[4] or "",
                summary=self._parse_summary_raw(row[5]),
            )
            for row in rows
        ]

    def count_pushed(self) -> int:
        try:
            with self._conn() as conn:
                cur = conn.execute("SELECT COUNT(*) FROM pushed")
                return int(cur.fetchone()[0])
        except sqlite3.Error as e:
            raise StorageError(f"统计已推送条数失败: {e}") from e

    def stats_by_importance(self, days: int = 7) -> dict[str, int]:
        """近 N 天(按 pushed_at)按重要性计数;摘要缺失计'未摘要'。"""
        cutoff_date = (datetime.now() - timedelta(days=days)).date().isoformat()
        try:
            with self._conn() as conn:
                cur = conn.execute(
                    "SELECT s.summary_json FROM pushed p "
                    "LEFT JOIN summaries s ON p.id = s.id "
                    "WHERE p.pushed_at >= ?", (cutoff_date,)
                )
                rows = cur.fetchall()
        except sqlite3.Error as e:
            raise StorageError(f"统计重要性分布失败: {e}") from e
        stats: dict[str, int] = {"高": 0, "中": 0, "低": 0, "未摘要": 0}
        for (raw,) in rows:
            summary = self._parse_summary_raw(raw)
            importance = summary.importance if summary is not None else "未摘要"
            if importance not in stats:
                importance = "未摘要"
            stats[importance] += 1
        return stats

    def recent_pushed_at(self) -> str | None:
        try:
            with self._conn() as conn:
                cur = conn.execute("SELECT MAX(pushed_at) FROM pushed")
                row = cur.fetchone()
                return str(row[0]) if row and row[0] else None
        except sqlite3.Error as e:
            raise StorageError(f"查询最近推送时间失败: {e}") from e

    def cleanup(self, retention_days: int) -> int:
        """删除超过保留天数的已推送记录与摘要缓存,返回删除行数。0 行也安全。"""
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat(
            timespec="seconds"
        )
        try:
            with self._conn() as conn:
                cur1 = conn.execute("DELETE FROM pushed WHERE pushed_at < ?", (cutoff,))
                cur2 = conn.execute(
                    "DELETE FROM summaries WHERE created_at < ?", (cutoff,)
                )
                deleted = cur1.rowcount + cur2.rowcount
            if deleted:
                logger.info("清理过期存储 %d 行(保留 %d 天)", deleted, retention_days)
            return deleted
        except sqlite3.Error as e:
            raise StorageError(f"清理过期存储失败: {e}") from e

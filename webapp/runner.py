"""手动触发运行管理器:子进程执行 main.py,环形缓冲日志,单例锁防并发。

用 `sys.executable + main.py` 而非 `uv run`:webapp 本身经 `uv run` 启动,
sys.executable 必然是正确的项目 venv Python,与定时任务行为等价。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

_STATUS_IDLE = "idle"
_STATUS_RUNNING = "running"
_STATUS_SUCCESS = "success"
_STATUS_FAILED = "failed"


class RunManager:
    """同一时刻最多一个雷达运行;输出行存内存环形缓冲供前端增量轮询。"""

    def __init__(self, project_root: Path, buffer_size: int = 2000) -> None:
        self._root = project_root
        self._buf: deque[str] = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._status = _STATUS_IDLE
        self._exit_code: int | None = None
        self._started_at: float | None = None
        self._finished_at: float | None = None
        # 环形缓冲丢弃旧行后,全局行号仍单调递增,前端据此增量拉取;
        # _base_offset = 缓冲内第一行的全局行号(每次 start 清缓冲后前移)
        self._total_lines = 0
        self._dropped_lines = 0
        self._base_offset = 0

    def _build_command(self, dry_run: bool) -> list[str]:
        cmd = [sys.executable, str(self._root / "main.py")]
        if dry_run:
            cmd.append("--dry-run")
        return cmd

    @property
    def running(self) -> bool:
        with self._lock:
            return self._status == _STATUS_RUNNING

    def start(self, dry_run: bool = False) -> bool:
        """启动一轮运行;已在跑则返回 False(拒绝并发)。"""
        with self._lock:
            if self._status == _STATUS_RUNNING and self._proc is not None \
                    and self._proc.poll() is None:
                return False

            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            win_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

            try:
                self._proc = subprocess.Popen(  # noqa: S603 - 命令为固定路径拼接
                    self._build_command(dry_run),
                    cwd=self._root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=win_flags,  # Windows 隐藏控制台窗口;POSIX 下传 0 无副作用
                )
            except OSError as e:
                logger.error("启动运行失败: %s", e)
                self._clear_buffer()
                self._append_line_locked(f"[错误] 启动失败: {e}")
                self._status = _STATUS_FAILED
                self._exit_code = -1
                return True

            self._status = _STATUS_RUNNING
            self._exit_code = None
            self._started_at = time.time()
            self._finished_at = None
            self._clear_buffer()
            mode = "dry-run" if dry_run else "完整"
            self._append_line_locked(f"▶ 启动{mode}运行 (pid={self._proc.pid})")

        threading.Thread(target=self._watch, args=(self._proc,), daemon=True).start()
        return True

    def _watch(self, proc: subprocess.Popen[bytes]) -> None:
        """后台线程:逐行读子进程合并输出,结束后更新状态。"""
        assert proc.stdout is not None
        try:
            for raw in proc.stdout:
                self._append_line(raw.decode("utf-8", errors="replace").rstrip())
        except (OSError, ValueError) as e:  # 进程被杀/管道异常不致命
            logger.warning("读取运行输出中断: %s", e)
        try:
            code = proc.wait()
        except OSError as e:
            logger.warning("等待运行进程结束失败: %s", e)
            code = -1
        duration = ""
        with self._lock:
            self._exit_code = code
            finished = time.time()
            self._finished_at = finished
            if self._started_at is not None:
                duration = f",耗时 {finished - self._started_at:.0f}s"
            self._status = _STATUS_SUCCESS if code == 0 else _STATUS_FAILED
        self._append_line(f"■ 运行结束:退出码 {code}{duration}")

    # ---- 缓冲与状态 ----
    # 约定:_locked 后缀方法要求调用方已持有 _lock;公开版本自行加锁。

    def _clear_buffer(self) -> None:
        self._buf.clear()
        self._dropped_lines = self._total_lines  # 已有行全部计入丢弃,行号单调不减
        self._base_offset = self._total_lines

    def _append_line(self, line: str) -> None:
        with self._lock:
            self._append_line_locked(line)

    def _append_line_locked(self, line: str) -> None:
        if self._buf.maxlen is not None and len(self._buf) >= self._buf.maxlen:
            self._dropped_lines += 1
        self._buf.append(line)
        self._total_lines += 1

    def lines_since(self, offset: int) -> tuple[list[str], int]:
        """返回 offset 之后的新行与最新全局行号。offset 为 -1 表示从头要全量。

        offset 落在被丢弃的区间时,退化为返回缓冲内全部现存行。
        """
        with self._lock:
            lines = list(self._buf)
            total = self._total_lines
            base = self._base_offset  # 缓冲第一行的全局行号(锁内快照,与 lines 一致)
        if offset < base or offset < 0:
            offset = base
        start = max(0, offset - base)
        return lines[start:], total

    def status(self) -> dict[str, object]:
        with self._lock:
            started = self._started_at
            finished = self._finished_at
            payload: dict[str, object] = {
                "status": self._status,
                "exit_code": self._exit_code,
                "pid": self._proc.pid if (self._proc and self._status == _STATUS_RUNNING) else None,
                "duration_s": (
                    round((finished or time.time()) - started) if started else None
                ),
                "total_lines": self._total_lines,
            }
        return payload

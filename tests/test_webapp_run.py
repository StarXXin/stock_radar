"""RunManager(手动触发运行)测试:fake Popen,无真实子进程。"""

import sys
from typing import Any

import pytest

from webapp.runner import RunManager


class FakePopen:
    """模拟 subprocess.Popen:输出预置行后以指定码退出。"""

    instances: list["FakePopen"] = []
    next_output: list[bytes] = [b"line-1\n", b"line-2\n"]
    next_exit_code = 0
    fail_start = False

    def __init__(self, args: Any, **kwargs: Any) -> None:
        if FakePopen.fail_start:
            raise OSError("boom")
        self.args = args
        self.pid = 12345
        self._lines = list(FakePopen.next_output)
        self.returncode: int | None = None
        FakePopen.instances.append(self)

    stdout = property(lambda self: self)

    def __iter__(self):
        return iter(self._lines)

    def wait(self) -> int:
        self.returncode = FakePopen.next_exit_code
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode


@pytest.fixture
def fake_popen(monkeypatch):
    FakePopen.instances = []
    FakePopen.next_output = [b"line-1\n", b"line-2\n"]
    FakePopen.next_exit_code = 0
    FakePopen.fail_start = False
    monkeypatch.setattr("webapp.runner.subprocess.Popen", FakePopen)
    monkeypatch.setattr("webapp.runner.subprocess.CREATE_NO_WINDOW", 0, raising=False)
    return FakePopen


def _wait_done(manager: RunManager) -> None:
    # start() 的 watcher 线程读的是真实 Popen.stdout;FakePopen 即可同步跑完。
    # 但线程是异步的,轮询等状态落定。
    for _ in range(200):
        if manager.status()["status"] in ("success", "failed"):
            return
        import time
        time.sleep(0.01)
    pytest.fail("运行状态未在超时内落定")


def test_build_command(tmp_path):
    manager = RunManager(tmp_path)
    assert manager._build_command(False) == [
        sys.executable, str(tmp_path / "main.py")
    ]
    assert manager._build_command(True) == [
        sys.executable, str(tmp_path / "main.py"), "--dry-run"
    ]


def test_start_runs_and_records_success(fake_popen, tmp_path):

    manager = RunManager(tmp_path)
    assert manager.start(dry_run=True) is True
    _wait_done(manager)

    proc = fake_popen.instances[0]
    assert proc.args[-1] == "--dry-run"
    status = manager.status()
    assert status["status"] == "success"
    assert status["exit_code"] == 0
    lines, total = manager.lines_since(-1)
    assert "启动dry-run运行" in lines[0] or any("启动" in ln for ln in lines)
    assert any("line-1" in ln for ln in lines)
    assert total >= 3  # 启动行 + 输出2行 + 结束行


def test_start_full_run_command(fake_popen, tmp_path):
    manager = RunManager(tmp_path)
    manager.start(dry_run=False)
    _wait_done(manager)
    assert fake_popen.instances[0].args[-1] != "--dry-run"


def test_concurrent_start_rejected(fake_popen, tmp_path):
    """第一个进程尚未结束时,再次 start 应被拒绝。"""
    import threading

    class HangingPopen(FakePopen):
        def __iter__(self):
            # 阻塞式输出流(模拟进程存活且无新输出),不烧 CPU、线程可常驻(daemon)
            ev = threading.Event()
            ev.wait()
            return iter(())

        def poll(self) -> int | None:
            return None  # 一直活着

    import webapp.runner as runner_mod
    runner_mod.subprocess.Popen = HangingPopen  # type: ignore[assignment]

    manager = RunManager(tmp_path)
    assert manager.start() is True
    assert manager.running is True
    assert manager.start() is False  # 并发拒绝


def test_start_failure_records_failed_state(fake_popen, tmp_path):
    fake_popen.fail_start = True
    manager = RunManager(tmp_path)
    assert manager.start() is True  # start 本身成功返回,状态记为 failed
    assert manager.status()["status"] == "failed"


def test_lines_since_incremental(fake_popen, tmp_path):

    manager = RunManager(tmp_path)
    manager.start()
    _wait_done(manager)
    all_lines, total = manager.lines_since(-1)
    assert len(all_lines) == total
    # 从中间偏移拉取只返回增量
    mid = total - 1
    tail_lines, next_offset = manager.lines_since(mid)
    assert next_offset == total
    assert len(tail_lines) <= 1


def test_exit_code_failure_marked(fake_popen, tmp_path):
    fake_popen.next_exit_code = 3
    manager = RunManager(tmp_path)
    manager.start()
    _wait_done(manager)
    status = manager.status()
    assert status["status"] == "failed"
    assert status["exit_code"] == 3

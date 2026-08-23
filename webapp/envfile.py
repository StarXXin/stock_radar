"""`.env` 文件读写工具(供 webapp 配置页使用)。

设计约束:
- 只改写"托管键"所在行,注释/空行/非托管键原样保留(逐行处理,顺序不变);
- 写前全量校验(由调用方传入 validator),任一非法则整体不写;
- tmp + os.replace 原子替换,并留 .bak 备份;模块级锁防并发写。
"""

from __future__ import annotations

import logging
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path

from exceptions import ConfigError

logger = logging.getLogger(__name__)

_WRITE_LOCK = threading.Lock()

# KEY=VALUE 或 KEY="VALUE"(允许 export 前缀与行内注释)
_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def parse_value(raw: str) -> str:
    """解析 .env 行内 VALUE 部分:去成对引号;非引号值去掉 " #" 起始的行内注释。"""
    value = raw.strip()
    if value[:1] in {'"', "'"}:  # 引号值:找到闭合引号,其后内容视为行内注释
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[1:end]
    idx = value.find(" #")  # 无空格的 # 属于值本身(如 URL fragment)
    if idx != -1:
        value = value[:idx]
    return value.rstrip()


def _split_inline_comment(raw: str) -> tuple[str, str]:
    """拆出 VALUE 部分的 (值原文, 行内注释含前导空格)。

    引号值的行内内容整体视为值(dotenv 同款语义);仅非引号值识别 " #" 注释。
    """
    if raw.lstrip().startswith(('"', "'")):
        return raw, ""
    idx = raw.find(" #")
    if idx != -1:
        return raw[:idx], raw[idx:]
    return raw, ""


def _format_value(value: str) -> str:
    """写回时序列化:含特殊字符时加双引号并转义。"""
    if any(ch in value for ch in ' "#\'\n'):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def read_env(path: Path) -> dict[str, str]:
    """读取 .env 为 dict(KEY→字符串值);文件不存在返回空 dict。"""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m is None:
            continue
        result[m.group(1)] = parse_value(m.group(2))
    return result


def update_env(
    path: Path,
    updates: dict[str, str],
    validate: Callable[[str, str], None] | None = None,
) -> None:
    """把 updates 写入 .env:托管键替换值,缺失键追加到末尾。

    - 注释/空行/非托管键所在行字节级保留;
    - validate(key, value) 在写盘前逐项调用,抛 ConfigError 则整体不写;
    - tmp + os.replace 原子替换;覆盖已有文件时先备份为 <path>.bak。
    """
    with _WRITE_LOCK:
        if validate is not None:
            for key, value in updates.items():
                validate(key, value)

        original_lines = (
            path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        )
        pending = dict(updates)
        out_lines: list[str] = []
        for line in original_lines:
            stripped = line.lstrip()
            if stripped.startswith("#") or "=" not in line:
                out_lines.append(line)
                continue
            m = _LINE_RE.match(line)
            if m is None or m.group(1) not in pending:
                out_lines.append(line)
                continue
            key = m.group(1)
            indent = line[: len(line) - len(line.lstrip())]
            _, comment = _split_inline_comment(m.group(2))
            out_lines.append(f"{indent}{key}={_format_value(pending.pop(key))}{comment}")

        for key, value in pending.items():  # 文件中没有的键追加到末尾
            out_lines.append(f"{key}={_format_value(value)}")

        new_text = "\n".join(out_lines) + ("\n" if out_lines else "")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup = path.with_name(path.name + ".bak")
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, path)
        logger.info("已更新 %s(%d 个配置项)", path, len(updates))


def mask_secret(value: str) -> str:
    """密钥掩码展示:只透露有无与首尾各 4 字符。"""
    if not value:
        return "(未配置)"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def raise_config_error(message: str) -> None:
    """供调用方在 validate 回调里抛出统一异常类型。"""
    raise ConfigError(message)

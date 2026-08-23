"""配置页表单字段声明:一处定义,驱动表单渲染、校验与 .env 写回三处。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from exceptions import ConfigError

FieldType = Literal["str", "int", "bool", "csv", "csv_watchlist", "choice"]

# 数据源合法值(与 sources/__init__.py 的 _REGISTRY 登记名一致)
VALID_SOURCES = ("eastmoney", "cninfo", "sse_official")
_VALID_IMPORTANCE = ("低", "中", "高")
_WATCHLIST_ITEM_RE = re.compile(r"^\d{6}(=(低|中|高))?$")

# 密钥类键:UI 只展示掩码状态,不提供编辑
SECRET_KEYS = ("DEEPSEEK_API_KEY", "PUSHPLUS_TOKEN")


@dataclass(frozen=True)
class FormField:
    """一个可编辑配置项的元数据与校验规则。"""

    key: str
    label: str
    ftype: FieldType
    required: bool = True
    min_v: int | None = None
    max_v: int | None = None
    choices: tuple[str, ...] = ()
    hint: str = ""
    placeholder: str = ""
    csv_choices: tuple[str, ...] = field(default=())  # csv 每项的合法值


# 表单字段顺序即页面展示顺序
FORM_FIELDS: tuple[FormField, ...] = (
    FormField("WATCHLIST", "自选股列表", "csv_watchlist",
              hint="6 位代码逗号分隔,支持 代码=低/中/高 按股覆盖阈值"),
    FormField("LOOKBACK_DAYS", "回看天数", "int", min_v=1, max_v=30),
    FormField("DATA_SOURCE", "数据源", "csv", csv_choices=VALID_SOURCES,
              hint="逗号分隔多源合并;可选: " + " / ".join(VALID_SOURCES)),
    FormField("FETCH_CONTENT", "抓取正文", "bool", required=False,
              hint="关=只用标题摘要,省时间但质量降"),
    FormField("KEYWORDS", "关键词", "csv", required=False,
              placeholder="留空用内置默认",
              hint="关键正文抽取关键词,逗号分隔;留空用内置默认"),
    FormField("PUSH_MIN_IMPORTANCE", "推送阈值", "choice",
              choices=_VALID_IMPORTANCE, hint="低于该重要性的公告不推送"),
    FormField("ROUTINE_TITLE_FILTER", "例行标题预滤", "bool", required=False,
              hint="命中例行公告跳过 AI,省 token"),
    FormField("ENRICH_CONCURRENCY", "富化并发数", "int", min_v=1, max_v=8,
              hint="LLM 限速报错多时降为 1"),
    FormField("PUSH_MAX_PER_MESSAGE", "单条推送条数上限", "int", min_v=1, max_v=50),
    FormField("ALERT_ON_ERROR", "失败告警", "bool", required=False,
              hint="采集全失败/推送失败时发告警消息(需配 Token)"),
    FormField("HEARTBEAT_DAYS", "心跳天数", "int", min_v=0, max_v=365,
              hint="距上次运行超 N 天发提醒;0=关"),
    FormField("RETENTION_DAYS", "数据保留天数", "int", min_v=0, max_v=3650,
              hint="去重库/摘要缓存/正文缓存保留天数;0=不清理"),
    FormField("LOG_LEVEL", "日志级别", "choice",
              choices=("DEBUG", "INFO", "WARNING", "ERROR")),
)

_MANAGED_KEYS: frozenset[str] = frozenset(f.key for f in FORM_FIELDS)


def is_managed(key: str) -> bool:
    return key in _MANAGED_KEYS


def validate_field(field_def: FormField, value: str) -> str:
    """校验并规整单个字段值,返回序列化到 .env 的字符串;非法抛 ConfigError。

    - bool: 接受 checkbox 提交的 "on"/"true"/缺失(→false);
    - int: 范围 [min_v, max_v];
    - choice: 必须在 choices 内;
    - csv/csv_watchlist: 按逗号拆分逐项校验。
    """
    if field_def.ftype == "bool":
        return "true" if value.strip().lower() in {"on", "true", "1", "yes"} else "false"

    text = value.strip()
    if not text:
        if field_def.required:
            raise ConfigError(f"{field_def.label}({field_def.key}) 不能为空")
        return ""

    if field_def.ftype == "int":
        try:
            num = int(text)
        except ValueError as e:
            raise ConfigError(f"{field_def.label}({field_def.key}) 需为整数: {text!r}") from e
        lo = field_def.min_v if field_def.min_v is not None else -(2**31)
        hi = field_def.max_v if field_def.max_v is not None else 2**31 - 1
        if not lo <= num <= hi:
            raise ConfigError(f"{field_def.label}({field_def.key}) 需在 {lo}~{hi} 之间")
        return str(num)

    if field_def.ftype == "choice":
        if text not in field_def.choices:
            raise ConfigError(
                f"{field_def.label}({field_def.key}) 需为 {'/'.join(field_def.choices)}")
        return text

    # csv / csv_watchlist:拆分、去空白、丢空项
    items = [item.strip() for item in text.split(",") if item.strip()]
    if field_def.required and not items:
        raise ConfigError(f"{field_def.label}({field_def.key}) 不能为空")
    if field_def.ftype == "csv_watchlist":
        for item in items:
            if not _WATCHLIST_ITEM_RE.match(item):
                raise ConfigError(
                    f"{field_def.label}({field_def.key}) 含非法项 {item!r},"
                    "应为 6 位数字代码或 代码=低/中/高")
    elif field_def.csv_choices:
        for item in items:
            if item not in field_def.csv_choices:
                raise ConfigError(
                    f"{field_def.label}({field_def.key}) 含非法值 {item!r},"
                    f"可选: {'/'.join(field_def.csv_choices)}")
    return ",".join(items)

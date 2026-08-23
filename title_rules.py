"""标题规则预滤:明显例行公告跳过 AI,直接给低重要性 Summary。

省 token、降延迟;被标为「低」后由 push_policy 决定是否推送。
匹配为子串/正则,可经 config.ROUTINE_TITLE_PATTERNS 覆盖。
"""

from __future__ import annotations

import re

import config
from models import Summary

# 保守默认:常见噪声类公告,避免误伤「重大合同/立案/减持」等
_DEFAULT_PATTERNS: list[str] = [
    r"股东大会",
    r"关于召开",
    r"法律意见书",
    r"保荐(?:人)?(?:工作报告|意见)",
    r"独立董事.*(?:声明|提名人)",
    r"股份回购进展",
    r"回购.*进展公告",
    r"投资者关系活动",
    r"网上业绩说明会",
    r"日常关联交易.*预计",
    r"延期.*股东大会",
    r"取消.*股东大会",
]


def _compiled_patterns(patterns: list[str] | None = None) -> list[re.Pattern[str]]:
    if patterns is not None:
        raw = patterns
    elif config.ROUTINE_TITLE_PATTERNS:
        raw = config.ROUTINE_TITLE_PATTERNS
    else:
        raw = _DEFAULT_PATTERNS
    out: list[re.Pattern[str]] = []
    for p in raw:
        p = (p or "").strip()
        if not p:
            continue
        try:
            out.append(re.compile(p))
        except re.error:
            out.append(re.compile(re.escape(p)))
    return out


def is_routine_title(title: str, patterns: list[str] | None = None) -> bool:
    if not title:
        return False
    return any(p.search(title) for p in _compiled_patterns(patterns))


def try_routine_summary(title: str, patterns: list[str] | None = None) -> Summary | None:
    """命中例行规则时返回低重要性 Summary;否则 None(交给 AI)。"""
    if not config.ROUTINE_TITLE_FILTER:
        return None
    if not is_routine_title(title, patterns):
        return None
    return Summary(
        importance="低",
        sentiment="中性",
        summary="例行公告(规则预滤,未调用AI)",
        key_points=[],
        content_source="rule",
    )

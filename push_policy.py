"""智能推送策略(summary -> 是否推送)。

低于阈值重要性的公告(如常规股东大会通知)不推送;重大合同等高重要性推送。
支持按股票覆盖阈值(WATCHLIST 里 "代码=低" 语法),未覆盖的用全局 PUSH_MIN_IMPORTANCE。
"""

from __future__ import annotations

import config
from models import Summary

_RANK = {"低": 1, "中": 2, "高": 3}


def should_push(
    summary: Summary,
    min_importance: str | None = None,
    code: str | None = None,
) -> bool:
    # 按股票覆盖 > 显式参数 > 全局默认;覆盖值非法时回退全局
    threshold = config.WATCHLIST_THRESHOLDS.get(code or "") if code else None
    if not threshold:
        threshold = min_importance if min_importance is not None else config.PUSH_MIN_IMPORTANCE
    # 未知重要性放行(避免漏掉);阈值未知按最低门槛
    return _RANK.get(summary.importance, 99) >= _RANK.get(threshold, 1)

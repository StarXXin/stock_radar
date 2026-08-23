"""智能推送策略(summary -> 是否推送)。

低于阈值重要性的公告(如常规股东大会通知)不推送;重大合同等高重要性推送。
"""

from __future__ import annotations

import config
from models import Summary

_RANK = {"低": 1, "中": 2, "高": 3}


def should_push(summary: Summary, min_importance: str | None = None) -> bool:
    threshold = min_importance if min_importance is not None else config.PUSH_MIN_IMPORTANCE
    # 未知重要性放行(避免漏掉);阈值未知按最低门槛
    return _RANK.get(summary.importance, 99) >= _RANK.get(threshold, 1)

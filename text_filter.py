"""关键词过滤(text -> 关键正文)。

抽取含关键词的段落/句子作为"关键正文"喂给 AI,先降噪、省 token;
无命中时回退到前几段,保证 AI 仍有上下文。
"""

from __future__ import annotations

import re

import config

_SPLIT_RE = re.compile(r"[\n。;；]+")


def extract_key_content(
    text: str,
    keywords: list[str] | None = None,
    max_chars: int | None = None,
    fallback_parts: int = 3,
) -> str:
    if not text:
        return ""
    kws = keywords if keywords is not None else config.KEYWORDS
    cap = max_chars if max_chars is not None else config.MAX_CONTENT_CHARS

    parts = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]
    hits = [p for p in parts if any(k in p for k in kws)]
    selected = hits if hits else parts[:fallback_parts]
    return "\n".join(selected)[:cap]

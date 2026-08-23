"""把 Notice + Summary 渲染成 Markdown 推送块。标题原样直出,不经 AI 加工。

支持按条数/字符数分页,避免 PushPlus 等渠道单条过长被拒。
"""

from __future__ import annotations

import config
from models import Notice, Summary


def _render_summary(summary: Summary | None) -> str:
    if summary is None:
        return "(无摘要)"
    head = f"【重要性:{summary.importance} | 倾向:{summary.sentiment}】{summary.summary}"
    if summary.key_points:
        points = "\n".join(f"  · {p}" for p in summary.key_points)
        return f"{head}\n{points}"
    return head


def render_notice(notice: Notice) -> str:
    return (
        f"### {notice.name or notice.code}\n"
        f"- 标题: {notice.title}\n"
        f"- AI: {_render_summary(notice.summary)}\n"
        f"- {notice.date}  {notice.url}"
    )


def render_blocks(notices: list[Notice]) -> str:
    return "\n\n".join(render_notice(n) for n in notices)


def paginate_notices(
    notices: list[Notice],
    max_per_message: int | None = None,
    max_chars: int | None = None,
) -> list[list[Notice]]:
    """把公告列表拆成多页。单条超长时独占一页(不截断正文,由渠道侧决定)。"""
    if not notices:
        return []
    per = max_per_message if max_per_message is not None else config.PUSH_MAX_PER_MESSAGE
    cap = max_chars if max_chars is not None else config.PUSH_MAX_CHARS
    per = max(1, per)
    cap = max(1, cap)

    pages: list[list[Notice]] = []
    batch: list[Notice] = []
    batch_chars = 0

    for n in notices:
        block = render_notice(n)
        # 批内用 \n\n 连接,第二块起多 2 字符
        extra = len(block) + (2 if batch else 0)
        if batch and (len(batch) >= per or batch_chars + extra > cap):
            pages.append(batch)
            batch = []
            batch_chars = 0
            extra = len(block)
        batch.append(n)
        batch_chars += extra

    if batch:
        pages.append(batch)
    return pages

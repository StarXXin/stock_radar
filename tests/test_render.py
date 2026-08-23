import render
from models import Notice, Summary


def test_render_includes_title_verbatim_and_fields():
    n = Notice(code="600519", name="茅台", title="关于回购的公告", date="2026-07-10", url="http://u")
    n.summary = Summary(
        importance="高", sentiment="利好", summary="回购注销", key_points=["金额5亿", "用于注销"]
    )
    block = render.render_notice(n)
    assert "关于回购的公告" in block  # 标题原样直出
    assert "【重要性:高 | 倾向:利好】回购注销" in block
    assert "金额5亿" in block and "用于注销" in block
    assert "茅台" in block
    assert "http://u" in block


def test_render_without_key_points():
    n = Notice(code="c", name="N", title="t", date="d", url="u")
    n.summary = Summary(importance="中", sentiment="中性", summary="摘要")
    block = render.render_notice(n)
    assert "【重要性:中 | 倾向:中性】摘要" in block


def test_render_handles_missing_summary():
    n = Notice(code="c", name="", title="t", date="d", url="u")
    block = render.render_notice(n)
    assert "(无摘要)" in block
    assert "### c" in block  # name 为空时回退到 code


def test_render_blocks_joins_with_blank_line():
    n1 = Notice(code="a", name="A", title="t1", date="d", url="u1")
    n2 = Notice(code="b", name="B", title="t2", date="d", url="u2")
    out = render.render_blocks([n1, n2])
    assert "t1" in out and "t2" in out
    assert "\n\n" in out


def _n(i: int) -> Notice:
    return Notice(code=str(i), name=f"N{i}", title=f"title-{i}", date="d", url=f"u{i}")


def test_paginate_by_count():
    pages = render.paginate_notices([_n(i) for i in range(5)], max_per_message=2, max_chars=10**9)
    assert len(pages) == 3
    assert [len(p) for p in pages] == [2, 2, 1]


def test_paginate_by_chars():
    # 故意把字符上限压到略大于单条,迫使每页只有 1 条
    one = render.render_notice(_n(0))
    pages = render.paginate_notices(
        [_n(i) for i in range(3)], max_per_message=10, max_chars=len(one) + 1
    )
    assert len(pages) == 3
    assert all(len(p) == 1 for p in pages)


def test_paginate_empty():
    assert render.paginate_notices([]) == []


def test_paginate_single_fits():
    pages = render.paginate_notices([_n(0)], max_per_message=8, max_chars=12000)
    assert len(pages) == 1 and len(pages[0]) == 1

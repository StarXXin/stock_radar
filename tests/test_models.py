from models import Notice, Summary, make_id


def test_notice_id_deterministic():
    n1 = Notice(code="600519", name="x", title="t", date="2026-07-10", url="u1")
    n2 = Notice(code="600519", name="y", title="t", date="2026-07-10", url="u2")
    assert n1.id == n2.id == make_id("600519", "2026-07-10", "t")


def test_notice_id_differs_on_title():
    n1 = Notice(code="600519", name="x", title="t1", date="d", url="u")
    n2 = Notice(code="600519", name="x", title="t2", date="d", url="u")
    assert n1.id != n2.id


def test_explicit_id_preserved():
    n = Notice(code="c", name="x", title="t", date="d", url="u", id="fixed")
    assert n.id == "fixed"


def test_summary_defaults():
    s = Summary(importance="高", sentiment="利好", summary="x")
    assert s.key_points == []
    assert s.content_source == "title"

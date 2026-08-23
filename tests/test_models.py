from models import Notice, Summary, make_id, normalize_date


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


def test_normalize_date_variants():
    assert normalize_date("2026-07-10") == "2026-07-10"
    assert normalize_date("2026-07-10 00:00:00") == "2026-07-10"
    assert normalize_date("2026/07/10") == "2026-07-10"
    assert normalize_date("2026年7月10日") == "2026-07-10"
    assert normalize_date("2026.07.10") == "2026-07-10"
    assert normalize_date("") == ""
    assert normalize_date("乱七八糟") == "乱七八糟"


def test_notice_normalizes_cross_source_dates():
    """同一公告两个渠道日期格式不同时,id 与去重 key 必须一致。"""
    n_em = Notice(code="600519", name="x", title="t", date="2026-07-10 00:00:00", url="em")
    n_cn = Notice(code="600519", name="x", title="t", date="2026/7/10", url="cninfo")
    assert n_em.date == n_cn.date == "2026-07-10"
    assert n_em.id == n_cn.id

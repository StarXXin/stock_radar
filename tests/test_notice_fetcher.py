import pytest

from models import Notice, RawNotice
from notice_fetcher import NoticeFetcher


def test_extract_art_code():
    assert NoticeFetcher._extract_art_code("http://x/AN202607101234.html") == "AN202607101234"
    assert NoticeFetcher._extract_art_code("http://x/none") is None
    assert NoticeFetcher._extract_art_code("") is None


def test_cache_key_eastmoney_and_cninfo():
    em = "https://data.eastmoney.com/notices/detail/600519/AN202607101234567890.html"
    assert NoticeFetcher._cache_key(em) == "AN202607101234567890"
    cn = (
        "http://www.cninfo.com.cn/new/disclosure/detail"
        "?stockCode=601127&announcementId=1212345678&announcementTime=2026-07-02"
    )
    assert NoticeFetcher._cache_key(cn) == "CN1212345678"
    assert NoticeFetcher._cache_key("http://no-code") is None


def test_fetch_returns_none_without_ident(tmp_path):
    f = NoticeFetcher(cache_dir=tmp_path)
    n = Notice(code="c", name="n", title="t", date="d", url="http://no-code")
    assert f.fetch(n) is None


def test_cache_hit_skips_download(tmp_path, sample_notice, mocker):
    art = NoticeFetcher._extract_art_code(sample_notice.url)
    (tmp_path / f"{art}.html").write_text("缓存正文", encoding="utf-8")
    f = NoticeFetcher(cache_dir=tmp_path)
    dl = mocker.patch.object(f, "_download")
    raw = f.fetch(sample_notice)
    assert raw is not None
    assert raw.kind == "html"
    assert raw.text == "缓存正文"
    dl.assert_not_called()  # 命中缓存,不再下载


def test_fetch_api_then_writes_cache(tmp_path, sample_notice, mocker):
    f = NoticeFetcher(cache_dir=tmp_path)
    resp = mocker.Mock()
    resp.json.return_value = {"data": {"notice_content": "重大合同正文"}}
    mocker.patch.object(f, "_get", return_value=resp)
    raw = f.fetch(sample_notice)
    assert raw.kind == "html"
    assert "重大合同" in raw.text
    art = NoticeFetcher._extract_art_code(sample_notice.url)
    assert (tmp_path / f"{art}.html").read_text(encoding="utf-8") == "重大合同正文"


def test_fetch_api_empty_falls_back_to_pdf(tmp_path, sample_notice, mocker):
    f = NoticeFetcher(cache_dir=tmp_path)
    mocker.patch.object(f, "_fetch_em_api", return_value=None)
    mocker.patch.object(f, "_fetch_em_pdf", return_value=RawNotice(kind="pdf", data=b"%PDF-1.4xxxx"))
    raw = f.fetch(sample_notice)
    assert raw.kind == "pdf"
    assert raw.data == b"%PDF-1.4xxxx"
    art = NoticeFetcher._extract_art_code(sample_notice.url)
    assert (tmp_path / f"{art}.pdf").read_bytes() == b"%PDF-1.4xxxx"


def test_fetch_all_fail_returns_none(tmp_path, sample_notice, mocker):
    f = NoticeFetcher(cache_dir=tmp_path)
    mocker.patch.object(f, "_fetch_em_api", return_value=None)
    mocker.patch.object(f, "_fetch_em_pdf", return_value=None)
    assert f.fetch(sample_notice) is None


def test_fetch_em_api_parses_notice_content(tmp_path, mocker):
    f = NoticeFetcher(cache_dir=tmp_path)
    resp = mocker.Mock()
    resp.json.return_value = {"data": {"notice_content": "  正文  "}}
    mocker.patch.object(f, "_get", return_value=resp)
    raw = f._fetch_em_api("AN1")
    assert raw.kind == "html"
    assert raw.text == "正文"


def _pdf_bytes(tag: bytes = b"cninfo") -> bytes:
    # 正文抓取会过滤过小/非 PDF 载荷,测试数据需 >100 字节
    return b"%PDF-1.4 " + tag + b" " + (b"x" * 120)


def test_cninfo_detail_resolves_pdf_and_caches(tmp_path, mocker):
    detail = (
        "http://www.cninfo.com.cn/new/disclosure/detail"
        "?stockCode=601127&announcementId=1212345678&announcementTime=2026-07-02"
    )
    n = Notice(code="601127", name="赛力斯", title="t", date="2026-07-02", url=detail)
    f = NoticeFetcher(cache_dir=tmp_path)

    html_resp = mocker.Mock()
    html_resp.text = (
        '<a href="http://static.cninfo.com.cn/finalpage/2026-07-02/1212345678.PDF">pdf</a>'
    )
    pdf_resp = mocker.Mock()
    pdf_resp.content = _pdf_bytes(b"detail")

    def _get(url, params=None, headers=None):
        if "static.cninfo.com.cn" in url:
            return pdf_resp
        return html_resp

    mocker.patch.object(f, "_get", side_effect=_get)
    raw = f.fetch(n)
    assert raw is not None
    assert raw.kind == "pdf"
    assert raw.data.startswith(b"%PDF")
    assert (tmp_path / "CN1212345678.pdf").read_bytes() == pdf_resp.content


def test_cninfo_finalpage_fallback(tmp_path, mocker):
    detail = (
        "http://www.cninfo.com.cn/new/disclosure/detail"
        "?stockCode=601127&announcementId=999&announcementTime=2026-07-02%2000:00:00"
    )
    n = Notice(code="601127", name="赛力斯", title="t", date="2026-07-02", url=detail)
    f = NoticeFetcher(cache_dir=tmp_path)
    mocker.patch.object(f, "_resolve_cninfo_pdf_from_detail", return_value=None)
    pdf_resp = mocker.Mock()
    pdf_resp.content = _pdf_bytes(b"fallback")

    def _get(url, params=None, headers=None):
        assert "finalpage/2026-07-02/999.PDF" in url
        return pdf_resp

    mocker.patch.object(f, "_get", side_effect=_get)
    raw = f.fetch(n)
    assert raw is not None
    assert raw.kind == "pdf"


def test_cninfo_direct_pdf_url(tmp_path, mocker):
    url = "http://static.cninfo.com.cn/finalpage/2026-07-02/1212345678.PDF"
    n = Notice(code="601127", name="赛力斯", title="t", date="2026-07-02", url=url)
    f = NoticeFetcher(cache_dir=tmp_path)
    pdf_resp = mocker.Mock()
    pdf_resp.content = _pdf_bytes(b"direct")
    mocker.patch.object(f, "_get", return_value=pdf_resp)
    raw = f.fetch(n)
    assert raw is not None
    assert raw.kind == "pdf"
    assert (tmp_path / "CN1212345678.pdf").exists()


def test_cleanup_cache_removes_old_files_only(tmp_path):
    import os
    import time

    old_file = tmp_path / "AN_old.html"
    new_file = tmp_path / "AN_new.html"
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")
    very_old = time.time() - 100 * 86400
    os.utime(old_file, (very_old, very_old))

    f = NoticeFetcher(cache_dir=tmp_path)
    removed = f.cleanup_cache(retention_days=90)

    assert removed == 1
    assert not old_file.exists()
    assert new_file.exists()


def test_cleanup_cache_zero_days_noop(tmp_path):
    f = NoticeFetcher(cache_dir=tmp_path)
    (tmp_path / "x.html").write_text("x", encoding="utf-8")
    assert f.cleanup_cache(retention_days=0) == 0
    assert (tmp_path / "x.html").exists()

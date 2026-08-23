import notice_parser
from models import RawNotice


def test_parse_html_strips_tags():
    raw = RawNotice(kind="html", text="<div>公司签订<b>5亿元</b>重大合同</div>")
    out = notice_parser.parse(raw)
    assert "<" not in out and ">" not in out
    assert "合同" in out
    assert "5亿元" in out


def test_parse_html_unescapes_entities():
    out = notice_parser.parse(RawNotice(kind="html", text="甲&amp;乙"))
    assert "甲&乙" in out


def test_parse_pdf(mocker):
    page = mocker.Mock()
    page.extract_text.return_value = "回购公告正文"
    reader = mocker.Mock()
    reader.pages = [page]
    mocker.patch("pypdf.PdfReader", return_value=reader)
    out = notice_parser.parse(RawNotice(kind="pdf", data=b"%PDF-1.4"))
    assert "回购公告正文" in out


def test_parse_empty_payloads():
    assert notice_parser.parse(RawNotice(kind="html", text="")) == ""
    assert notice_parser.parse(RawNotice(kind="pdf", data=None)) == ""

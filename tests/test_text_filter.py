import text_filter

KW = ["合同", "回购"]


def test_keeps_only_keyword_sentences():
    text = "今天天气不错。\n公司签订5亿元重大合同。\n无关内容。"
    out = text_filter.extract_key_content(text, KW)
    assert "合同" in out
    assert "今天天气" not in out


def test_fallback_lead_when_no_keyword():
    text = "第一段无关。\n第二段也无关。\n第三段。\n第四段。"
    out = text_filter.extract_key_content(text, KW, fallback_parts=2)
    assert "第一段无关" in out
    assert "第四段" not in out


def test_empty_text_returns_empty():
    assert text_filter.extract_key_content("", KW) == ""


def test_length_capped():
    text = "重大合同" + "啊" * 5000
    out = text_filter.extract_key_content(text, KW, max_chars=100)
    assert len(out) <= 100

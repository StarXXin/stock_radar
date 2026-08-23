"""原始载荷解析(raw -> text)。pdf 走 pypdf;html/纯文本去标签并规整空白。"""

from __future__ import annotations

import io
import logging
import re
from html import unescape

from exceptions import ContentFetchError
from models import RawNotice

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_INLINE_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def parse(raw: RawNotice) -> str:
    if raw.kind == "pdf":
        return _pdf_to_text(raw.data or b"")
    return _html_to_text(raw.text or "")


def _pdf_to_text(data: bytes) -> str:
    if not data:
        return ""
    import pypdf  # 延迟导入:仅解析 PDF 时才依赖

    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:
        raise ContentFetchError(f"PDF 解析失败: {e}") from e
    return _normalize(text)


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    text = _TAG_RE.sub("\n", html)  # 标签换成换行,保留段落感
    return _normalize(unescape(text))


def _normalize(text: str) -> str:
    text = _INLINE_WS_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()

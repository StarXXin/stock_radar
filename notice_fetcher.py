"""公告正文抓取(url -> html/pdf 原始载荷)。

职责:根据 notice.url 拿到原始正文载荷,带本地缓存避免重复下载。
按 URL 分流:
- 东财: art_code → 正文接口 → 官方 PDF
- 巨潮: 直链 PDF / 详情页解析 PDF 链 / finalpage 拼接
解析交给 notice_parser。
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

import config
from exceptions import ContentFetchError
from models import RawNotice

logger = logging.getLogger(__name__)

_ART_CODE_RE = re.compile(r"AN\d+")
_CONTENT_API = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
_PDF_URL = "https://pdf.dfcfw.com/pdf/H2_{art_code}_1.pdf"
_CNINFO_PDF_RE = re.compile(
    r"https?://static\.cninfo\.com\.cn/[^\s\"'<>]+\.pdf",
    re.IGNORECASE,
)
_CNINFO_REL_PDF_RE = re.compile(
    r"(?:finalpage|notice)/[^\s\"'<>]+\.pdf",
    re.IGNORECASE,
)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


class NoticeFetcher:
    def __init__(
        self,
        cache_dir: Path | None = None,
        timeout: int | None = None,
        retries: int | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir is not None else config.CONTENT_CACHE_DIR
        self._timeout = timeout if timeout is not None else config.REQUEST_TIMEOUT
        self._retries = retries if retries is not None else config.HTTP_RETRIES
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _UA})

    def fetch(self, notice) -> RawNotice | None:
        url = notice.url or ""
        cache_key = self._cache_key(url)
        if not cache_key:
            logger.warning("无法识别正文标识,降级用标题: %s", url)
            return None

        cached = self._load_cache(cache_key)
        if cached is not None:
            logger.info("正文命中缓存 key=%s (%s)", cache_key, cached.kind)
            return cached

        raw = self._download(url, cache_key)
        if raw is not None:
            self._save_cache(cache_key, raw)
        else:
            logger.warning("正文抓取失败,降级用标题 key=%s url=%s", cache_key, url)
        return raw

    def _download(self, url: str, cache_key: str) -> RawNotice | None:
        if self._is_cninfo(url):
            return self._download_cninfo(url, cache_key)
        return self._download_eastmoney(cache_key)

    def _download_eastmoney(self, art_code: str) -> RawNotice | None:
        for label, fetch_fn in (("接口", self._fetch_em_api), ("PDF", self._fetch_em_pdf)):
            try:
                raw = fetch_fn(art_code)
            except ContentFetchError as e:
                logger.warning("%s 抓取失败 art_code=%s: %s", label, art_code, e)
                continue
            if raw is not None:
                logger.info("正文来自东财%s art_code=%s", label, art_code)
                return raw
            logger.info("东财%s 无正文 art_code=%s", label, art_code)
        return None

    def _download_cninfo(self, url: str, cache_key: str) -> RawNotice | None:
        # ① 链接本身已是 PDF
        if url.lower().endswith(".pdf") or "static.cninfo.com.cn" in url.lower():
            try:
                raw = self._fetch_pdf_url(url)
            except ContentFetchError as e:
                logger.warning("巨潮直链 PDF 失败 key=%s: %s", cache_key, e)
                return None
            if raw is not None:
                logger.info("正文来自巨潮直链 PDF key=%s", cache_key)
            return raw

        # ② 详情页 HTML 内找 PDF 链接
        try:
            pdf_url = self._resolve_cninfo_pdf_from_detail(url)
        except ContentFetchError as e:
            logger.warning("巨潮详情页解析失败 key=%s: %s", cache_key, e)
            pdf_url = None

        # ③ 用 query 参数拼接 finalpage(常见路径,不保证全覆盖)
        if not pdf_url:
            pdf_url = self._build_cninfo_finalpage_url(url)
            if pdf_url:
                logger.info("尝试巨潮 finalpage 拼接 key=%s", cache_key)

        if not pdf_url:
            return None

        try:
            raw = self._fetch_pdf_url(pdf_url)
        except ContentFetchError as e:
            logger.warning("巨潮 PDF 下载失败 key=%s: %s", cache_key, e)
            return None
        if raw is not None:
            logger.info("正文来自巨潮 PDF key=%s", cache_key)
        return raw

    def _resolve_cninfo_pdf_from_detail(self, detail_url: str) -> str | None:
        resp = self._get(detail_url, headers={"Referer": "http://www.cninfo.com.cn/"})
        html = resp.text or ""
        m = _CNINFO_PDF_RE.search(html)
        if m:
            return m.group(0)
        m = _CNINFO_REL_PDF_RE.search(html)
        if m:
            return "http://static.cninfo.com.cn/" + m.group(0).lstrip("/")
        return None

    @staticmethod
    def _build_cninfo_finalpage_url(url: str) -> str | None:
        qs = parse_qs(urlparse(url).query)
        ann_ids = qs.get("announcementId") or qs.get("announcementid")
        times = qs.get("announcementTime") or qs.get("announcementtime")
        if not ann_ids:
            return None
        ann_id = ann_ids[0].strip()
        if not ann_id:
            return None
        # announcementTime 常见为 2026-07-02 或 2026-07-02 00:00:00
        if times:
            day = times[0].strip()[:10]
            if len(day) == 10:
                return f"http://static.cninfo.com.cn/finalpage/{day}/{ann_id}.PDF"
        return None

    @staticmethod
    def _is_cninfo(url: str) -> bool:
        host = (urlparse(url).netloc or "").lower()
        return "cninfo.com.cn" in host

    @staticmethod
    def _cache_key(url: str) -> str | None:
        art = NoticeFetcher._extract_art_code(url)
        if art:
            return art
        if NoticeFetcher._is_cninfo(url):
            qs = parse_qs(urlparse(url).query)
            ann_ids = qs.get("announcementId") or qs.get("announcementid")
            if ann_ids and ann_ids[0].strip():
                return f"CN{ann_ids[0].strip()}"
            # 直链 PDF: 用路径末段做 key
            path = urlparse(url).path
            name = Path(path).stem
            if name:
                return f"CN{name}"
        return None

    @staticmethod
    def _extract_art_code(url: str) -> str | None:
        match = _ART_CODE_RE.search(url or "")
        return match.group(0) if match else None

    def _fetch_em_api(self, art_code: str) -> RawNotice | None:
        resp = self._get(
            _CONTENT_API,
            params={"art_code": art_code, "client_source": "web", "page_index": 1},
        )
        payload = resp.json()
        data = payload.get("data") or {}
        content = (data.get("notice_content") or "").strip()
        return RawNotice(kind="html", text=content) if content else None

    def _fetch_em_pdf(self, art_code: str) -> RawNotice | None:
        return self._fetch_pdf_url(_PDF_URL.format(art_code=art_code))

    def _fetch_pdf_url(self, url: str) -> RawNotice | None:
        resp = self._get(url, headers={"Referer": "http://www.cninfo.com.cn/"})
        data = resp.content or b""
        # 粗筛: 过小或明显 HTML 错误页不当 PDF
        if len(data) < 100:
            return None
        head = data[:20].lstrip()
        if head.startswith(b"<") or head.startswith(b"{"):
            return None
        return RawNotice(kind="pdf", data=data)

    def _get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = self._session.get(
                    url, params=params, headers=headers, timeout=self._timeout
                )
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                last_exc = e
                logger.debug("请求失败(第 %d 次) %s: %s", attempt + 1, url, e)
                if attempt < self._retries:
                    time.sleep(0.5 * (attempt + 1))
        raise ContentFetchError(f"请求失败: {url}: {last_exc}") from last_exc

    # --- 本地缓存:避免每次都下载 ---
    def _html_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.html"

    def _pdf_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.pdf"

    def _load_cache(self, key: str) -> RawNotice | None:
        html_path = self._html_path(key)
        if html_path.exists():
            return RawNotice(kind="html", text=html_path.read_text(encoding="utf-8"))
        pdf_path = self._pdf_path(key)
        if pdf_path.exists():
            return RawNotice(kind="pdf", data=pdf_path.read_bytes())
        return None

    def _save_cache(self, key: str, raw: RawNotice) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            if raw.kind == "pdf" and raw.data is not None:
                self._pdf_path(key).write_bytes(raw.data)
            elif raw.text:
                self._html_path(key).write_text(raw.text, encoding="utf-8")
        except OSError as e:
            logger.warning("写正文缓存失败 key=%s: %s", key, e)

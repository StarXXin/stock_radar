"""上交所官方公告数据源(免费,无需注册)。

直连 query.sse.com.cn 个股公告接口,作为沪市的第三重保障:
东财按日接口改版/漏单时,沪市公告仍可从此源获取。
公告链接为 static.sse.com.cn 的 PDF 直链,notice_fetcher 可直接下载正文。

接口要点(2026-08 实测):
- 必须带 Referer: https://www.sse.com.cn/... 否则防盗链拦截;
- 返回 JSONP,需剥掉回调外壳;结果在 result[] 数组;
- PDF 地址 = https://static.sse.com.cn + URL 字段。

返回语义(与 eastmoney/cninfo 一致):
- 正常空列表: 接口可用但窗口内无自选股公告
- DataSourceError: 自选股全部请求均失败(勿当成「无公告」)
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import requests

from exceptions import DataSourceError
from models import Notice
from sources.base import NoticeSource

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_BULLETIN_URL = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
_REFERER = (
    "https://www.sse.com.cn/assortment/stock/list/info/announcement/index.shtml"
)
_PDF_PREFIX = "https://static.sse.com.cn"
# JSONP 外壳: jsonpCallback123({...}) -> {...}
_JSONP_RE = re.compile(r"^[^(]*\((.*)\)\s*;?\s*$", re.S)


class SseOfficialNoticeSource(NoticeSource):
    name = "sse_official"

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "Mozilla/5.0", "Referer": _REFERER}
        )

    def fetch_recent(self, codes: list[str], lookback_days: int) -> list[Notice]:
        end = datetime.now()
        begin = (end - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end_date = end.strftime("%Y-%m-%d")

        notices: list[Notice] = []
        seen: set[tuple[str, str, str]] = set()
        attempted = 0
        failed = 0
        for code in codes:
            attempted += 1
            items, ok = self._fetch_symbol(code, begin, end_date)
            if not ok:
                failed += 1
                continue
            for item in items:
                title = str(item.get("TITLE") or "").strip()
                if not title:
                    continue
                date = str(item.get("SSEDATE") or item.get("ADDDATE") or "")
                pdf_url = _PDF_PREFIX + str(item.get("URL") or "")
                key = (code, date, title)
                if key in seen:
                    continue
                seen.add(key)
                notices.append(
                    Notice(
                        code=code,
                        name=str(item.get("SECURITY_NAME_ABBR") or code),
                        title=title,
                        date=date,
                        url=pdf_url,
                    )
                )

        if attempted > 0 and failed == attempted:
            raise DataSourceError(
                f"上交所官方采集全部失败({failed}/{attempted} 只),请检查网络或接口"
            )
        if failed:
            logger.warning("上交所官方部分代码失败 %d/%d 只,已用成功代码继续", failed, attempted)
        logger.info("上交所官方采集到 %d 条自选股公告", len(notices))
        return notices

    def _fetch_symbol(
        self, code: str, begin_date: str, end_date: str
    ) -> tuple[list[dict], bool]:
        """返回 (items, ok)。ok=False 请求失败; ok=True 空=区间无公告。"""
        try:
            resp = self._session.get(
                _BULLETIN_URL,
                params={
                    "isPagination": "true",
                    "securityType": "0101,120100,020100,020200,120200",
                    "reportType": "ALL",
                    "pageHelp.pageSize": "50",
                    "pageHelp.pageCount": "50",
                    "pageHelp.pageNo": "1",
                    "pageHelp.beginPage": "1",
                    "pageHelp.cacheSize": "1",
                    "pageHelp.endPage": "5",
                    "_": str(int(time.time() * 1000)),
                    "beginDate": begin_date,
                    "endDate": end_date,
                    "productId": code,
                },
                timeout=15,
            )
            resp.raise_for_status()
            payload = _JSONP_RE.sub(r"\1", resp.text)
            data = json.loads(payload)
            return data.get("result") or [], True
        except (requests.RequestException, ValueError) as e:
            logger.warning("上交所官方拉取 %s 公告失败: %s", code, e)
            return [], False

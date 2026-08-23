"""东方财富公告数据源。

按日期拉全市场公告,再按自选股过滤。东财数据覆盖全,
不像巨潮那张表会漏掉科创板/次新股而报错。

返回语义:
- 正常空列表: 接口可用但窗口内无自选股公告
- DataSourceError: 回看窗口内全部交易日请求均失败(勿当成「无公告」)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import akshare as ak

from exceptions import DataSourceError
from models import Notice
from sources.base import NoticeSource

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)


class EastMoneyNoticeSource(NoticeSource):
    name = "eastmoney"

    def fetch_recent(self, codes: list[str], lookback_days: int) -> list[Notice]:
        wanted = {str(c) for c in codes}
        end = datetime.now()
        notices: list[Notice] = []
        seen: set[tuple[str, str, str]] = set()
        attempted = 0
        failed = 0
        for i in range(lookback_days + 1):
            day = (end - timedelta(days=i)).strftime("%Y%m%d")
            attempted += 1
            df, ok = self._fetch_day(day)
            if not ok:
                failed += 1
                continue
            if df is None or df.empty:
                continue
            sub = df[df.iloc[:, 0].astype(str).isin(wanted)]
            for _, row in sub.iterrows():
                # 东财列顺序: 代码, 名称, 公告标题, 公告类型, 公告日期, 网址
                code = str(row.iloc[0])
                title = str(row.iloc[2])
                date = str(row.iloc[4])
                key = (code, date, title)
                if key in seen:
                    continue
                seen.add(key)
                notices.append(
                    Notice(
                        code=code,
                        name=str(row.iloc[1]),
                        title=title,
                        date=date,
                        url=str(row.iloc[5]),
                    )
                )

        if attempted > 0 and failed == attempted:
            raise DataSourceError(
                f"东财采集全部失败({failed}/{attempted} 日),请检查网络或数据源"
            )
        if failed:
            logger.warning("东财部分日期失败 %d/%d 日,已用成功日期继续", failed, attempted)
        logger.info("东财采集到 %d 条自选股公告", len(notices))
        return notices

    def _fetch_day(self, date_str: str) -> tuple[pd.DataFrame | None, bool]:
        """返回 (df, ok)。ok=False 表示请求失败; ok=True 且 df 空表示当日无数据。"""
        try:
            return ak.stock_notice_report(symbol="全部", date=date_str), True
        except Exception as e:
            logger.warning("拉取 %s 公告失败: %s", date_str, e)
            return None, False

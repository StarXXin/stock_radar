"""巨潮资讯(CNINFO)公告数据源。

巨潮是官方法定信息披露平台,沪深京全覆盖。按代码逐只查询近 lookback_days 的
信息披露公告(区别于东财"按日拉全市场再过滤")。

返回语义:
- 正常空列表: 接口可用但窗口内无公告(含 akshare 无数据 KeyError)
- DataSourceError: 自选股全部请求均失败(勿当成「无公告」)
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


class CninfoNoticeSource(NoticeSource):
    name = "cninfo"

    def fetch_recent(self, codes: list[str], lookback_days: int) -> list[Notice]:
        end = datetime.now()
        start_date = (end - timedelta(days=lookback_days)).strftime("%Y%m%d")
        end_date = end.strftime("%Y%m%d")

        notices: list[Notice] = []
        seen: set[tuple[str, str, str]] = set()
        attempted = 0
        failed = 0
        for code in codes:
            attempted += 1
            df, ok = self._fetch_symbol(str(code), start_date, end_date)
            if not ok:
                failed += 1
                continue
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                # 巨潮列: 代码, 简称, 公告标题, 公告时间, 公告链接
                c = str(row["代码"])
                title = str(row["公告标题"])
                date = str(row["公告时间"])
                key = (c, date, title)
                if key in seen:
                    continue
                seen.add(key)
                notices.append(
                    Notice(
                        code=c,
                        name=str(row["简称"]),
                        title=title,
                        date=date,
                        url=str(row["公告链接"]),
                    )
                )

        if attempted > 0 and failed == attempted:
            raise DataSourceError(
                f"巨潮采集全部失败({failed}/{attempted} 只),请检查网络或数据源"
            )
        if failed:
            logger.warning("巨潮部分代码失败 %d/%d 只,已用成功代码继续", failed, attempted)
        logger.info("巨潮采集到 %d 条自选股公告", len(notices))
        return notices

    def _fetch_symbol(
        self, symbol: str, start_date: str, end_date: str
    ) -> tuple[pd.DataFrame | None, bool]:
        """返回 (df, ok)。ok=False 请求失败; ok=True 且空=区间无公告。"""
        try:
            return (
                ak.stock_zh_a_disclosure_report_cninfo(
                    symbol=symbol, market="沪深京", start_date=start_date, end_date=end_date
                ),
                True,
            )
        except KeyError:
            # 无公告时 akshare 会在列选择处抛 KeyError,视作"无数据"而非失败
            logger.debug("巨潮 %s 区间内无公告", symbol)
            return None, True
        except Exception as e:
            logger.warning("拉取 %s 巨潮公告失败: %s", symbol, e)
            return None, False

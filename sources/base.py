"""数据源抽象。新增渠道只需继承 NoticeSource 并在 sources 注册表登记。"""

from abc import ABC, abstractmethod

from models import Notice


class NoticeSource(ABC):
    #: 渠道唯一名称,用于配置 DATA_SOURCE 与注册表键
    name: str = ""

    @abstractmethod
    def fetch_recent(self, codes: list[str], lookback_days: int) -> list[Notice]:
        """拉取自选股在近 lookback_days(含当天)内的公告。"""
        raise NotImplementedError

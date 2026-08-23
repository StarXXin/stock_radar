"""数据源注册表:按名称获取 NoticeSource 实现,便于扩展多渠道。"""

from exceptions import ConfigError
from sources.base import NoticeSource
from sources.cninfo import CninfoNoticeSource
from sources.eastmoney import EastMoneyNoticeSource
from sources.sse_official import SseOfficialNoticeSource

_REGISTRY: dict[str, type[NoticeSource]] = {
    EastMoneyNoticeSource.name: EastMoneyNoticeSource,
    CninfoNoticeSource.name: CninfoNoticeSource,
    SseOfficialNoticeSource.name: SseOfficialNoticeSource,
}


def register_source(cls: type[NoticeSource]) -> type[NoticeSource]:
    """登记新数据源(可作装饰器使用)。"""
    _REGISTRY[cls.name] = cls
    return cls


def get_source(name: str) -> NoticeSource:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ConfigError(f"未知数据源: {name!r}. 可选: {', '.join(sorted(_REGISTRY))}")
    return cls()


__all__ = ["NoticeSource", "get_source", "register_source"]

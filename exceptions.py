"""项目统一异常分类。

底层模块抛出具体子类,main 分步捕获并记日志。
"""


class StockRadarError(Exception):
    """所有自定义异常的基类。"""


class ConfigError(StockRadarError):
    """配置缺失或非法(如 WATCHLIST 为空)。"""


class DataSourceError(StockRadarError):
    """行情/公告数据源拉取失败。"""


class ContentFetchError(StockRadarError):
    """公告正文(接口或 PDF)抓取失败。best-effort,通常内部捕获后降级。"""


class SummarizeError(StockRadarError):
    """大模型调用或 JSON 解析失败。"""


class NotifyError(StockRadarError):
    """消息推送失败。"""


class StorageError(StockRadarError):
    """本地存储(SQLite)读写失败。"""

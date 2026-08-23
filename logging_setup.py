"""日志配置:同时输出到控制台(stderr)与 data/ 下的滚动文件。"""

import logging
import sys
from logging.handlers import RotatingFileHandler

import config

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    """初始化根日志(幂等)。级别取 config.LOG_LEVEL。"""
    root = logging.getLogger()
    if getattr(root, "_stock_radar_configured", False):
        return

    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    root.setLevel(level)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    config.LOG_FILE.parent.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        config.LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    root._stock_radar_configured = True  # type: ignore[attr-defined]

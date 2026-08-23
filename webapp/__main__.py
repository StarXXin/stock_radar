"""webapp 入口:`uv run python -m webapp [--host H] [--port P]`。

默认仅监听 127.0.0.1(界面无鉴权,勿暴露到局域网)。
"""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK,避免中文乱码
    parser = argparse.ArgumentParser(
        prog="stock_radar web", description="stock_radar 本地控制台(Web UI)"
    )
    parser.add_argument("--host", default=os.getenv("WEB_HOST", "127.0.0.1"),
                        help="监听地址(默认 127.0.0.1;无鉴权,不建议改)")
    parser.add_argument("--port", type=int, default=int(os.getenv("WEB_PORT", "8787")))
    args = parser.parse_args(argv)

    import uvicorn

    from webapp.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

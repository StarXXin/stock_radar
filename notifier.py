"""消息推送:控制台打印 + PushPlus。

推送硬失败抛 NotifyError,让上层不标记已推送、下次自动重试。
"""

from __future__ import annotations

import logging

import requests

import config
from exceptions import NotifyError

logger = logging.getLogger(__name__)

PUSHPLUS_URL = "https://www.pushplus.plus/send"


class PushPlusNotifier:
    def __init__(self, token: str | None = None, timeout: int | None = None) -> None:
        self._token = token if token is not None else config.PUSHPLUS_TOKEN
        self._timeout = timeout if timeout is not None else config.REQUEST_TIMEOUT
        self._session = requests.Session()

    def notify(self, title: str, content: str) -> None:
        self._print_console(title, content)

        if not self._token:
            logger.info("未配置 PUSHPLUS_TOKEN,仅控制台输出")
            return

        try:
            resp = self._session.post(
                PUSHPLUS_URL,
                json={
                    "token": self._token,
                    "title": title,
                    "content": content,
                    "template": "markdown",
                },
                timeout=self._timeout,
            )
            data = resp.json()
        except requests.RequestException as e:
            raise NotifyError(f"推送请求异常: {e}") from e
        except ValueError as e:
            raise NotifyError(f"推送响应解析失败: {e}") from e

        if data.get("code") != 200:
            raise NotifyError(f"推送失败: {data.get('msg')}")
        logger.info("推送成功: %s", title)

    @staticmethod
    def _print_console(title: str, content: str) -> None:
        print("\n" + "=" * 46)
        print(title)
        print("-" * 46)
        print(content)
        print("=" * 46 + "\n")

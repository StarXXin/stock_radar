"""公告摘要:调用 DeepSeek(OpenAI 兼容)输出结构化 JSON。

输入=公告标题 + 关键正文(text_filter 过滤后);无正文退标题。
JSON 模式避免解析不稳定。
"""

from __future__ import annotations

import json
import logging
import time

from openai import OpenAI

import config
from exceptions import SummarizeError
from models import Notice, Summary

logger = logging.getLogger(__name__)

# 合规红线:只客观描述,严禁投资建议/买卖建议/涨跌预测
SYSTEM_PROMPT = (
    "你是A股上市公司公告摘要助手。\n"
    "输入:公告标题、公告正文关键内容。\n"
    "任务:1.提取事实 2.判断公告重要性 3.判断公告倾向。\n"
    "禁止:投资建议、买卖建议、涨跌预测、使用'利好买入'等表达。\n"
    "只输出一个 JSON 对象,字段:\n"
    "  importance: 取值 高/中/低\n"
    "  sentiment: 取值 利好/利空/中性/关注\n"
    "  summary: 一句话客观摘要\n"
    "  key_points: 关键事实要点数组(0~5 条,每条简短)"
)


class Summarizer:
    def __init__(
        self,
        client: OpenAI | None = None,
        model: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> None:
        self._client = client  # 延迟创建:空 API Key 时不在构造期报错
        self._model = model or config.DEEPSEEK_MODEL
        self._timeout = float(timeout if timeout is not None else config.LLM_TIMEOUT)
        self._retries = retries if retries is not None else config.LLM_RETRIES

    @staticmethod
    def _build_user_prompt(notice: Notice) -> str:
        if notice.content:
            body = notice.content[: config.MAX_CONTENT_CHARS]
            return f"公告标题:{notice.title}\n公告正文关键内容:{body}"
        return f"公告标题:{notice.title}\n公告正文关键内容:"

    def _ensure_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url=config.DEEPSEEK_BASE_URL,
                timeout=self._timeout,
            )
        return self._client

    def summarize(self, notice: Notice) -> Summary:
        if notice.content:
            source = "content"
        else:
            source = "title"

        user_prompt = self._build_user_prompt(notice)

        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = self._ensure_client().chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    timeout=self._timeout,
                )
                return self._parse(resp, source)
            except Exception as e:  # SDK 异常/超时/解析失败统一包装后重试
                if isinstance(e, SummarizeError):
                    last_exc = e
                else:
                    wrapped = SummarizeError(f"摘要调用失败: {e}")
                    wrapped.__cause__ = e
                    last_exc = wrapped
                logger.warning("摘要失败(第 %d/%d 次): %s", attempt + 1, self._retries + 1, e)
                if attempt < self._retries:
                    time.sleep(0.5 * (attempt + 1))
        raise SummarizeError(f"摘要重试耗尽({self._retries + 1} 次): {last_exc}") from last_exc

    def _parse(self, resp, source: str) -> Summary:
        try:
            data = json.loads(resp.choices[0].message.content)
            raw_points = data.get("key_points") or []
            if not isinstance(raw_points, list):
                raw_points = [raw_points]
            return Summary(
                importance=str(data["importance"]).strip(),
                sentiment=str(data["sentiment"]).strip(),
                summary=str(data["summary"]).strip(),
                key_points=[str(p).strip() for p in raw_points if str(p).strip()],
                content_source=source,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise SummarizeError(f"摘要解析失败: {e}") from e

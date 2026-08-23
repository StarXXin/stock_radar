"""数据模型(dataclass)。

`Notice` 贯穿采集→去重→摘要→推送全流程;`RawNotice` 是抓取到的原始载荷;
`Summary` 为 AI 的结构化结果。
"""

import hashlib
from dataclasses import dataclass, field


def make_id(code: str, date: str, title: str) -> str:
    raw = f"{code}|{date}|{title}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


@dataclass
class RawNotice:
    """notice_fetcher 抓到的原始载荷,交由 notice_parser 解析成文本。"""

    kind: str  # "html"(含纯文本正文)或 "pdf"
    text: str = ""  # html/纯文本载荷
    data: bytes | None = None  # pdf 二进制载荷


@dataclass
class Summary:
    """AI 对公告的结构化判断(仅客观描述,不含投资建议)。"""

    importance: str  # 高 / 中 / 低
    sentiment: str  # 利好 / 利空 / 中性 / 关注
    summary: str  # 一句话客观摘要
    key_points: list[str] = field(default_factory=list)  # 关键事实要点
    content_source: str = "title"  # content / title / rule(例行预滤)


@dataclass
class Notice:
    """一条公告。id 缺省时由 code|date|title 生成,保证去重稳定。"""

    code: str
    name: str
    title: str
    date: str
    url: str
    id: str = ""
    content: str | None = None  # 关键正文(过滤后,喂给 AI;取不到则降级用标题)
    summary: Summary | None = None  # AI 摘要(富化阶段填充)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = make_id(self.code, self.date, self.title)

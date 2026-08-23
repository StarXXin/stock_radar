"""数据模型(dataclass)。

`Notice` 贯穿采集→去重→摘要→推送全流程;`RawNotice` 是抓取到的原始载荷;
`Summary` 为 AI 的结构化结果。
"""

import hashlib
import re
from dataclasses import dataclass, field

_DATE_RE = re.compile(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})")


def normalize_date(raw: str) -> str:
    """把各数据源的日期字符串规整为 YYYY-MM-DD。

    东财/巨潮可能返回 '2026-07-10'、'2026-07-10 00:00:00'、'2026/07/10' 等;
    跨源去重 key 含 date,格式不一致会导致同一公告重复推送。无法解析时原样返回。
    """
    m = _DATE_RE.search(raw or "")
    if not m:
        return (raw or "").strip()
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def make_id(code: str, date: str, title: str) -> str:
    raw = f"{code}|{normalize_date(date)}|{title}"
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
        # 日期统一规整为 YYYY-MM-DD:跨源去重 key 与展示都依赖一致格式
        self.date = normalize_date(self.date)
        if not self.id:
            self.id = make_id(self.code, self.date, self.title)

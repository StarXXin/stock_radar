"""配置中心。全项目统一从此模块读取配置(仅模块级常量,无可变全局)。"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


# --- 路径 ---
DATA_DIR: Path = Path(__file__).parent / "data"
DB_PATH: Path = DATA_DIR / "pushed.db"
LOG_FILE: Path = Path(os.getenv("LOG_FILE", str(DATA_DIR / "stock_radar.log")))
CONTENT_CACHE_DIR: Path = Path(os.getenv("CONTENT_CACHE_DIR", str(DATA_DIR / "content_cache")))

# --- 大模型(DeepSeek,OpenAI 兼容) ---
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# --- 推送 ---
PUSHPLUS_TOKEN: str = os.getenv("PUSHPLUS_TOKEN", "")

# --- 自选股与采集 ---
# WATCHLIST 支持 "代码" 或 "代码=推送阈值"(如 600519=低,表示该股低重要性也推);
# 未标注阈值的股票用 PUSH_MIN_IMPORTANCE。解析结果见 WATCHLIST_CODES / WATCHLIST_THRESHOLDS。
WATCHLIST: list[str] = [c.strip() for c in os.getenv("WATCHLIST", "").split(",") if c.strip()]
WATCHLIST_CODES: list[str] = []
WATCHLIST_THRESHOLDS: dict[str, str] = {}
for _item in WATCHLIST:
    _code, _, _thresh = _item.partition("=")
    _code = _code.strip()
    if not _code:
        continue
    WATCHLIST_CODES.append(_code)
    if _thresh.strip():
        WATCHLIST_THRESHOLDS[_code] = _thresh.strip()
LOOKBACK_DAYS: int = int(os.getenv("LOOKBACK_DAYS", "3"))
DATA_SOURCE: str = os.getenv("DATA_SOURCE", "eastmoney")

# --- 正文抓取 ---
FETCH_CONTENT: bool = _as_bool(os.getenv("FETCH_CONTENT", "true"))
MAX_CONTENT_CHARS: int = int(os.getenv("MAX_CONTENT_CHARS", "3000"))

# --- 关键词过滤:先抽取含关键词的关键正文,再喂给 AI ---
_DEFAULT_KEYWORDS = [
    "中标", "合同", "回购", "减持", "增持",
    "业绩", "诉讼", "处罚", "并购", "重组", "分红",
]
KEYWORDS: list[str] = [
    k.strip() for k in os.getenv("KEYWORDS", "").split(",") if k.strip()
] or _DEFAULT_KEYWORDS

# --- 智能推送阈值:低于该重要性的公告不推送(低/中/高) ---
PUSH_MIN_IMPORTANCE: str = os.getenv("PUSH_MIN_IMPORTANCE", "中")

# --- 富化(正文抓取+AI摘要)并发数:1 为串行;过大易触发 LLM 限速 ---
ENRICH_CONCURRENCY: int = max(1, int(os.getenv("ENRICH_CONCURRENCY", "4")))

# --- 例行公告标题预滤:命中则跳过 AI,标为低重要性 ---
ROUTINE_TITLE_FILTER: bool = _as_bool(os.getenv("ROUTINE_TITLE_FILTER", "true"))
# 逗号分隔正则;为空则用 title_rules 内置默认
_ROUTINE_ENV = [p.strip() for p in os.getenv("ROUTINE_TITLE_PATTERNS", "").split(",") if p.strip()]
ROUTINE_TITLE_PATTERNS: list[str] = _ROUTINE_ENV  # 空列表时 title_rules 回退默认

# --- 失败告警:采集/推送等关键失败时经推送渠道发告警消息(默认关,配 Token 后可开) ---
ALERT_ON_ERROR: bool = _as_bool(os.getenv("ALERT_ON_ERROR", "false"))
# --- 心跳:距上次"有产出"的运行超过 N 天时发一条提醒(捕获定时任务静默挂掉),0=关 ---
HEARTBEAT_DAYS: int = max(0, int(os.getenv("HEARTBEAT_DAYS", "0")))

# --- 推送分页:单条消息最多条数/字符,超出则拆多条 ---
PUSH_MAX_PER_MESSAGE: int = int(os.getenv("PUSH_MAX_PER_MESSAGE", "8"))
PUSH_MAX_CHARS: int = int(os.getenv("PUSH_MAX_CHARS", "12000"))

# --- 外部请求 ---
REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "15"))
HTTP_RETRIES: int = int(os.getenv("HTTP_RETRIES", "2"))
# 大模型调用超时(秒)。生成长 JSON 常超过普通 HTTP 超时,独立给更长默认值
LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))
# 摘要失败重试次数(带退避),重试耗尽才走兜底文案
LLM_RETRIES: int = int(os.getenv("LLM_RETRIES", "2"))
# 熔断:富化时连续 N 条真实 AI 摘要均失败则中止本轮剩余摘要(疑似服务/网络故障),0=关
LLM_CIRCUIT_BREAKER: int = max(0, int(os.getenv("LLM_CIRCUIT_BREAKER", "5")))
# 单轮 LLM 调用上限(条数,含重试前的原始调用):控制积压时的费用,0=不限
LLM_MAX_CALLS_PER_RUN: int = max(0, int(os.getenv("LLM_MAX_CALLS_PER_RUN", "50")))

# --- 摘要缓存版本:调 KEYWORDS/prompt 等影响摘要结果的配置后 +1 使旧缓存失效 ---
SUMMARY_CACHE_VERSION: int = int(os.getenv("SUMMARY_CACHE_VERSION", "1"))

# --- 过期清理:本地去重库与正文缓存保留天数,0=不清理 ---
RETENTION_DAYS: int = max(0, int(os.getenv("RETENTION_DAYS", "90")))

# --- 日志 ---
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

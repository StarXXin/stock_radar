import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK,避免中文乱码

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import config
import notice_parser
import push_policy
import render
import text_filter
import title_rules
from exceptions import ConfigError, DataSourceError, NotifyError, StorageError, SummarizeError
from logging_setup import setup_logging
from models import Notice, Summary
from notice_fetcher import NoticeFetcher
from notifier import PushPlusNotifier
from sources import get_source
from store import Store
from summarizer import Summarizer

logger = logging.getLogger(__name__)


def _warn_config() -> None:
    """启动时软校验:缺 Token 只 warning(无 Token 仍可控制台输出)。"""
    if not config.PUSHPLUS_TOKEN:
        logger.warning("未配置 PUSHPLUS_TOKEN,仅控制台输出")


def _require_api_key() -> bool:
    """缺 DEEPSEEK_API_KEY 时硬退出:否则每条摘要失败、兜底'中'会全量误推送。"""
    if not config.DEEPSEEK_API_KEY:
        logger.error("未配置 DEEPSEEK_API_KEY,拒绝运行(避免摘要失败导致全量误推送)")
        print("错误: 未配置 DEEPSEEK_API_KEY,请在 .env 中填写")
        return False
    return True


class _LlmGuard:
    """LLM 熔断器 + 单轮调用预算。

    - 连续 LLM_CIRCUIT_BREAKER 条真实摘要均失败 → trip(),中止本轮剩余摘要(疑似服务故障);
    - 原始调用次数达 LLM_MAX_CALLS_PER_RUN → 预算耗尽,同样中止。
    两者都可通过配置设 0 关闭。被中止的公告本轮不标记,下次运行自动重试。
    """

    def __init__(self) -> None:
        self.calls = 0  # 真实 AI 摘要的原始调用条数(不含内部重试)
        self.consecutive_failures = 0
        self.tripped_reason: str | None = None

    def record_call(self) -> bool:
        """记录一次即将发起的真实调用;返回 False 表示预算已耗尽应跳过。"""
        limit = config.LLM_MAX_CALLS_PER_RUN
        if limit and self.calls >= limit:
            self.tripped_reason = self.tripped_reason or f"单轮调用达上限 {limit} 条"
            return False
        self.calls += 1
        return True

    def record_result(self, ok: bool) -> bool:
        """记录结果;返回 False 表示熔断触发应停止后续调用。"""
        breaker = config.LLM_CIRCUIT_BREAKER
        self.consecutive_failures = 0 if ok else self.consecutive_failures + 1
        if not ok and breaker and self.consecutive_failures >= breaker:
            self.tripped_reason = f"连续 {self.consecutive_failures} 条摘要失败"
            return False
        return True


def _enrich(
    notice: Notice,
    fetcher: NoticeFetcher,
    summarizer: Summarizer,
    store: Store,
    guard: _LlmGuard,
) -> str:
    """富化:标题规则预滤 → (可选)正文 → AI 摘要(缓存+熔断+预算)。

    返回 "ok" / "fallback"(兜底,不写缓存) / "skipped"(被熔断/预算跳过,未标记可重试)。
    """
    routine = title_rules.try_routine_summary(notice.title)
    if routine is not None:
        logger.info("例行预滤跳过AI %s 标题=%s", notice.code, notice.title)
        notice.summary = routine
        return "ok"

    if config.FETCH_CONTENT:
        try:
            raw = fetcher.fetch(notice)
            if raw is not None:
                text = notice_parser.parse(raw)
                notice.content = text_filter.extract_key_content(text, config.KEYWORDS) or None
        except Exception as e:  # 正文处理为 best-effort,失败降级用标题
            logger.warning("正文处理异常,降级用标题 %s: %s", notice.code, e)

    # 摘要缓存命中直接用(推送失败重跑/定时重叠时省一次 LLM 调用)
    try:
        cached = store.get_summary(notice.id)
    except StorageError as e:
        logger.warning("读取摘要缓存失败,继续正常摘要 %s: %s", notice.code, e)
        cached = None
    if cached is not None:
        logger.info("摘要命中缓存 %s 标题=%s", notice.code, notice.title)
        notice.summary = cached
        return "ok"

    # 熔断/预算检查放在缓存之后:命中缓存的条目不受影响
    if guard.tripped_reason or not guard.record_call():
        logger.warning("LLM 已熔断/预算耗尽(%s),跳过摘要 %s", guard.tripped_reason, notice.id)
        return "skipped"

    try:
        notice.summary = summarizer.summarize(notice)
    except SummarizeError as e:
        logger.warning("摘要失败,兜底后仍推送 %s: %s", notice.code, e)
        notice.summary = Summary(
            importance="中",
            sentiment="关注",
            summary="(摘要失败,建议人工查看原文)",
            key_points=[],
        )
        guard.record_result(False)  # 兜底结果不写缓存,下次运行重新摘要
        return "fallback"
    guard.record_result(True)

    try:
        store.save_summary(notice.id, notice.summary)
    except StorageError as e:
        logger.warning("写入摘要缓存失败(不影响本次推送) %s: %s", notice.code, e)
    return "ok"


def _safe_mark(store: Store, notice: Notice) -> None:
    try:
        store.mark_pushed(notice)
    except StorageError as e:
        logger.warning("标记已处理失败 %s: %s", notice.id, e)


def _alert(notifier: PushPlusNotifier, message: str) -> None:
    """关键失败时发告警消息(ALERT_ON_ERROR 开且配了 Token 才发);告警自身失败只记日志。"""
    if not config.ALERT_ON_ERROR or not notifier._token:
        return
    try:
        notifier.notify("stock_radar 运行告警", message)
    except NotifyError as e:
        logger.warning("发送告警消息失败(忽略): %s", e)


def _check_heartbeat(notifier: PushPlusNotifier) -> None:
    """心跳:距上次运行超过 HEARTBEAT_DAYS 天则发提醒并刷新时间戳。

    时间戳记在 data/last_run;每轮 run() 开头检查、结尾更新——
    若定时任务静默挂掉(进程没跑/启动即崩),时间戳不再刷新,下次手动运行即触发提醒。
    """
    if config.HEARTBEAT_DAYS <= 0:
        return
    stamp_file = config.DATA_DIR / "last_run"
    now = datetime.now()
    try:
        if stamp_file.exists():
            last = datetime.fromisoformat(stamp_file.read_text(encoding="utf-8").strip())
            silent_days = (now - last).days
            if silent_days >= config.HEARTBEAT_DAYS and notifier._token:
                try:
                    notifier.notify(
                        "stock_radar 心跳提醒",
                        f"距上次成功运行已 {silent_days} 天,请检查定时任务是否正常",
                    )
                except NotifyError as e:
                    logger.warning("发送心跳提醒失败(忽略): %s", e)
        stamp_file.parent.mkdir(parents=True, exist_ok=True)
        stamp_file.write_text(now.isoformat(timespec="seconds"), encoding="utf-8")
    except OSError as e:
        logger.warning("心跳时间戳读写失败(忽略): %s", e)


def _fetch_from_sources() -> list[Notice]:
    """按 DATA_SOURCE 采集(逗号分隔可多源合并)。单源失败 warning 继续;全失败抛错。

    多源结果按 (code,date,title) 去重——同一公告两个渠道都会报。
    """
    names = [s.strip() for s in config.DATA_SOURCE.split(",") if s.strip()]
    notices: list[Notice] = []
    seen: set[tuple[str, str, str]] = set()
    ok_count = 0
    last_err: Exception | None = None
    for name in names:
        try:
            source = get_source(name)
            for n in source.fetch_recent(config.WATCHLIST_CODES, config.LOOKBACK_DAYS):
                key = (n.code, n.date, n.title)
                if key in seen:
                    continue
                seen.add(key)
                notices.append(n)
            ok_count += 1
        except (ConfigError, DataSourceError) as e:
            logger.warning("数据源 %s 采集失败: %s", name, e)
            last_err = e
    if ok_count == 0:
        raise DataSourceError(f"全部数据源采集失败({len(names)} 个): {last_err}")
    return notices


def run(dry_run: bool = False, source_override: str | None = None, days: int | None = None) -> None:
    """执行一轮完整流程。

    - dry_run: 只采集+摘要+控制台打印,不推送、不标记已处理(下次运行会再处理一遍);
      同时忽略摘要熔断/预算(避免调试时被计数干扰)。
    - source_override / days: 临时覆盖 DATA_SOURCE / LOOKBACK_DAYS,优先于 .env。
    """
    if source_override:
        config.DATA_SOURCE = source_override
    if days is not None:
        config.LOOKBACK_DAYS = max(1, days)

    setup_logging()

    if not config.WATCHLIST_CODES:
        logger.error("WATCHLIST 为空,请先在 .env 里配置自选股代码")
        return

    if not dry_run and not _require_api_key():
        return

    _warn_config()

    fetcher = NoticeFetcher()
    summarizer = Summarizer()
    notifier = PushPlusNotifier()
    store = Store()

    # ① 采集(支持多源合并)
    _check_heartbeat(notifier)  # 心跳检查(HEARTBEAT_DAYS>0 时启用)
    if config.RETENTION_DAYS > 0:  # 过期清理 best-effort,失败不影响主流程
        try:
            store.cleanup(config.RETENTION_DAYS)
            fetcher.cleanup_cache(config.RETENTION_DAYS)
        except StorageError as e:
            logger.warning("过期清理失败(忽略): %s", e)

    try:
        notices = _fetch_from_sources()
    except DataSourceError as e:
        logger.error("采集失败: %s", e)
        _alert(notifier, f"采集失败,本轮未检查公告: {e}")
        return

    # ② 去重
    try:
        new_notices = [n for n in notices if store.is_new(n.id)]
    except StorageError as e:
        logger.error("去重查询失败: %s", e)
        return

    if not new_notices:
        logger.info("本次没有新公告")
        print("本次没有新公告")
        return

    # ③ 富化(规则预滤 / 正文 / AI 摘要;带缓存+熔断+预算;并发执行,单条失败互不影响)
    guard = _LlmGuard()
    if len(new_notices) == 1 or config.ENRICH_CONCURRENCY == 1:
        enrich_results = [
            _enrich(n, fetcher, summarizer, store, guard) for n in new_notices
        ]
    else:
        with ThreadPoolExecutor(max_workers=config.ENRICH_CONCURRENCY) as pool:
            enrich_results = list(
                pool.map(
                    lambda n: _enrich(n, fetcher, summarizer, store, guard),
                    new_notices,
                )
            )
    if guard.tripped_reason:
        logger.warning("LLM 熔断触发: %s,本轮 %d 条被跳过(下次运行自动重试)",
                       guard.tripped_reason,
                       sum(1 for r in enrich_results if r == "skipped"))
        _alert(notifier, f"LLM 摘要中止({guard.tripped_reason}),部分公告下次重试")

    # ④ 智能过滤:低于阈值重要性的不推送,但仍标记已处理(避免下次重复摘要);
    # 被熔断/预算跳过的条目不标记,下次运行重新处理
    to_push: list[Notice] = []
    filtered: list[Notice] = []
    for n, result in zip(new_notices, enrich_results, strict=True):
        if result == "skipped":
            continue
        assert n.summary is not None
        (to_push if push_policy.should_push(n.summary, code=n.code) else filtered).append(n)

    for n in filtered:
        assert n.summary is not None
        logger.info("过滤不推送 %s 重要性=%s 标题=%s", n.code, n.summary.importance, n.title)
        if not dry_run:
            _safe_mark(store, n)

    # dry-run 模式:打印全部结果后直接返回,不推送、不标记
    if dry_run:
        print(render.render_blocks(new_notices))
        print(f"\n[dry-run] 共 {len(new_notices)} 条(达阈值 {len(to_push)} 条),未推送未标记")
        return

    if not to_push:
        logger.info("本次无达到推送阈值的公告(已过滤 %d 条)", len(filtered))
        print("本次没有需要推送的公告")
        return

    # ⑤ 推送(分页:条数/字符超限拆多条;每页成功即标记该页公告,失败页下次重试)
    pages = render.paginate_notices(to_push)
    total_pages = len(pages)
    pushed_count = 0
    for i, page in enumerate(pages, start=1):
        if total_pages == 1:
            title = f"自选股情报 · {len(to_push)} 条新公告"
        else:
            title = f"自选股情报 · {len(to_push)} 条({i}/{total_pages})"
        try:
            notifier.notify(title, render.render_blocks(page))
        except NotifyError as e:
            logger.error(
                "第 %d/%d 页推送失败: %s (已推送 %d 条已标记;失败页下次自动重试)",
                i, total_pages, e, pushed_count,
            )
            _alert(notifier, f"第 {i}/{total_pages} 页推送失败(下次自动重试): {e}")
            break
        for n in page:
            _safe_mark(store, n)
        pushed_count += len(page)

    logger.info("本次共推送并标记 %d 条公告", pushed_count)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="自选股公告雷达(单次运行)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只采集+摘要+控制台打印,不推送不标记(调试/验证数据源用)",
    )
    parser.add_argument("--source", help="临时覆盖 DATA_SOURCE(如 eastmoney,cninfo)", default=None)
    parser.add_argument("--days", type=int, help="临时覆盖 LOOKBACK_DAYS 回看天数", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    _args = _parse_args()
    run(dry_run=_args.dry_run, source_override=_args.source, days=_args.days)

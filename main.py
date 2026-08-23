import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK,避免中文乱码

import logging

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


def _enrich(notice: Notice, fetcher: NoticeFetcher, summarizer: Summarizer, store: Store) -> None:
    """富化:标题规则预滤 → (可选)正文 → AI 摘要(带缓存,避免重跑重复调 LLM)。"""
    routine = title_rules.try_routine_summary(notice.title)
    if routine is not None:
        logger.info("例行预滤跳过AI %s 标题=%s", notice.code, notice.title)
        notice.summary = routine
        return

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
        return

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
        return  # 兜底结果不写缓存,下次运行重新摘要

    try:
        store.save_summary(notice.id, notice.summary)
    except StorageError as e:
        logger.warning("写入摘要缓存失败(不影响本次推送) %s: %s", notice.code, e)


def _safe_mark(store: Store, notice: Notice) -> None:
    try:
        store.mark_pushed(notice)
    except StorageError as e:
        logger.warning("标记已处理失败 %s: %s", notice.id, e)


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
            for n in source.fetch_recent(config.WATCHLIST, config.LOOKBACK_DAYS):
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


def run() -> None:
    setup_logging()

    if not config.WATCHLIST:
        logger.error("WATCHLIST 为空,请先在 .env 里配置自选股代码")
        return

    if not _require_api_key():
        return

    _warn_config()

    fetcher = NoticeFetcher()
    summarizer = Summarizer()
    notifier = PushPlusNotifier()
    store = Store()

    # ① 采集(支持多源合并)
    try:
        notices = _fetch_from_sources()
    except DataSourceError as e:
        logger.error("采集失败: %s", e)
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

    # ③ 富化(规则预滤 / 正文 / AI 摘要,带缓存)
    for n in new_notices:
        _enrich(n, fetcher, summarizer, store)

    # ④ 智能过滤:低于阈值重要性的不推送,但仍标记已处理(避免下次重复摘要)
    to_push: list[Notice] = []
    skipped: list[Notice] = []
    for n in new_notices:
        (to_push if push_policy.should_push(n.summary) else skipped).append(n)

    for n in skipped:
        logger.info("过滤不推送 %s 重要性=%s 标题=%s", n.code, n.summary.importance, n.title)
        _safe_mark(store, n)

    if not to_push:
        logger.info("本次无达到推送阈值的公告(已过滤 %d 条)", len(skipped))
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
            break
        for n in page:
            _safe_mark(store, n)
        pushed_count += len(page)

    logger.info("本次共推送并标记 %d 条公告", pushed_count)


if __name__ == "__main__":
    run()

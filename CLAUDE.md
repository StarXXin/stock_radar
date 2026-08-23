# stock_radar — 自选股公告雷达

A股自选股公告监控工具：采集公告 → 去重 → 抓正文 → AI 摘要（DeepSeek）→ 重要性过滤 → PushPlus 推送。单次运行 CLI，靠外部定时任务调度。

**详细需求与设计文档见《[需求说明.md](./需求说明.md)》**（模块表、配置全表、处理流程图、定时任务示例都在里面），本文件只放快速上手和开发约定。

## 运行 / 测试

项目用 **uv** 管理，Python 3.12 虚拟环境在 `.venv/`：

```bash
uv sync                        # 首次/依赖变更后同步环境
uv run pytest -q               # 全部 mock，无真实网络/LLM 调用，应全绿（117 用例）
uv run python main.py          # 单次执行；配置读 .env（全部配置项见 .env.example）
uv run python main.py --dry-run   # 只采集+摘要+控制台打印，不推送不标记
uv run ruff check .            # lint
uv run mypy .                  # 类型检查（生产代码强制注解；tests 已排除）
```

提交前三项都应通过。缺 DEEPSEEK_API_KEY 时程序会拒绝运行（防全量误推送），`--dry-run` 下例外。推到 GitHub 后 `.github/workflows/ci.yml` 自动跑三项检查。

## 六步流程（main.run）

① `_fetch_from_sources` 多源采集（`DATA_SOURCE` 逗号分隔可多源合并，单源失败继续）+ 心跳检查 + `RETENTION_DAYS` 过期清理 → ② `store.py` SQLite 去重 → ③ `_enrich` 线程池并发（`_LlmGuard` 熔断+预算）：`title_rules` 例行预滤(命中跳过AI) → 摘要缓存查询(带版本) → `notice_fetcher`(线程安全 Session+缓存) → `notice_parser` → `text_filter` 关键词抽取 → `summarizer` DeepSeek JSON 摘要(超时+重试) → 成功写摘要缓存 → ④ `push_policy` 阈值过滤(全局+按股覆盖) → ⑤ `render` 分页渲染 + `notifier` 推送，**每页成功即逐条标记**，失败页下次重试。

## 开发约束（改动前必读）

- Python ≥3.12（uv 管理），全项目类型注解（生产代码 mypy 强制）；数据模型用 dataclass；禁止全局可变变量。依赖变更后 `uv add/remove` + 提交 `uv.lock`。
- 配置统一从 `config.py` 读（`.env` 加载）；新增配置项要同步 `.env.example` 和《需求说明.md》§7 表格。
- 所有外部请求必须设超时（HTTP 用 `REQUEST_TIMEOUT`，LLM 用 `LLM_TIMEOUT`）。
- 异常分类见 `exceptions.py`；所有异常记日志不得静默。降级语义：
  - 数据源回看窗口内**全部单元失败**才抛 `DataSourceError`（不能当"无新公告"）；多源时全部源失败才退出；
  - 正文抓取失败 → 降级用标题摘要（best-effort）；
  - AI 摘要失败 → 重试 `LLM_RETRIES` 次 → 兜底"中/关注"占位 Summary，仍推送，**兜底不写缓存**；
  - **推送失败 → 该页不标记已推送**，下次自动重试；已推送页照常标记。
- 新增功能优先保持模块职责单一，不改 `main.py` 整体流程。
- AI 输出必须是 JSON（`response_format: json_object`），且只客观描述、严禁投资建议。
- LLM 有熔断保护（连续失败 `LLM_CIRCUIT_BREAKER`=5 条中止本轮）和单轮预算（`LLM_MAX_CALLS_PER_RUN`=50），被中止的公告不标记、下次重试；改 prompt 或 KEYWORDS 后把 `SUMMARY_CACHE_VERSION` +1 使旧缓存失效。
- 改 `store.py`/`models.py` 时注意 SQLite 两张表：`pushed`（去重）、`summaries`（摘要缓存，按 notice id + 版本号）。

## 扩展点

- **新数据源**：继承 `sources/base.NoticeSource`，在 `sources/__init__.py` 的 `_REGISTRY` 登记，列顺序注意东财是按位置取（`iloc`）、巨潮按列名。多源合并逻辑在 `main._fetch_from_sources`。
- **现有三源**：`eastmoney`(按日全市场,缺北交所改码股) / `cninfo`(按股,沪深京全覆盖,新旧码都认) / `sse_official`(上交所官方直连,沪市第三重保障,PDF 直链)。北交所股票须用 920 新码且配 cninfo 源。
- **新推送渠道**：仿照 `notifier.PushPlusNotifier` 实现 `notify(title, content)`，硬失败抛 `NotifyError`。
- **例行公告正则**：`title_rules._DEFAULT_PATTERNS`，可用 env `ROUTINE_TITLE_PATTERNS` 覆盖。
- **按股阈值**：`WATCHLIST` 支持 `代码=低/中/高` 语法，解析在 `config.WATCHLIST_THRESHOLDS`，消费在 `push_policy.should_push(code=...)`。

## 易踩的坑

- 东财/巨潮接口均为未公开端点，改版时先看 `data/stock_radar.log` 的 warning 定位是采集还是正文环节。
- 正文缓存目录 `data/content_cache/` 与两张 SQLite 表按 `RETENTION_DAYS`（默认 90 天，0=关）自动清理。
- 公告去重 ID = `md5(code|date|title)`，改标题格式会导致重复推送。
- 富化默认并发 4（`ENRICH_CONCURRENCY`），LLM 限速报错多时可降为 1。

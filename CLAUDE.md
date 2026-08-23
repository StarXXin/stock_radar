# stock_radar — 自选股公告雷达

A股自选股公告监控工具：采集公告 → 去重 → 抓正文 → AI 摘要（DeepSeek）→ 重要性过滤 → PushPlus 推送。单次运行 CLI，靠外部定时任务调度。

**详细需求与设计文档见《[需求说明.md](./需求说明.md)》**（模块表、配置全表、处理流程图、定时任务示例都在里面），本文件只放快速上手和开发约定。

## 运行 / 测试

```bash
# 注意：机器默认 python 是 3.7，必须用 py -3.11（项目要求 >=3.11）
py -3.11 -m pytest -q          # 全部 mock，无真实网络/LLM 调用，应全绿
py -3.11 main.py               # 单次执行；配置读 .env（模板见 .env.example）
```

## 六步流程（main.run）

① `sources/` 采集 → ② `store.py` SQLite 去重 → ③ `_enrich`：`title_rules` 例行预滤(命中跳过AI) → `notice_fetcher`(带缓存) → `notice_parser` → `text_filter` 关键词抽取 → `summarizer` DeepSeek JSON 摘要 → ④ `push_policy` 重要性阈值过滤 → ⑤ `render` 分页渲染 + `notifier` 推送 → ⑥ 标记已推送。

## 开发约束（改动前必读）

- Python ≥3.11，全项目类型注解；数据模型用 dataclass；禁止全局可变变量。
- 配置统一从 `config.py` 读（`.env` 加载）；新增配置项要同步 `.env.example` 和《需求说明.md》§7 表格。
- 所有外部请求必须设超时（HTTP 用 `REQUEST_TIMEOUT`，LLM 用 `LLM_TIMEOUT`）。
- 异常分类见 `exceptions.py`；所有异常记日志不得静默。降级语义：
  - 数据源回看窗口内**全部单元失败**才抛 `DataSourceError`（不能当"无新公告"）；
  - 正文抓取失败 → 降级用标题摘要（best-effort）；
  - AI 摘要失败 → 兜底"中/关注"占位 Summary，仍推送；
  - **推送失败 → 不标记已推送**，下次自动重试。
- 新增功能优先保持模块职责单一，不改 `main.py` 整体流程。
- AI 输出必须是 JSON（`response_format: json_object`），且只客观描述、严禁投资建议。

## 扩展点

- **新数据源**：继承 `sources/base.NoticeSource`，在 `sources/__init__.py` 的 `_REGISTRY` 登记，列顺序注意东财是按位置取（`iloc`）、巨潮按列名。
- **新推送渠道**：仿照 `notifier.PushPlusNotifier` 实现 `notify(title, content)`，硬失败抛 `NotifyError`。
- **例行公告正则**：`title_rules._DEFAULT_PATTERNS`，可用 env `ROUTINE_TITLE_PATTERNS` 覆盖。

## 易踩的坑

- 东财/巨潮接口均为未公开端点，改版时先看 `data/stock_radar.log` 的 warning 定位是采集还是正文环节。
- 正文缓存目录 `data/content_cache/` 只增不清，调试时可手动删除。
- 公告去重 ID = `md5(code|date|title)`，改标题格式会导致重复推送。

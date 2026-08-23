# stock_radar — 自选股公告雷达

[![CI](https://github.com/StarXXin/stock_radar/actions/workflows/ci.yml/badge.svg)](https://github.com/StarXXin/stock_radar/actions/workflows/ci.yml)

A股自选股公告监控与智能提醒工具：定时抓取自选股公告 → 抓取正文（关键词预过滤）→ DeepSeek 大模型结构化摘要（重要性/倾向）→ 按重要性阈值过滤 → PushPlus 推送到微信。

## 功能特性

- **多源采集**：东方财富 / 巨潮资讯 / 上交所官方，支持多源合并互补（`DATA_SOURCE=eastmoney,cninfo,sse_official`），单源故障不中断
- **降噪省费**：例行公告标题预滤跳过 AI；关键词抽取关键正文再送模型；摘要结果本地缓存（带版本失效）
- **智能推送**：全局 + 按股重要性阈值（`WATCHLIST=600519=低,000001`）；分页推送、逐页标记、失败自动重试
- **稳健可观测**：LLM 超时/重试/熔断/预算四重保护；失败告警 + 心跳提醒；分层异常 + 全量日志
- **本地 Web 控制台**：`uv run python -m webapp` 打开浏览器控制台（默认 http://127.0.0.1:8787）——推送历史与统计、网页编辑常用配置（写回 .env，下次运行生效）、按钮手动触发运行并实时看日志。仅监听本机且无鉴权，请勿改为 `0.0.0.0` 暴露到局域网
- **合规**：AI 仅客观描述公告，严禁投资建议

## 快速开始

使用 [uv](https://docs.astral.sh/uv/) 管理（自动创建 Python 3.12 虚拟环境、锁定依赖）：

```bash
uv sync                 # 创建 .venv 并安装全部依赖
cp .env.example .env    # 填入 DEEPSEEK_API_KEY 和 WATCHLIST(自选股代码)

uv run python main.py             # 单次运行
uv run python main.py --dry-run   # 只采集+摘要+控制台打印,不推送不标记
uv run python main.py --help      # 更多参数(--source/--days)
```

Windows 下也可直接双击/调用 `run_radar.bat`。

### 定时运行

Windows：管理员 PowerShell 执行 `.\install_task.ps1` 注册计划任务（每天 8:30 / 18:30，经 uv 运行）。
Linux/macOS：cron 示例见《需求说明.md》§8.1。

## 开发

```bash
uv sync --dev       # 含开发依赖(pytest/ruff/mypy)
uv run pytest -q    # 117 用例,全部 mock,无真实外呼
uv run ruff check .
uv run mypy .
```

详细设计文档：《[需求说明.md](./需求说明.md)》（架构、配置全表、处理流程、扩展指南）。

## License

MIT

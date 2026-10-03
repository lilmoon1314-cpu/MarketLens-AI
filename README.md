# MarketLens AI

中文优先的商品用户反馈分析项目，计划使用 LangGraph、GLiNER2、多阶段 LLM 分析与 Streamlit 展示淘宝商品评论中的问题和需求。

目前已实现 **F00：开发环境与项目骨架**、**F01：数据与 Agent 契约**、**F02：本地评论导入**。**F03：LangGraph离线闭环**也已完成，提供显式demo命令。淘宝采集、真实模型分析和Dashboard继续按计划实现。

## 本地开发

需要 Python 3.12、uv 和 Git。以下命令在仓库根目录执行；Windows PowerShell 可直接使用。

```powershell
uv sync --locked --group dev
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --no-sources
```

`uv sync` 创建独立的 `.venv`，安装已锁定的项目和开发依赖；测试默认不访问外部服务、不下载模型。CI 在 Windows 和 Linux 上执行同样的检查，并验证打包。

## 数据与 Agent 契约

公开类型位于 `marketlens.contracts`，包括 `AnalysisRequest`、`Review`、`SemanticReview`、三个 Agent 的输入输出及 `AnalysisState`。对象禁止额外字段，不隐式转换字符串数字；可空来源字段也必须显式提供。时间采用 UTC，未知值填 `null`；Python 调用传入带时区的 `datetime`，JSON 调用使用 `model_validate_json()` 解析 RFC3339 日期。

六个 Agent 入口及共享定义导出到 `docs/schemas/`，由 Pydantic 自动生成：

```powershell
uv run --locked python -m marketlens.contracts.export
uv run --locked pytest tests/unit/test_contracts.py -q
```

修改类型后重新导出并提交 Schema；测试检查导出文件一致性、Draft 2020-12 合法性与内部引用。Pydantic 额外检查非空白文本、UTC、来源必需输入、评论/标注 ID 匹配和主题图表限制。Schema 不执行这些跨字段或上下文规则；证据白名单、来源授权、商品主机/短链解析、数据集存在性及预算由后续对应服务验证。当前 URL 校验仅保证 HTTP(S) 格式，不授权采集。

## 本地评论导入

`marketlens.tools.collection.load_local_reviews(dataset_id, datasets, limit=1000)` 只读取调用方注册的 `dict[str, Path]`。CSV 必须有唯一列名和 `text` 列；JSONL 每行一个对象。文件为 UTF-8（可带 BOM），上限 10 MiB。可选字段为 `source_id`、`product_id`、`url`、`time`；未知值留空，日期必须包含时区，导入时转为 UTC。来源统一为 `local`，作者及额外列不进入业务对象。

正文做 NFKC 与空白归一化；同商品全文或相同来源 ID 保留第一条。无来源 ID 时用来源、商品 ID、正文计算 SHA256。结果包含 `reviews`、`raw_count`、`rejected_counts`；非法行、空文本、重复及超量分别计数，最多保留 1000 条。CSV 引号损坏导致行边界不可靠时拒绝整个文件；JSONL 语法错误逐行隔离。CLI用法见下节。

## 离线工作流（模拟模式）

```powershell
uv sync --locked --group dev --extra workflow
uv run --locked --extra workflow marketlens analyze --demo --input reviews.csv --product "示例商品" --goal "了解用户反馈"
uv run --locked --extra workflow pytest -q
```

CLI将输入文件注册到本次运行，再调用统一的 `AnalysisService`。`run(request)` 返回JSON报告；`stream(request)` 发出阶段进度，末事件包含报告。三个模拟Agent只验证契约与图编排，不产生真实模型分析。没有数据时返回 `insufficient_data`；坏文件/节点失败保留错误状态；少于4条时不调用模拟Analyst。模拟证据最多1条且严格低于30%，正式分层与token预算在F06实现。CLI成功/部分结果退出0，失败退出1，参数或依赖错误退出2。

运行时依赖通过LangGraph context注入，State只存可序列化数据。图API参考[LangGraph官方文档](https://docs.langchain.com/oss/python/langgraph/graph-api)。没有持久化、真实语义标注、真实LLM或可渲染统计数据；模拟ChartSpec仅验证输出传递。

## 可选依赖

按对应功能需要安装；安装依赖不代表功能已实现。默认开发环境不安装 PyTorch、模型权重或浏览器。

```powershell
uv sync --locked --group dev --extra workflow
uv sync --locked --group dev --extra llm
uv sync --locked --group dev --extra nlp
uv sync --locked --group dev --extra ui
uv sync --locked --group dev --extra collector
```

需要多组时在同一条命令中重复 `--extra`；uv 会按本次指定的组同步环境。GLiNER2 权重由后续模型功能显式加载。未来淘宝采集功能采用 Playwright；其浏览器安装与登录步骤在 F13 实现时说明，本轮不启动浏览器或采集评论。

## 配置

`.env.example` 列出后续功能使用的配置项；F00 尚不加载 `.env`。LLM 服务地址、密钥及模型由环境变量配置。淘宝评论将按用户指定的商品链接采集，登录状态保存在 `.local/` 的独立浏览器目录，不提交账号密码、Cookie、原始评论或运行数据库。

## 测试约定

自动测试位于 `tests/unit/`，后续集成测试位于 `tests/integration/`。测试命名为 `test_*.py`。`model_smoke` 与 `live_api` 为显式外部检查标记，默认排除；相应测试实现后可使用 `uv run --locked pytest -m model_smoke` 或 `-m live_api` 单独执行。

## 文档与贡献

- [PRD](MarketLens_AI_PRD_v0.1.md)：文件名保留，正文版本为 v0.2。
- [Tech Design Spec](docs/TECH_DESIGN_SPEC.md)：State、Agent契约、采集和分析设计。
- [开发计划](docs/DEVELOPMENT_PLAN.md)：一次一个功能及验收顺序。
- [进度记录](docs/PROGRESS.md)：验证结果、提交与推送状态。
- [贡献指南](AGENTS.md)：代码风格与交付约定。

每次只实现一个功能，完成必要验证后更新进度并提交、推送。frontend视觉验收截图保存在 `test/pic_test/`；当前功能无前端页面，不需要截图。

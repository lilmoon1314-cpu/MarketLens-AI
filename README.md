# MarketLens AI

中文优先的商品用户反馈分析项目，计划使用 LangGraph、GLiNER2、多阶段 LLM 分析与 Streamlit 展示淘宝商品评论中的问题和需求。

目前已实现 **F00：开发环境与项目骨架**、**F01：数据与 Agent 契约**。尚无评论采集、分析命令或 Dashboard；这些功能按开发计划逐项实现。

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

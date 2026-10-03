# MarketLens AI

中文优先的商品用户反馈分析项目，计划使用 LangGraph、GLiNER2、多阶段 LLM 分析与 Streamlit 展示淘宝商品评论中的问题和需求。

目前已实现 **F00：开发环境与项目骨架**、**F01：数据与 Agent 契约**、**F02：本地评论导入**。**F03：LangGraph离线闭环**和**F04：GLiNER2语义适配器**已完成，提供显式demo命令。F05—F10的统计、预算与三个真实Agent均已实现；淘宝采集、持久化和Dashboard继续按计划实现。

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

CLI将输入文件注册到本次运行，再调用统一的 `AnalysisService`。`run(request)` 返回JSON报告；`stream(request)` 发出阶段进度，末事件包含报告。三个模拟Agent只验证契约与图编排，不产生真实模型分析。没有数据时返回 `insufficient_data`；坏文件/节点失败保留错误状态；少于4条时不调用模拟Analyst。F06已接入正式分层与token预算；demo的语义标注仍由固定fixture提供。CLI成功/部分结果退出0，失败退出1，参数或依赖错误退出2。

运行时依赖通过LangGraph context注入，State只存可序列化数据。图API参考[LangGraph官方文档](https://docs.langchain.com/oss/python/langgraph/graph-api)。没有持久化或真实LLM。可注入SemanticAnalyzer验证真实语义+模拟Agent混合流程，报告仍标demo；ChartSpec尚无UI绑定。

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

## 本地语义适配器

```powershell
uv sync --locked --group dev --extra workflow --extra nlp
uv run --locked --extra workflow --extra nlp pytest tests/integration/test_gliner_smoke.py -m model_smoke -q
```

`SemanticAnalyzer().analyze(reviews)` 延迟加载CPU模型，进程内复用；首次下载约1.23GB权重到`.local/huggingface/hub`。模型ID与revision固定，使用GLiNER2 2.0.0 span架构。`GLiNERConfig`支持batch_size、char/whitespace切分、zh/en标签描述和缓存目录。普通测试通过注入backend，不下载模型。

返回逐评论`SemanticReview`，包括实际分数、processed/truncated。缺失分数保留null；sentiment低于0.50记unknown，主题低于0.40剔除、无命中记other且不伪造其分数。长文本按实际Schema编码容量截断推理视图；批次失败减半重试一次。模型加载失败向调用方报错，不自动切模型或调用LLM。适配器可注入统一服务，F05统计与F06路由已接入；默认demo仍使用模拟语义。真实smoke与四组开发对比见[验证记录](docs/GLINER_DEVELOPMENT_CHECK.md)，广告和负面情绪分类存在已记录质量风险。

## 聚合统计

`aggregate_statistics(reviews, annotations, raw_count, rejected_counts)` 返回严格的 `Statistics` 契约。ID必须唯一且标注只属于当前评论；raw必须等于valid加拒绝数。缺失或失败标注进入unknown，不能归为neutral。spam保留在value分布和valid分母，情绪/主题使用排除spam的product_denominator；多主题评论可贡献多个计数，topic总数可大于分母。有效样本少于20条标记low_sample。计数由程序生成，模型不输出总体频次。此工具已接入统一图。

## 高价值预算路由

`select_reviews(reviews, annotations, budget)` 仅接受processed、actionable且value分数至少0.60的候选；有效评论N包含spam，独立上限为`max(0, (3*N-1)//10)`，1000条最多299条。按最高分主主题分层，主题并列按固定枚举，层内按value分数/ID稳定排序；先覆盖各层，再按剩余容量用最大余数分配。

`RoutingBudget`限制每批8000输入tokens（预留2000提示词/Schema）、2000输出tokens、20条和运行剩余60000 tokens。无tokenizer时按完整评论与标注JSON的UTF-8字节保守估算，报告明确estimated；过长评论整条跳过，保留原文，不能任意切证据。实际usage/重试费用已由F07累计，Planner等先前消耗须从remaining扣除。结果包含固定selected_ids、batches及未选计数；`selected_evidence`拒绝白名单外ID。

图现为Planner→导入→语义→统计/路由→有预算时Analyst→Visualization→报告。真实Analyst批次与合并已在F09实现，CLI仍demo，真实组件可通过服务显式注入；无候选时输出partial统计。

## 配置

`.env.example` 是无凭据模板，复制到忽略的 `.env` 再填写。F07的 `load_llm_config()` 默认读取仓库根目录 `.env`，进程环境变量优先；支持普通KEY=VALUE、单/双引号和export，不执行脚本或变量展开。LLM 服务地址、密钥及模型由环境变量配置。淘宝评论将按用户指定的商品链接采集，登录状态保存在 `.local/` 的独立浏览器目录，不提交账号密码、Cookie、原始评论或运行数据库。

## 结构化LLM适配器

```powershell
uv sync --locked --group dev --extra workflow --extra llm
uv run --locked --extra workflow --extra llm pytest -q
uv run --locked --extra workflow --extra llm pytest tests/integration/test_llm_smoke.py -m live_api -q --tb=no
```

显式live_api会访问已配置服务并产生用量；可用`MARKETLENS_ENV_FILE`指定配置文件。`StructuredLLM.generate(OutputContract, system, payload)`通过ChatOpenAI请求JSON，随后用Pydantic严格校验。默认json_mode兼容JSON对象接口，可显式设json_schema；不自动更换provider或输出模式。超时45秒，SDK重试关闭，临时网络/429/5xx或非法JSON最多应用层重试一次；永久错误不重试，错误信息不含原始服务异常。

每次调用前保守估计完整消息/Schema字节并预留输出，检查context/input/run上限；重试也收费并计数。服务返回有效usage时记录reported，无usage/网络失败保留estimated_reserved；不得将估计当精确账单。每次运行创建独立适配器，`remaining_tokens`供后续路由使用。实际服务需遵循标准Chat Completions字段，见[ChatOpenAI官方说明](https://docs.langchain.com/oss/python/integrations/chat/openai)。当前适配器独立可用，真实Planner已在F08接入；真实Analyst已在F09接入，Visualization继续F10。

## Research Planner

`PlannerAgent(llm).plan(PlannerInput)`返回计划与warnings；只允许请求来源和可用来源的交集。网络/Schema/越权失败使用产品名关键词和四个默认维度，记录planner_fallback；空交集直接失败，不虚构数据来源。提示词版本在`marketlens.prompts.planner`。

可通过`AnalysisService(..., planner=PlannerAgent(llm))`接入真实Planner；同一运行共享StructuredLLM账本，路由扣除Planner实测/预留消耗，遵守provider context/input/output限制。每个真实运行创建新的LLM/Planner实例。可逐个注入组件做混合验证（仍标demo）；完整真实模式由AnalysisService.real创建，三个Agent共享账本。

## Review Analyst与证据

`AnalystAgent(llm).analyze(AnalystInput, batches)`只接收路由选定评论，batches必须完整且不重复地划分该集合。按实际完整消息/Schema容量细分，每批最多20条；无法容纳的长评论整条跳过并记录warning。批次失败保留其他批结果，合并阶段只接收有效洞察，不能增加原文或评论ID。

每批只允许该批证据，合并只允许先前有效洞察的证据。含非法引用的洞察整体删除，摘要由确定性模板重建，避免残留无证据结论。合并失败用按kind/规范化title去重的结果；证据集合取并集，程序生成稳定insight_id与去重evidence_count。不同洞察可能共享证据，这些计数不能相加当作独立用户数。

`AnalysisService(..., planner=PlannerAgent(llm), analyst=AnalystAgent(llm))`要求共享同一运行的LLM实例；报告包含程序洞察计数、实际尝试送入的analyst_sent_ids、warnings和累计usage。部分失败标partial。提示词位于`prompts/analyst.py`；抽样洞察不代表总体发生率。真实Visualization与完整CLI模式已在F10实现。

## 图表配置与真实模式

`VisualizationAgent.configure()`只接收产品、语言、已有数据集描述与洞察标题，不接收评论正文。选择已存在且不重复的数据集，字段仅label/count；topic与洞察证据存在重叠，只允许bar，情绪/value可用donut。模型失败/非法配置回退为已有数据的默认柱状图；零数据不调用LLM。图表数字与中文标签均由服务端生成绑定，报告charts包含配置和data，不能执行模型代码。

```powershell
uv sync --locked --group dev --extra workflow --extra llm --extra nlp
uv run --locked --extra workflow --extra llm --extra nlp marketlens analyze --real --input reviews.jsonl --product "示例商品" --goal "了解反馈"
```

必须显式选择--real或--demo。真实模式读取忽略.env，使用CPU模型和三个真实Agent；会产生API用量，首次下载模型。数据不足/部分失败仍生成可用统计图，报告标partial；完成状态不代表准确率验收。stdout为JSON，上游模型加载输出不污染它。每次真实运行创建新服务，持久化在F11、页面图表渲染在F12实现。

## 测试约定

自动测试位于 `tests/unit/`，后续集成测试位于 `tests/integration/`。测试命名为 `test_*.py`。`model_smoke` 与 `live_api` 为显式外部检查标记，默认排除；相应测试实现后可使用 `uv run --locked pytest -m model_smoke` 或 `-m live_api` 单独执行。

## 文档与贡献

- [PRD](MarketLens_AI_PRD_v0.1.md)：文件名保留，正文版本为 v0.2。
- [Tech Design Spec](docs/TECH_DESIGN_SPEC.md)：State、Agent契约、采集和分析设计。
- [开发计划](docs/DEVELOPMENT_PLAN.md)：一次一个功能及验收顺序。
- [进度记录](docs/PROGRESS.md)：验证结果、提交与推送状态。
- [贡献指南](AGENTS.md)：代码风格与交付约定。

每次只实现一个功能，完成必要验证后更新进度并提交、推送。frontend视觉验收截图保存在 `test/pic_test/`；当前功能无前端页面，不需要截图。

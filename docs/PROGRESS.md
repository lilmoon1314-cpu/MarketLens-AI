# MarketLens AI 进度记录

## 当前状态

- 日期：2026-10-03。
- 阶段：F00开发环境与项目骨架、F01契约、F02本地导入完成；下一项F03离线工作流。
- PRD基线：`MarketLens_AI_PRD_v0.1.md`正文v0.2。
- 本地基线：Python3.12、uv锁文件、src布局、pytest/Ruff、基础CI；Git main已初始化。
- 远端目标：`https://github.com/lilmoon1314-cpu/MarketLens-AI.git`。
- 远端核实：GitHub连接器确认空仓库、默认main、具有push权限；扩展网络Git只读连接成功。
- 推送状态：F00已发布，交付记录提交fbdd8863f51bcd344f73d753613439dc8ed66e9d；F01已发布8480f77，Windows/Ubuntu CI通过；F02本提交包含该任务，发布pending。

## F02 — 本地评论导入

- 日期：2026-10-03；状态：实现及本地验证完成，提交时发布pending。
- 交付：注册数据集ID读取CSV/JSONL、10 MiB有界读取、NFKC/空白规范化、稳定SHA256 ID、同商品全文/来源ID去重；保留首条，最多1000条。
- provenance：来源统一local；日期须含时区并转UTC，未知为null；额外字段及作者丢弃。非法JSON/记录、空正文、重复、超量分别计数，raw数等于保留数加拒绝数。
- 失败：未知ID、编码/大小/文件结构错误拒绝；CSV损坏引号不猜测后续行。未增加CLI、采集或分析功能。
- 验证：全量离线pytest 79 passed；Ruff lint/format通过；wheel/sdist构建通过。新增26项涵盖稳定ID、跨商品、元数据、CSV多行/BOM、坏行、1000条上限、大小/编码/路径边界。
- 文档：README导入说明；本轮无前端，截图不适用。
- 后续：用户授权自动逐功能推进；发布验证后开始F03，不再逐项等待用户确认。

## F01 — 数据与Agent契约

- 日期：2026-10-02；状态：实现及本地验证完成；本提交包含该任务，发布pending。
- 退出标准：Pydantic业务类型、六个Agent入口Schema、合法/非法输入及引用结构测试；只实施契约，不接入模型或采集。
- 交付：`src/marketlens/contracts/`中的请求/评论/标注/洞察/图表及Agent类型、可序列化AnalysisState声明、Schema导出模块；`docs/schemas/`中六个独立入口和一个共享bundle（14个定义）。
- 校验：禁止额外字段、严格JSON类型、长度/数量/评分范围、唯一数组、必需可空字段、UTC、来源所需输入、评论与标注ID匹配、批次评论ID唯一、主题仅bar图；空白文本不自动改写原文。
- 测试：`uv run --locked --offline pytest -q`：53 passed（含原2项环境检查）；中文六契约JSON往返、Draft202012元校验/样例校验、全部内部引用、导出文件字节一致、错误字段/评分/日期/ID均通过。
- 质量：`uv run --locked --offline ruff check .`与`ruff format --check .`通过；`uv lock --check --offline`通过；`uv build --no-sources --offline`成功生成wheel/sdist。
- 依赖：jsonschema加入dev组，复用已锁版本；生产依赖保持Pydantic，未安装LangGraph/GLiNER2/浏览器，未触发外部服务。锁文件只添加dev组声明，保留其他解析结果。
- 文档：README记录导出/校验用法；贡献指南、设计状态和开发计划同步。未知日期/来源为null，不提交个人数据；本轮无前端，截图不适用。
- 边界：Schema通过不表示证据真实或URL可抓；商品URL主机/短链/ID验证F13、来源交集F08、证据白名单F09、数据集存在F10、最终报告强类型随统计/持久化补齐。State只是TypedDict声明，尚无LangGraph运行逻辑。
- 交付：基于main正常追加，不改写历史；使用已授权GitHub连接器发布并核对本地tree，最终SHA/CI结果在交付回复提供。
- 下一任务：F02本地评论导入（CSV/JSONL、规范化、稳定ID/去重）；本轮停止在F01。

## D02 — 评论渠道改为淘宝

- 用户要求：将外部评论获取渠道改为爬取淘宝，保留本地导入；中文优先与严格低于30%的LLM预算保持。
- 更新：PRD、Tech Design Spec、开发计划与README，source枚举改为taobao/local；请求增加商品URL，评价增加product_id，加入质量/物流/包装主题。
- 采集设计：Playwright读取用户指定商品页的可见评价，独立登录profile、有限分页、实际覆盖量、partial返回；真实页面适配在F13实施，本轮未抓取评论。
- 验证：JSON Schema元校验与内部引用检查通过；淘宝请求/评论样例通过；原reddit来源被新契约拒绝。

## F00 — 项目开发环境

- 日期：2026-10-02；状态：完成，已提交并发布远端，Windows/Ubuntu CI通过。
- 退出标准：可复现安装、可编辑包导入、离线pytest、Ruff、wheel/sdist打包、基础CI配置；无业务功能越界。
- 交付：pyproject.toml、uv.lock、Python版本约束、src包、环境检查测试、README/.env.example/.gitignore、Windows/Linux GitHub Actions。
- 依赖：基础仅Pydantic；workflow/llm/nlp/ui/collector为可选extras；dev使用标准dependency group。锁定126个含可选依赖的包，本轮安装13个基础/开发包，没有安装可选NLP/UI/浏览器，也未下载模型权重。
- 测试：`uv run --locked pytest -q`：2 passed；`uv run --locked ruff check .`与`ruff format --check .`通过；`uv lock --check --offline`通过。
- 打包：`uv build --no-sources`生成wheel和sdist；wheel在独立环境离线安装并用隔离模式导入成功；归档检查确认没有运行数据/缓存/实际凭据。
- 忽略验证：.venv、.uv-cache、.local淘宝profile、.env、dist均被Git忽略；.env.example仅为无密钥配置模板。
- CI：Ubuntu与Windows作业均success，运行链接：https://github.com/lilmoon1314-cpu/MarketLens-AI/actions/runs/36995046559。
- 提交：768ac89d42fdfcc343de305801eb3a5da455773c，`feat(F00): bootstrap development environment and plan Taobao collection`；包含F00及用户授权的渠道文档变更。
- 发布方式：HTTPS Git连接失败，现有SSH身份无该仓库写权限、CLI token仅可读；使用已授权的Codex GitHub连接器创建Git对象并非强制更新main。全部14个文件blob及最终tree与本地逐项核对一致。
- 历史：远端先以8518819初始化.gitignore，再发布F00；原未发布本地root提交b933897保存在local/f00-before-api，主分支对齐真实远端历史，无远端force push。
- 进度同步：本次仅追加完成记录的文档提交；其最终SHA在交付回复提供，不继续为记录自身SHA追加提交。
- 下一任务：F01数据与Agent契约；本轮停止在F00，不自动实施F01。

## D01 — 开发计划与技术设计

- 交付：TECH_DESIGN_SPEC.md、DEVELOPMENT_PLAN.md、本进度文档。
- 内容：State、三个Agent输入输出Schema、GLiNER2调用、工具边界、目录、MVP顺序、失败降级、预算、证据、UI、评估与Git流程。
- 校验：PRD正文与官方GLiNER2/LangGraph接口查阅；文档内JSON Schema做解析、Draft 2020-12元Schema与引用完整性检查。没有运行应用测试，因应用尚不存在。
- 校验结果：12个类型定义通过；六个Agent契约分别通过中文合法样例，并拒绝额外字段；三个Markdown文档代码围栏配对有效；中文优先模型引用一致性通过。检查为临时只读脚本，没有添加应用或测试源文件。
- 已确认：中文评论优先、中文UI/报告；可配置OpenAI兼容接口；按主题分层抽样且严格低于30%。实际服务地址/模型待接入时配置。
- 设计决定：本地数据优先；不自动切GLiNER2.5；RAG先做运行内证据检索；计数由程序生成；后续每次只实现一个功能。
- 连接检查：普通网络请求失败；扩展网络只读检查亦返回Connection was reset，远端信息仍未核实。
- 当时下一步：核实远端后实施F00；本条为D01历史，后续用户已授权实施，最新状态见F00。

## 后续记录模板

每项登记：任务ID、日期、目标/退出标准、行为变化、受影响文件、测试命令与结果、视觉截图（适用时）、风险/遗留问题、commit/push状态、下一任务。记录真实状态，不用fake结果代替真实模型验收，不把本地提交称为远端交付。

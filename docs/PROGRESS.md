# MarketLens AI 进度记录

## 当前状态

- 日期：2026-10-03。
- 阶段：F00开发环境与项目骨架、F01契约、F02导入、F03离线工作流完成；F04语义适配器完成；F05聚合统计完成；F06预算路由完成；F07 LLM适配器完成；F08 Planner接入完成；F09 Analyst与证据完成；F10 Visualization与真实本地闭环完成；F11持久化完成；下一项F12中文Dashboard。
- PRD基线：`MarketLens_AI_PRD_v0.1.md`正文v0.2。
- 本地基线：Python3.12、uv锁文件、src布局、pytest/Ruff、基础CI；Git main已初始化。
- 远端目标：`https://github.com/lilmoon1314-cpu/MarketLens-AI.git`。
- 远端核实：GitHub连接器确认空仓库、默认main、具有push权限；扩展网络Git只读连接成功。
- 推送状态：F00已发布，交付记录提交fbdd8863f51bcd344f73d753613439dc8ed66e9d；F01已发布8480f77，Windows/Ubuntu CI通过；F02已发布b802c27，CI 37092971430成功；F03已发布8ba1671，CI 37093433646成功；F04已发布17bc94a；F05已发布3476a9d；F06已发布dca80d2；F07已发布0f3f33b，CI 37095966234成功；F08已发布13f389d，CI 37096431061成功；F09已发布4ae5bd9；F10已发布131f1c8；F11本提交包含该任务，发布pending。

## F11 — 运行持久化与历史记录

- 日期：2026-10-03；状态：实现及离线验证完成，提交时发布pending。
- 交付：强类型AnalysisReport及生成Schema；SQLite运行快照、评论、标注、报告、版本缓存和引用；逐阶段事务保存、历史列表、运行内证据白名单、历史删除与孤立缓存清理；官方SqliteSaver检查点独立文件。
- 缓存：规范化文本哈希、模型revision、语义schema/parser、推理配置、报告语言、三个提示词版本形成键；demo独立空间，注入的未知后端不共享真实缓存。缓存只复用语义标注，不复用LLM结论；更换review_id后正确绑定当前运行。
- 故障：初始化/阶段/最终写入失败保留内存结果与安全提示；persisted仅在最终事务成功后为true。检查点失败停止并返回已有结果，不重放外部调用；没有承诺自动恢复或恰好一次执行。真实LLM服务每次运行新建，防止共享跨运行预算。
- CLI：默认存入忽略的.local/marketlens.sqlite3，支持--data-dir；导出仍为stdout JSON。程序服务显式注入RunStore，无存储调用仍保持兼容。
- 验证：全量离线pytest 201 passed、7外部检查排除；9项新增测试覆盖报告/检查点/证据/历史、删除与共享引用、事务回滚、缓存版本与损坏、阶段/最终/检查点故障；Ruff、锁检查及wheel/sdist构建通过。
- 边界：本轮没有前端，截图不适用。两个SQLite文件的删除是顺序操作，跨文件不具原子事务；异常时允许重试删除。仅本地保存，未实现多租户、自动恢复或迁移框架。
- 后续：发布后自动推进F12；真实淘宝验收目标为iPhone 17，具体店铺商品链接仍待用户提供。

## F10 — Visualization与真实本地闭环

- 日期：2026-10-03；状态：实现及离线/真实闭环验证完成，提交时发布pending。
- 交付：版本化图表提示词、字段/数据集白名单、去重配置、已有数据默认bar/零数据跳过、程序中文标签与绑定数据；topic与证据重叠计数禁止donut。运行时约束同步ChartSpec并重新导出检查Schema。
- 图：统计partial也走确定性图表fallback；支持真实Visualization注入，三Agent共享账本；完整AnalysisService.real与显式--real CLI，不再把真实流程标demo。
- 验证：离线pytest 192 passed、7外部检查排除；已有/缺失/重复数据集、overlap donut、零数据不调用、中文绑定数据均通过；Ruff/lock/打包通过。
- 真实验证：Visualization与12条合成评论完整GLiNER2/三Agent smoke 2 passed（65.06秒含加载/API，2上游模型警告）；模式real、12条语义处理、严格预算、绑定图表、usage/证据通过。非真实用户数据，不能作为质量或1000条性能验收。
- CLI验收：3条合成评论真实CLI stdout解析JSON成功，mode real/status partial/selected0/charts3；上游模型配置打印已隔离stdout，stderr警告未影响JSON。
- 边界：本轮交付数据与配置，没有页面渲染，截图不适用；F12再做真实布局/视觉验收。已询问后续淘宝验收商品URL，同时继续独立工作。
- 后续：发布后自动推进F11 SQLite报告、checkpoint与版本缓存。

## F09 — Review Analyst与证据

- 日期：2026-10-03；状态：实现及本地/真实API验证完成，提交时发布pending。
- 交付：版本化中文batch/merge提示词、入选集合分批与实际Schema消息容量细分、失败partial恢复、合并fallback、证据白名单、同义标题确定性去重、程序insight_id/evidence_count。
- 安全边界：批次必须划分固定入选集合，单批引用只能本批；合并只引用已验证洞察证据。非法引用整条删除，摘要重建；无证据摘要也重建。长评论不截证据，预算不足不调用；共享Planner/Analyst运行账本。
- 图：支持真实Analyst注入，记录实际尝试送入的独立ID、完整usage、程序计数；warnings导致partial。demo依然显式，真实Visualization为下一项。
- 验证：离线pytest 184 passed、5外部检查排除；批次/合并、假引用、部分失败、重叠证据、稳定ID、输入细分、长正文、零预算、越权批次、实际图白名单/计数测试通过。
- 真实验证：首个Analyst检查失败，未保存原响应，不能确定其具体原因；脱敏诊断复测输出合法且一次调用成功（833输入/1486输出，2319 reported tokens）。将smoke改为10条开发样例入选2条，再执行真实检查1 passed（13.05秒），引用/程序计数通过。保留首次失败记录，不宣称稳定性/质量达标。
- 质量：Ruff/lock/打包通过；密钥扫描无泄漏，.env继续忽略；无前端截图。
- 后续：发布后自动推进F10，限制图表字段/数据集并接入完整真实模式。

## F08 — Research Planner接入

- 日期：2026-10-03；状态：实现及本地/真实API验证完成，提交时发布pending。
- 交付：版本化中文Planner提示词、输入到计划、request/available来源交集校验、失败/越权fallback与warnings；无可用交集时明确失败。
- 图：支持注入PlannerAgent，使用同运行LLM账本，统计/路由前扣除Planner消耗并限制provider输入/context/output；标注planner_mode与usage。混合流程整体仍demo，不假装Analyst已真实接入。
- 验证：离线pytest 173 passed、4外部检查排除；新增允许交集、越权、敏感错误、200字产品fallback关键词100字、空交集、Planner消耗4500/5000后无评论预算、失败后仍导入测试。
- 真实验证：脱敏耳机请求Planner smoke 1 passed（9.37秒），来源只local、关键词非空、未降级；Ruff/lock/打包通过。无前端截图。
- 后续：发布后自动推进F09；真实Analyst批次/合并与证据检查为下一独立任务。

## F07 — LLM结构化输出适配器

- 日期：2026-10-03；状态：实现及本地/真实API验证完成，提交时发布pending。
- 交付：配置地址/模型/密钥、JSON对象/显式JSON Schema模式、Pydantic严格输出、45秒超时、关闭SDK重试、应用层一次临时失败/非法输出重试、脱敏错误、usage与全运行预算。
- 计费：发送前按完整消息/Schema字节保守预留输出；每次尝试均计入账本，服务usage有效记reported，否则estimated_reserved；不捏造价格。context较小时下调输入上限，超限不请求。
- 验证：离线pytest 167 passed、3外部检查排除；真实LangChain/OpenAI SDK经MockTransport验证两种格式、500仅一次重试、请求参数与usage；错误JSON/额外字段/缺失字段/预算/配置优先级/密钥隐藏均通过。
- 真实验证：用户配置的服务最小PlannerOutput live_api 1 passed（12.98秒）；仅测试接口，不宣称Planner行为已验收。并行测试缓存出现WinError5警告，未影响结果或调用。
- 配置迁移：用户最初将配置写入跟踪的.env.example；已完整复制到忽略.env并恢复无凭据模板，再添加公开token参数。密钥未输出/提交，git check-ignore确认.env忽略。
- 质量：Ruff/lock/打包通过；CI加llm extra执行HTTP离线集成。无UI截图。
- 后续：发布验证后自动推进F08；配置障碍已解决，不需用户重新提供凭据。

## F06 — 高价值预算路由

- 日期：2026-10-03；状态：实现及本地验证完成，提交时发布pending。
- 交付：整数严格<30%上限、processed/actionable>=0.60候选、主主题分层/最大余数/稳定排序、完整评论JSON保守token估算、输入/输出/剩余运行/批条数限制、固定白名单证据读取。
- 图接入：semantic→aggregate/selection节点，支持注入F04真实适配器；默认明确DemoSemantic。失败保留unknown统计，无候选或预算不足跳过Analyst并partial；报告展示Statistics/selection。
- 验证：离线pytest 140 passed、2 model_smoke排除；新增比例0—1000全部整数边界、手算19/8/2层分配、输入乱序、长评论不截证据、10000/0 token预算、299上限、白名单拒绝、语义失败图测试。
- 真实验证：两个显式model_smoke通过，14.53秒含加载；真实GLiNER2→统计/路由→fake三Agent图通过，仍标demo，不宣称真实LLM或模型准确率验收。
- 质量：Ruff/lock/打包通过；无前端截图。F04 CI 37094307495成功。
- 边界：token数是estimated，需F07累计实测usage/重试，F08扣Planner消耗、F09正式分批/合并。候选错分类风险沿用F04，不静默降阈值或把全量文本发LLM。
- 后续：发布后自动推进F07；用户回复LLM已配置，目前进程环境/.env不可见，接入阶段进一步检查本机配置可读性。

## F05 — 聚合统计

- 日期：2026-10-03；状态：实现及本地验证完成，提交时发布pending。
- 交付：Statistics强类型与聚合工具；raw/valid/rejected、processed/unknown/spam/truncated、low_sample、三分布及明确分母。共享Schema重新生成，Agent接口保持。
- 规则：缺失/失败标注计unknown；spam只从产品情绪/主题排除，value和预算valid分母保留；多标签topic可超过分母。拒绝重复/外来ID与不一致raw计数，输出与输入排列无关。
- 验证：离线pytest 119 passed、1真实模型检查默认排除；9项新增覆盖手算混合fixture、全spam、零样本、20条边界、伪失败标签、输入计数/ID错误；Schema字节/引用回归、Ruff/打包通过。
- 边界：仅确定性统计工具，不将抽样证据外推为发生率；图接入随F06，不改变demo含义。无前端截图。
- 后续：本功能发布后自动推进F06。

## F04 — GLiNER2语义适配器

- 日期：2026-10-03；状态：实现及本地验证完成，提交时发布pending。
- 交付：延迟加载/进程复用CPU span模型、固定revision、三任务组合分类、严格分数转换、unknown/other、原文保留与实际编码截断、减半batch重试一次、失败unknown/processed=false；不转LLM。
- 兼容：原1.3.2缺失set_word_splitter；按设计升级正式2.0.0，并锁定其兼容transformers4.57.6/tokenizers0.22.2/hub0.36.2；去除不再需要的依赖，保留无关CUDA锁段。
- 验证：离线pytest 110 passed、1 model_smoke deselected；显式中文真实model_smoke 1 passed（11.13秒含加载，2项上游警告）；Ruff/lock/构建通过。权重下载至忽略缓存，约1.23GB。
- 中文对比：四条脱敏人工开发样例、四组配置；char/中文value匹配3/4、sentiment1/4。选择路由初值但不宣称准确率达标；广告误判与负面情绪风险登记 `GLINER_DEVELOPMENT_CHECK.md`，留F14/F15独立评估。
- 边界：独立适配器已完成，demo仍明确fake；F05/F06接入统计/候选预算后再组合真实语义。没有前端，截图不适用。
- 后续：发布验证后自动推进F05。

## F03 — LangGraph离线闭环

- 日期：2026-10-03；状态：实现及本地验证完成，提交时发布pending。
- 交付：真实StateGraph与context依赖注入、三个契约化fake Agent、空数据/低样本/失败条件边、统一AnalysisService.run/stream、显式--demo CLI。
- 结果：正常demo complete；空数据insufficient_data；低于4条跳过Analyst并partial；节点异常保留已导入评论，输出脱敏错误。每个运行独立UUID，State不存模型/文件句柄。
- 验证：全量离线pytest 90 passed；含实际图编排、进度顺序、数据隔离、三Agent失败、假证据/越权来源、CLI退出码和JSON报告；Ruff lint/format、lock检查、wheel/sdist通过。
- 依赖：安装锁定workflow extra，版本LangGraph1.2.12；生产基础依赖未扩张。CI安装workflow执行集成测试；没有模型下载或API调用。
- 边界：模拟只取首条证据且N>=4，不实现F06正式分层/token路由；模拟unknown不代表语义处理。ChartSpec仅演示传递，不表示统计或UI已存在。真实Report类型/持久化仍F11。
- 文档：README命令/状态/局限，AGENTS与计划同步；无前端截图。
- 后续：发布本功能后自动推进F04。

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

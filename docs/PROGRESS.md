# MarketLens AI 进度记录

## 当前状态

- 日期：2026-10-02。
- 阶段：F00开发环境与项目骨架完成，本地验证通过；业务功能尚未实现。
- PRD基线：`MarketLens_AI_PRD_v0.1.md`正文v0.2。
- 本地基线：Python3.12、uv锁文件、src布局、pytest/Ruff、基础CI；Git main已初始化。
- 远端目标：`https://github.com/lilmoon1314-cpu/MarketLens-AI.git`。
- 远端核实：GitHub连接器确认空仓库、默认main、具有push权限；扩展网络Git只读连接成功。
- 推送状态：F00提交待推送，推送后验证远端SHA并补充交付记录。

## D02 — 评论渠道改为淘宝

- 用户要求：将外部评论获取渠道改为爬取淘宝，保留本地导入；中文优先与严格低于30%的LLM预算保持。
- 更新：PRD、Tech Design Spec、开发计划与README，source枚举改为taobao/local；请求增加商品URL，评价增加product_id，加入质量/物流/包装主题。
- 采集设计：Playwright读取用户指定商品页的可见评价，独立登录profile、有限分页、实际覆盖量、partial返回；真实页面适配在F13实施，本轮未抓取评论。
- 验证：JSON Schema元校验与内部引用检查通过；淘宝请求/评论样例通过；原reddit来源被新契约拒绝。

## F00 — 项目开发环境

- 日期：2026-10-02；状态：本地完成，提交/远端验证待执行。
- 退出标准：可复现安装、可编辑包导入、离线pytest、Ruff、wheel/sdist打包、基础CI配置；无业务功能越界。
- 交付：pyproject.toml、uv.lock、Python版本约束、src包、环境检查测试、README/.env.example/.gitignore、Windows/Linux GitHub Actions。
- 依赖：基础仅Pydantic；workflow/llm/nlp/ui/collector为可选extras；dev使用标准dependency group。锁定126个含可选依赖的包，本轮安装13个基础/开发包，没有安装可选NLP/UI/浏览器，也未下载模型权重。
- 测试：`uv run --locked pytest -q`：2 passed；`uv run --locked ruff check .`与`ruff format --check .`通过；`uv lock --check --offline`通过。
- 打包：`uv build --no-sources`生成wheel和sdist；wheel在独立环境离线安装并用隔离模式导入成功；归档检查确认没有运行数据/缓存/实际凭据。
- 忽略验证：.venv、.uv-cache、.local淘宝profile、.env、dist均被Git忽略；.env.example仅为无密钥配置模板。
- CI：已配置Ubuntu/Windows两平台；远端实际运行结果在推送后核实，不以本地通过替代。
- 提交：本提交包含F00及用户授权的渠道文档变更，实际SHA在推送后交付记录登记。
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

# MarketLens AI 开发计划

日期：2026-10-02；依据PRD正文v0.2；详细接口见 `TECH_DESIGN_SPEC.md`。采集渠道已改为淘宝商品评论；本轮仅实施F00，后续任务按次推进。

## 1. 开发原则

按垂直闭环逐步完善，每次仅完成下表一个功能任务；不跨任务顺手添加功能。每项必须有可观察的退出标准、必要测试、进度记录、独立提交和推送。模型可替换但契约稳定，先本地数据，后外部采集。先用fake验证工作流，再验证真实模型，fake结果不能作为AI效果验收。

PRD里程碑顺序调整为：契约/离线输入 → 图编排 → 语义路由 → 分析 → 可视化 → 淘宝 → 效果与性能。这样减少外部凭据、网络与模型性能同时阻塞开发的问题。

## 2. 目录结构（拟建，不代表已经存在）

```text
MarketLens-AI/
├── AGENTS.md
├── MarketLens_AI_PRD_v0.1.md       # 当前正文v0.2，暂不重命名
├── README.md
├── pyproject.toml / uv.lock
├── .env.example / .gitignore
├── docs/
│   ├── TECH_DESIGN_SPEC.md
│   ├── DEVELOPMENT_PLAN.md
│   └── PROGRESS.md
├── src/marketlens/
│   ├── contracts/                 # Pydantic，Schema导出
│   ├── workflow/                  # State、nodes、routing、service
│   ├── agents/                    # planner、analyst、visualization
│   ├── prompts/                   # 各Agent版本化提示词
│   ├── tools/                     # collection、normalization、aggregation、evidence
│   ├── adapters/                  # gliner2、llm、taobao（Playwright）
│   ├── storage/                   # SQLite、cache
│   ├── evaluation/                # 指标与bad cases
│   ├── ui/                        # Streamlit页面与图表
│   └── config.py / cli.py
├── tests/
│   ├── unit/ / integration/
│   └── fixtures/                  # 脱敏小样本与fake模型响应
├── test/pic_test/                 # 视觉验收截图
├── evals/                        # 版本化标注数据/说明
├── .github/workflows/            # 后续基础CI
└── .local/                       # 运行DB、上传、报告、缓存；Git忽略
```

## 3. MVP开发顺序与单功能退出标准

| ID | 单次功能 | 依赖 | 交付与必要验证 |
|---|---|---|---|
| F00 | 项目开发环境 | 设计 | uv/Python3.12、包配置、README命令、Ruff/pytest、Git忽略；安装/导入检查，基础CI |
| F01 | 数据与Agent契约 | F00 | Pydantic类型、六个Agent入口Schema；合法/非法输入、引用结构测试 |
| F02 | 本地评论导入 | F01 | CSV/JSONL、规范化、稳定ID/去重；空/坏行/重复/超量测试 |
| F03 | LangGraph离线闭环 | F02 | 三Agent fake、条件边、统一service/CLI；正常/无数据/节点失败图测试 |
| F04 | GLiNER2语义适配器 | F03 | 本地模型复用、组合分类、分数转换；fake边界测试+真实模型显式smoke |
| F05 | 聚合统计 | F04 | sentiment/topic/value分布、unknown/spam分母；手算fixture对照 |
| F06 | 高价值预算路由 | F05 | K限制、主题分层、token预算、白名单；边界/稳定性/无候选测试 |
| F07 | LLM结构化输出适配器 | F06 | 可配置provider、usage、一次重试；断网mock与显式真实API smoke |
| F08 | Research Planner接入 | F07 | 请求→计划、允许sources校验、失败fallback；固定输入与错误输出测试 |
| F09 | Review Analyst接入 | F08 | batch/merge、证据校验、程序计数；假引用/重叠证据/部分批次失败测试 |
| F10 | Visualization接入 | F09 | ChartSpec选择、字段白名单、默认配置；无数据/非法dataset/多标签donut测试 |
| F11 | 运行报告持久化 | F10 | SQLite、节点checkpoint、版本缓存、历史查询；事务/回读/失效测试 |
| F12 | Streamlit端到端页面 | F11 | 上传→进度→报告→证据→导出；真实页面验收、桌面/窄屏截图 |
| F13 | 淘宝商品评论采集 | F12 | 指定商品URL、独立浏览器登录profile、可见评论分页、部分结果；登录/验证/DOM变化mock+真实商品smoke |
| F14 | Bad Case记录 | F13 | 标记错误评论/洞察、导出脱敏人工评估包；ID追溯/敏感字段检查 |
| F15 | MVP质量与性能验收 | F14 | 冻结评估集、1000条真实基准、成本/质量报告；不达标记录后开独立修复任务 |

F00不实现业务；F03 fake仅用于证明编排。F12页面按一个明确可验收闭环交付，不扩展登录、后台管理或额外页面。每个任务发现额外缺陷时，必要的本功能修复可以纳入，其他事项登记backlog。

## 4. 开发命令

```text
uv sync --locked --group dev                # 安装锁定依赖
uv run pytest tests/unit -q        # 契约与纯逻辑
# 集成测试落地后：uv run pytest tests/integration -q # 使用fake的集成测试
uv run ruff check .
uv run ruff format --check .
# F03 CLI落地后：uv run marketlens analyze --input <file> --product <name> --goal <goal>
# F12 UI落地后：uv run streamlit run src/marketlens/ui/app.py
uv run pytest -m model_smoke       # 显式下载/加载真实模型
uv run pytest -m live_api          # 显式使用凭据，可能产生费用
```

普通pytest默认排除model_smoke/live_api；真实评估命令由F15登记README。每次运行受影响的测试；契约/图变更运行离线集成回归；UI做视觉验收；不得声称尚不存在的命令已通过。

## 5. 进度、提交与推送约定

用户已授权后续每功能自动提交/推送，目标标准化为 `https://github.com/lilmoon1314-cpu/MarketLens-AI.git`（移除原链接中文句号）。不反复询问常规提交与推送许可。

首次实现前先只读核实远端HEAD/历史和本地状态；2026-10-02已核实远端为空，默认main，具有push权限，本地main已初始化。远端为空时以main初始化；远端非空时以远端默认分支为基线，将本地PRD/指南/设计文档受控纳入，不覆盖远端同名文件，也不建立无关历史。冲突需要比对内容后合并；若存在实质产品决策冲突才询问用户。

默认在远端默认分支正常提交/推送；若分支保护要求PR，使用 `feat/Fxx-<slug>` 分支和PR，记录等待合并，不绕过保护。不使用force push、不改写远端历史、不提交无关用户改动。

每功能流程：

1. 在PROGRESS登记任务ID/验收标准，确认仅此任务进入实施。
2. 实现该功能，执行必要测试；失败则修复，尚未通过不标记complete。
3. 更新PROGRESS：行为变化、测试命令/结果、截图、遗留问题、下一任务、交付状态。
4. 检查diff和秘密/大文件，仅暂存该功能与进度文件；提交 `feat(Fxx): <description>`，文档使用 `docs:`，修复使用 `fix:`。
5. 正常push，验证远端分支包含本次SHA；在回复报告SHA/分支/测试/截图。若push失败，记录错误并优先解决，不能说“已推送”。

进度文档不能在同一commit预写自己尚不存在的SHA。同次提交中填写“本提交包含该任务”，最终SHA在交付回复、下次进度条目或必要的独立同步记录中记录。push状态在提交时记pending，验证成功后回复；只有需要持久化同步状态时另做纯文档提交，不能为填写文档SHA无限追加提交。

2026-10-02：通过GitHub连接器与扩展网络核实空仓库，已恢复远端访问；提交推送结果见PROGRESS。受限环境中的Git和依赖网络操作需要扩展权限，常规实现仍在仓库内完成。

# 当前任务：实施 R1/T1/T2/E1（模型假设诊断的复核后方案）

> 本文件已从"模型假设诊断"改为"实施 R1/T1/T2/E1"。诊断轮（`docs/model_assumptions_audit.md`）与 Codex 独立复核轮（`docs/model_assumptions_review.md`、`docs/model_assumptions_plan.md`）均已完成，均未修改业务代码。本轮按用户指令，只实施复核方案中的 R1（纠正文档）、T1/T2（补充测试）、E1（诊断工具），**不进入 B1 业务校准，不重开 B2/D1**。原两轮内容作为历史背景保留在下方。

## 基线（延续上一轮，未变化）

- 分支：`audit/model-assumptions`，HEAD `50ce335c2d5c8f20bbecc1e9eeae44745b076879`（本轮开始前重新核实分支/HEAD/工作区差异，与用户预期一致；本轮全程未 commit，HEAD 未变化）。
- 测试：`python -m pytest -W error -ra` → **98 passed, 0 skipped**（78 基线 + T1 新文件 8 个 + T2 在 `tests/test_simulation.py` 新增 12 个）。

## 本轮范围与产出

- **R1（纠正文档）：** 在 `docs/model_assumptions_audit.md` 顶部加入醒目横幅，标明结论已被复核修正，链接到 `model_assumptions_review.md`/`model_assumptions_plan.md`；原文不改，作为历史材料保留。在 `docs/runbook.md` 中：纠正 `overstock_capital_exposure` 的定义（原文误写为"超过 180 天需求"，改为当前 `max_stock` 方法的真实有效阈值 `max(ROP+Q, d×overstock.coverage_days)`）；补充 `demand_cv` 的准确定义（含零月份的月度销量相对波动，及其与相关系数 0.84 的关系，撤回"主要衡量间歇性"的过度推断）；澄清 `months_in_window==3` 与 `short_history<3` 不是一回事；标注 `ordering_cost_gbp`/`annual_holding_rate`/`max_order_coverage_days`/`overstock.coverage_days`/`supplier_lead_time_days`/服务水平均为"演示/待校准"参数，责任人与校准日期明确写"未定"，不虚构。
- **T1（`tests/test_demand_simulation_interface.py`，新建，8 个测试）：** 0/1/2/3 个月观测通过真实 `full_months`/`build_sku_profile`/`classify_skus`/`simulate` 端到端验证，不手写跳过中间步骤的模拟输入；覆盖仅截断月、单月 NaN 处理、2→3 月边界（`short_history` 翻转点）、高收入短历史仍 Priority、零需求库存 0/>0 分别得 Normal/Overstock（用配置副本固定 `no_demand_units`，不改 live 参数）。
- **T2（`tests/test_simulation.py`，新增 12 个测试）：** EOQ 整数化上限的相等/超过边界、极小正需求的封顶下限、订货成本/持有率/单位成本的单调关系、放宽上限不减少最终订货量、库存恰等于再订货点/`max_stock_level`的严格比较边界、补货缺口用 `max(Q, shortfall)`（缺口超过封顶 EOQ 时用缺口）、固定库存实验（ROP/SS/库存不变，仅阈值和建议补货随配置变化）与完整重生成实验（`policy_position`/ROP/SS 不变，但库存随 EOQ 变化）的对照。所有新测试断言的是任意合法参数下都应成立的不变量，不锁定当前 `capped≈59%`、`699` 等诊断快照数字为通用正确答案。
- **E1（`scripts/model_assumptions_diagnostics.py`，新建）：** 显式接收 `--profile`/`--config`/`--output-dir`，拒绝写入 `outputs/`/`config/`/`data/`/`notebooks/`/`reports/`/`src/`/`tests/`/`docs/`/`scripts/`/仓库根目录（含祖先目录）；支持固定库存实验 A（复用 `apply_replenishment_rules` 的 `methods.inventory="fixed_range"` 跳过库存重写分支，不重新实现业务逻辑）、完整重生成实验 B、以及本轮九个敏感性场景；每个场景从基线深拷贝，不累积修改；记录代码提交/工作区脏污状态、输入文件哈希、依赖版本、seed、实际参数变化（如场景 5 的真实四舍五入交期值）；同时报告风险数量、缺货件数、金额指标；不做任何参数寻优。
- 未实施 B1（业务参数校准）、未重开 B2/D1（短窗口保守策略研究）——按用户指令明确排除在本轮之外。

## 验收结果

详见 `docs/handoff.md` 本轮交接（完整命令、E1 与复核报告 A/B/九场景的逐项数字对照、确定性重跑验证、变异测试证据、剩余限制）。摘要：`pytest -W error -ra` 全绿、0 跳过；E1 独立复现复核报告的 A/B 与九场景全部数字（含风险转移矩阵），逐项精确匹配；相同输入重跑 `scenario_summary.csv`/`field_change_counts.csv` 逐字节一致；固定库存实验（A）实测验证库存 0 处改变；T1/T2 各自的关键变异（首销前补零、截断月纳入统计、单月 NaN 未处理、`<3`→`<=3`、超储 `>`→`>=`、EOQ 封顶被误删）均已在临时副本中验证会让对应新测试失败；正式 `config/`、`outputs/`、`data/processed/`、notebook 文件在本轮前后哈希/`git status` 均无变化。

## Git 基线

分支 `audit/model-assumptions`，HEAD `50ce335c2d5c8f20bbecc1e9eeae44745b076879`（本轮全程未变化，未 commit、未 push）。

---

## 历史背景 4：模型假设诊断轮 + Codex 独立复核与方案（上一轮，已完成）

> 该轮产出了 `docs/model_assumptions_audit.md`（Claude 诊断）、`docs/model_assumptions_review.md`（Codex 独立复核，多处认定"部分成立"或"证据不足"并修正措辞）、`docs/model_assumptions_plan.md`（Codex 后续方案）。均未修改业务代码，均未 commit。

## 历史背景 3：实施修复方案任务书（更早一轮，已完成并提交）

> 该轮完成了 `docs/remediation_plan.md` 的 R1、R2、R3、R4、R5、R7、R8，并经 Codex 独立验收（发现并修复了 R1 第三处端到端缺口、收入回归测试容差过宽、验证脚本假成功风险、R2 正向覆盖不足、文档与实跑不一致、归因报告的一便士差异），最终测试数 78，已提交为 `50ce335`。完整记录见 `docs/handoff.md`。

### 用户决策（业务口径 D1/D2/D3，历史）

- **D1：** 保留收入优先分类和现有模拟规则，不新增安全库存下限。已补充 `short_history` 分类边界测试（`tests/test_demand.py`），并在文档中记录历史不足的统计局限。
- **D2：** 接受现有工作区作为整体验收基线，不拆分已有改动，不放宽单写者规则。
- **D3：** 继续支持缺少 `order_quantity` 段的合法 `top_up` 配置；EOQ 专属参数只在 EOQ 路径读取；年度持有成本在没有对应参数时明确标为不可用。

## 历史背景 2：问题复核与修复方案设计任务书（更早一轮，已完成）

> 该轮产出了 `docs/issue_review.md` 和 `docs/remediation_plan.md`，确认当前 live 配置实际运行的是 Phase 3B-1 模型（`config/simulation_assumptions.json` 的 `methods` 字段）。

### 本轮目标（历史）

对 `docs/issue_audit.md` 列出的 12 项诊断问题做独立复核，产出 `docs/issue_review.md`（逐项复核结论）与 `docs/remediation_plan.md`（修复方案，区分业务缺陷、文档问题、工程隐患/测试覆盖、以及需要用户决定的业务口径）。

### 重要说明（该轮复核中确认的事实，仍然有效）

- 自诊断阶段快照（`tmp/audit_snapshot_manifest.txt`，记录于当时 15:31）以来，工作区没有第三方改动。
- 已确认存在分支治理问题：`docs/current_task.md` 此前的"仅第一阶段清洗"范围与另一会话正在进行的 Phase 3B-1 实现，是在同一个分支（`phase1-data-correctness`）上并行发生的，违反了 `docs/ai_workflow.md` 自己规定的"每轮独立分支"和"同一时间只有一个工具修改仓库"——这是业务口径 D2，用户已在本轮决定接受现状，不拆分支（见上文）。

## 历史背景 1：原 Phase 1 收尾任务书（仅供参考，不代表当前验收要求）

### 目标

核实并收尾现有清洗规则、01–05 notebook、对比结果与文档，为用户审阅和提交做好准备。

### 范围

- 核对现有实现，不重复重写已经完成的清洗模块。
- 核对取消订单优先匹配同价销售、审核过的手工冲正、规则表校验及截断月份标记。
- 核对旧版 notebook 的删除与 archive/ 中归档的对应关系。
- 确认 clean_sales.csv 的忽略规则；取消 Git 跟踪时保留本地文件，遵守环境审批要求。
- 按顺序重新运行 01–05 和对比脚本，更新必要输出。
- 文档明确区分最初基线与上一轮修正结果。

### 验收要求（历史，清洗类数字仍然有效，已在本轮复核中重新验证）

- 在项目 `.venv` 下运行 `python -m pytest -W error`，全部通过；现有基准是 30 个测试，新增有意义的回归测试时允许增加。（本轮复核确认实际已增至 59 个测试。）
- 01–05 本轮从头执行，无错误；记录实际执行方式和结果。
- 对比脚本运行成功，并核对以下预期数据：清洗销售 519,627 行，收入 £9,818,872.18；同价取消匹配 2,722 条、异价 93 条、审核手工冲正 1 条。（本轮复核确认这些数字目前仍然真实有效。）
- 若输出与预期不同，查明原因并记录，不能为了吻合数字修改结果。
- README、runbook、管理层摘要、CHANGELOG 与报告的数字和口径一致。（本轮复核发现清洗类数字一致，但模拟/仓库策略相关数字已经过时，见 `docs/remediation_plan.md` R3/R4。）
- `data/processed/clean_sales.csv` 本地仍存在，且不再被 Git 跟踪。
- 更新 `docs/handoff.md`，列出验收证据和未解决问题。

### 本轮不做（历史，已被后续工作取代）

- 不重构月均需求、需求波动与库存模拟逻辑；这些作为下一轮任务。（实际上，另一会话已在本文件写成之前就开始了这部分工作，见上文"重要说明"。）
- 不删除忽略的 `.pyc` 缓存。
- 不假设能读取 Claude Commerce 项目里的 roadmap；无法访问时如实记录。
- 不 commit、不 push、不合并。

### Git 基线（历史）

此前核查的最新提交为 `1e73781`。执行者必须重新检查当前状态；工作区已有大量未提交修改，必须保留。

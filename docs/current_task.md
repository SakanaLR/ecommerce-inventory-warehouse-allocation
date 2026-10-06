# 当前任务：实施修复方案（R1/R2/R3/R4/R5/R7/R8）

> 本文件已从"问题复核与修复方案设计"改为"实施修复方案"。用户已就 `docs/remediation_plan.md` 中的三个业务口径做出决定（见下），本轮据此实施代码修复、测试补充和文档更新。原两轮任务书作为历史背景保留在下方。

## 用户决策（业务口径 D1/D2/D3）

- **D1：** 保留收入优先分类和现有模拟规则，不新增安全库存下限。已补充 `short_history` 分类边界测试（`tests/test_demand.py`），并在 `docs/management_summary.md`、`README.md`、`docs/runbook.md` 中记录历史不足的统计局限。
- **D2：** 接受现有工作区作为整体验收基线，不拆分已有改动，不放宽单写者规则。本轮继续在 `phase1-data-correctness` 分支上工作，未新建分支，也未声称完成任何改动拆分。
- **D3：** 继续支持缺少 `order_quantity` 段的合法 `top_up` 配置；EOQ 专属参数只在 EOQ 路径读取；年度持有成本在没有对应参数时明确标为不可用，不补默认值、不输出 0 冒充计算结果。

## 本轮范围

- 完成 `docs/remediation_plan.md` 的 R1、R2、R3、R4、R5、R7、R8（R6 已在复核轮的 `docs/management_summary.md` 更新中一并完成，未重复创建新报告）。
- 允许修改：`src/retail_analytics/simulation.py`、`scripts/attribute_model_changes.py`、`notebooks/05_working_capital_impact.ipynb`、`tests/*`、`README.md`、`docs/runbook.md`、`docs/management_summary.md`、`CHANGELOG.md`、`docs/handoff.md`、本文件。
- 不 commit、不 push、不合并。

## 完成情况摘要

详见 `docs/handoff.md`（本轮修改文件、实际验证命令、通过/跳过情况、结果变化说明、剩余限制）。

## Git 基线

分支 `phase1-data-correctness`，HEAD `1e73781429f09d310a4c75e5e94eb085aa3b0fb1`（与复核阶段一致，本轮未变化）。工作区存在大量未提交修改，必须全部保留，不 reset、不强制 checkout。

---

## 历史背景 2：问题复核与修复方案设计任务书（上一轮，已完成）

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

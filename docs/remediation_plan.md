# 修复方案（Remediation Plan）

本方案只覆盖 `docs/issue_review.md` 中复核为**确认**或**部分成立且存在真实待办**的问题。已被复核为"不成立"（ISSUE-10）或"已并入其它项"（ISSUE-09→ISSUE-08）的不再单独列出方案。不能仅因为模拟结果相对 Phase 3A 有大幅变化就判定实现有错——本轮复核已确认 3A→3B-1 的切换本身是正确实现，以下方案均不涉及回退或质疑该模型升级。

本文档仅设计方案，不在本轮实施；实施仍需另开一轮，遵循 `docs/ai_workflow.md` 的分支/单写者协议。

---

## 业务缺陷（需要修改 `src/`，属于真正的代码 bug）

### R1 — `order_quantity` 缺失/`top_up` 分支下的无条件读取导致 KeyError（对应 ISSUE-07）

- **根因**：`src/retail_analytics/simulation.py:252-253`（`apply_replenishment_rules`）在判断 `methods["order_quantity"]` 具体取值之前，无条件执行 `oq = assumptions["order_quantity"]` 并计算 `annual_demand_units`；该变量只在 `eoq` 分支（`simulation.py:261`）里被使用，是 3B-1 重构时把共享变量提到分支外面遗留的死代码。`scripts/attribute_model_changes.py:60` 存在完全相同的模式，是第三个受影响位置（`notebooks/05_working_capital_impact.ipynb` 的 `annual_holding_rate` 读取是第二个，已在诊断报告 ISSUE-07 中定位）。
- **推荐方案**：把 `oq = assumptions["order_quantity"]` 及依赖它的 `annual_demand_units` 计算移到 `if methods["order_quantity"] == "eoq":` 分支内部（`simulation.py`、`attribute_model_changes.py`、以及 notebook 05 对应代码三处同步修改），使 `top_up` 路径完全不依赖 `order_quantity` 配置段是否存在。
- **替代方案**：反过来在 `validate_assumptions` 里强制要求任何配置都必须包含 `order_quantity` 段（不论选择哪种方法），从源头拒绝不完整配置。优点是校验更严格；缺点是会让"精简的 Phase 3A 风格配置"（如 `reports/baseline_end_phase3a/simulation_assumptions_phase3a.json`）无法直接使用，需要产品确认是否要保留对这种精简配置格式的支持（见业务口径 D3）。若不需要保留，此替代方案更简单彻底。
- **涉及文件**：`src/retail_analytics/simulation.py`、`scripts/attribute_model_changes.py`、`notebooks/05_working_capital_impact.ipynb`。
- **回归测试**：`tests/test_simulation.py` 新增用例——构造 `methods.order_quantity="top_up"` 且 `assumptions` 中不含 `order_quantity` 键，断言 `apply_replenishment_rules` 正常返回、不抛异常。
- **验收标准**：新测试通过；额外用 `reports/baseline_end_phase3a/simulation_assumptions_phase3a.json` 在临时输出目录（不覆盖现有 `outputs/`）跑一次 notebook 04+05，确认不再崩溃且能产出 Phase 3A 口径的资金指标。
- **实施顺序**：**优先**——这是会直接阻断 notebook 04 执行的真实崩溃路径，且已发现三处同类隐患。

### R2 — `overstock=max_stock` 缺少与 `order_quantity=eoq` 的强制配对校验（对应 ISSUE-08）

- **根因**：`validate_assumptions`（`simulation.py:86-88`）只校验了 `inventory=policy_band` 需要 `order_quantity=eoq`，没有对称地校验 `overstock=max_stock` 也需要 `order_quantity=eoq`；`top_up` 分支下 `max_stock_level` 全为 `NaN`，`apply_replenishment_rules` 用 `fillna(reorder_point)` 兜底，导致有效超储阈值系统性缺少 EOQ 部分，偏离 `config/simulation_assumptions.json` 自己注释的定义。
- **推荐方案**：在 `validate_assumptions` 中增加对称校验：`methods.overstock=="max_stock"` 时要求 `methods.order_quantity=="eoq"`，否则 `raise ValueError`，与现有 `policy_band`/`eoq` 的校验风格保持一致。
- **替代方案**：如果确实希望支持"`max_stock` 超储定义 + 非 EOQ 订货量"的组合，则需要明确定义此时 `max_stock_level` 该如何计算（而不是隐式 `fillna` 到 `reorder_point`），并把新定义写进配置注释和文档——需要产品决定是否有这种业务场景。
- **涉及文件**：`src/retail_analytics/simulation.py`（`validate_assumptions`）。
- **回归测试**：仿照现有 `test_policy_band_requires_eoq`，新增 `test_max_stock_requires_eoq`，断言该组合触发 `ValueError`。
- **验收标准**：新测试通过；确认当前 live 配置（`overstock=max_stock` + `order_quantity=eoq`）不受影响，`pytest -W error` 全绿。
- **实施顺序**：与 R1 一起处理（当前 live 配置未触发，但属于容易被误配置踩中的陷阱，成本很低）。

---

## 文档问题（只需修改 `docs/`、`README.md`、`CHANGELOG.md`，不涉及代码）

### R3 — `docs/management_summary.md` 仓库分配策略表数字重算（对应 ISSUE-02）

- **根因**：文档数字对应旧的 Phase 3A 模拟结果，未随 3B-1 切换同步更新。
- **推荐方案**：用当前 `outputs/sku_inventory_simulation.csv` 的 `warehouse_strategy` 分布重新生成表格（Standard Replenishment Review 1,164；Overstock Review 1,008；Local Warehouse Priority 748；External or Limited Stock Strategy 626；Stable Local Warehouse Inventory 171；Small-Batch 73；合计 3,790），并注明对应模型版本（Phase 3B-1）与数据来源。
- **涉及文件**：`docs/management_summary.md`。
- **验收标准**：表格数字与 `outputs/sku_inventory_simulation.csv` 重新核对一致。
- **实施顺序**：高——这是一个会被直接引用的、明确错误的管理层数字。

### R4 — README/runbook/management_summary/CHANGELOG 补充 Phase 3B-1 模型说明（对应 ISSUE-05）

- **根因**：3B-1 的代码/配置改动没有同步更新到面向读者的"活文档"。（两份带日期的历史阶段报告不在此列，复核认为不应被视为过时，不需要修改。）
- **推荐方案**：在这四份文档中补充：安全库存改用 z·σ·√LT（service_level）、订货量改用 EOQ、超储定义改用 max_stock，以及新增的 `annual_holding_cost`、`eoq_capped_skus` 两个指标说明；同步把文中引用的旧模拟数字（库存价值、缺货/超储风险计数等）更新为当前 live 值；CHANGELOG.md 需要新增一条独立的 "Phase 3B-1" 记录。
- **涉及文件**：`README.md`、`docs/runbook.md`、`docs/management_summary.md`、`CHANGELOG.md`。
- **验收标准**：四个文件中出现 3B-1 相关关键词（service_level/EOQ/policy_band/max_stock/annual_holding_cost/eoq_capped_skus），且引用数字与当前 live 输出一致。
- **实施顺序**：高——属于向业务/读者交付的核心说明文档，与 R3 一起处理效率最高（同一批改动）。

### R5 — CHANGELOG.md 测试数量描述更新（对应 ISSUE-11）

- **根因**：`CHANGELOG.md:28` 停留在 "tests/test_simulation.py (7 tests)"，未反映 3B-1 阶段新增的 13 个模拟测试和 3 个 `test_repo_layout.py` 测试。
- **推荐方案**：更新为实际数字（模拟测试 20 个，全仓库 59 个），可与 R4 合并在同一次 CHANGELOG 更新里处理。
- **涉及文件**：`CHANGELOG.md`。
- **验收标准**：数字与 `pytest --collect-only -q` 实际结果一致。
- **实施顺序**：低，顺手处理。

### R6 — 归因表中间步骤增加一句说明性备注（对应 ISSUE-12）

- **根因**：`reports/phase3b1_attribution.csv` 中间行（仅启用 service_level、未切换 policy_band）显示缺货风险飙升到 1,855，脱离完整归因链条阅读容易被误判为回归。
- **推荐方案**：在下一轮撰写 3B-1 阶段说明文档时，加一句话解释这个中间态的成因（旧的 `fixed_range` 随机当前库存与新的、更高的再订货点不匹配），提醒读者要看完整的 4 步归因链条而非只看首尾。
- **涉及文件**：待新增的 3B-1 阶段报告（不在本轮范围内创建）。
- **实施顺序**：低，可与下一轮 3B-1 文档补全一起做。

---

## 工程隐患／测试覆盖（低成本，有现成模板）

### R7 — 清洗阶段增加锁定关键汇总数字的回归测试（对应 ISSUE-03）

- **根因**：`tests/test_cleaning.py` 等测试文件不加载真实原始数据、不断言最终行数/收入/取消匹配数，理论上这些数字可以在 pytest 全绿的情况下漂移。
- **推荐方案**：照抄 `tests/test_simulation.py:213` 已有的模式（`@pytest.mark.skipif` + 对比冻结快照），新增一个测试对比 `data/processed/data_quality_summary.csv`/`reversed_sales.csv` 的关键聚合数字（519,627 行、£9,818,872.18、2,722/93/1）与 `reports/baseline_end_phase1`（或更新后的合适基线）快照。
- **涉及文件**：`tests/test_cleaning.py` 或新建 `tests/test_pipeline_baseline.py`（不修改业务代码）。
- **验收标准**：新测试通过；建议实施时手动改一次 `config/non_product_stock_codes.csv` 验证测试真的会失败，验证后撤销改动（不提交这次临时修改）。
- **实施顺序**：中，成本低、有现成模板，值得与下一轮测试补充一起做。

### R8 — 补充"高收入 + short_history"分类边界测试（对应 ISSUE-04，与业务口径 D1 配套）

- **根因**：`tests/test_demand.py:82-101` 已经用高 CV 路径锁定了"收入优先于波动性"的规则，但没有 `short_history=True` 路径的对应用例。
- **推荐方案**：新增一条 fixture，`total_revenue` 达标 + `short_history=True`（不依赖高 CV），断言当前实现下仍分类为 `High-Revenue Priority`，把 ISSUE-01 复核确认的"设计即如此"行为用测试锁定，防止未来无意间改变优先级顺序。
- **涉及文件**：`tests/test_demand.py`。
- **实施顺序**：中，建议与业务口径 D1 的决策结果一起处理（如果 D1 决定要给 short_history SKU 设安全库存下限，测试用例需要同步覆盖新行为）。

---

## 实施顺序总览

1. R1（阻断性 bug，三处同类隐患）
2. R2（潜在静默错误，成本低）
3. R3 + R4 + R5（文档批量更新，建议同一次改动完成）
4. R7 + R8（测试补充，等 D1 决策后一并处理）
5. R6（信息性备注，可延后到下一轮 3B-1 文档撰写）

---

## 需要用户决定的业务口径（不属于"修复方案"，需要先决策）

### D1 — `short_history` 标记是否应该真正约束模拟层

当前 27 个"高收入但历史短于 3 个月"的 SKU 中，26 个的安全库存/缺货风险表现和正常历史的同类 SKU 没有系统性差异；只有 1 个（`23552`，1 个月历史、`demand_cv=0.000`、`safety_stock=0.0`）是真正"数据点太少导致 CV 本身没有意义"的边界情形。`short_history` 这个字段目前存在于输出里，但 `simulation.py` 从未读取它。是否要真正利用这个标记（例如给 `short_history=True` 的 SKU 设一个安全库存下限，不管落在哪个 SKU 分类），还是维持现状（`short_history` 仅作信息展示），是一个业务口径问题，需要你来定，定了之后再决定是否需要新增代码逻辑。

### D2 — 分支治理：本轮任务与并行的 3B-1 实现共享同一分支，是否需要梳理

`docs/ai_workflow.md` 自身规定"每轮使用一个独立分支"和"同一时间只有一个工具修改仓库"，但当前 `phase1-data-correctness` 分支上同时存在"仅第一阶段清洗"范围的任务（`docs/current_task.md`）和另一会话正在进行的 3B-1 实现的产物，直接违反了这两条规则。这不是文档更新能解决的，需要你决定：是否要把 3B-1 相关的未提交改动挪到一个新分支，让 `phase1-data-correctness` 恢复成纯 Phase 1 范围；还是接受当前状态，把 `docs/current_task.md`/`docs/ai_workflow.md` 的协议描述改得更宽松以匹配实际的多线并行工作方式。

### D3 — 是否需要继续支持"精简配置"（缺少 `order_quantity` 段）格式

R1 的两种方案中，"替代方案"（强制要求所有配置都包含 `order_quantity` 段）更彻底，但会让 `reports/baseline_end_phase3a/simulation_assumptions_phase3a.json` 这种历史快照格式的文件无法直接作为 live 配置使用。需要你确认：这类历史快照文件是否有被重新用作 live 配置的实际需求（例如用于对比实验），如果没有，"替代方案"更简单；如果有，应采用"推荐方案"（把变量计算移入对应分支内部），保留对精简配置的兼容。

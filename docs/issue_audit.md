# 问题诊断报告（Issue Audit）

## 范围与方法

本报告仅做诊断，不修改任何业务代码、notebook、`outputs/`、`data/processed/` 或 `config/` 文件，不 commit、不 push。审查覆盖：数据清洗、取消/冲正匹配、月度需求计算、SKU 分类、库存模拟（含安全库存、EOQ、补货策略）、仓库分配、资金指标、测试覆盖，以及文档与实现的一致性。

对既有报告（包括本轮对话中用户转述的交接总结、`reports/phase1_data_correctness.md`、`reports/phase3a_demand_and_simulation.md`）一律视为待核实的假设，逐项与当前代码、数据重新核对，而非直接采信。

**基线快照**：Git 分支 `phase1-data-correctness`，HEAD `1e73781`，本报告分析对象为 2026-09-16 15:31（PDT）时刻的工作区状态，完整 `git status` 与关键文件 SHA-256 记录在 `tmp/verify_pipeline_log` 同目录下的 `tmp/audit_snapshot_manifest.txt`（该目录被 `.gitignore` 忽略）。**审查期间确认另有一个会话在同一仓库并行工作**（详见"关键背景"），因此本报告是对该时间点的快照分析，此后仓库状态可能已经变化。

诊断过程未重跑任何会覆盖现有产出的 notebook 或脚本；涉及数字核实的地方，均直接对已存在的 CSV/JSON 输出做只读重算，或在临时目录内用独立 Python 片段验证，未写入仓库。

## 关键背景：Phase 3A → Phase 3B-1 的时间线（对既有报告的核实结论）

用户在本轮对话开始时转述的交接报告，描述当前状态为"Phase 3A 已实现并通过验收"，并建议"下一步做 3B：安全库存改用 z·σ·√LT、加 EOQ"。核查发现：**这份报告在撰写当时是准确的，但已被同一工作区中后续发生的改动覆盖，转述给用户时已经过时**：

- 今天 12:35，本会话运行 `scripts/verify_pipeline.sh`，复现的结果（库存价值 £637,918.62、缺货风险 1,326、超储风险 1,086）与用户转述的"3A"结果完全一致——当时 `config/simulation_assumptions.json` 确实还没有 `methods` 字段，`src/retail_analytics/simulation.py` 按默认的 `PHASE_3A_METHODS` 运行。
- 今天 14:49:09，`config/simulation_assumptions.json` 与 `src/retail_analytics/simulation.py` 被**同一时刻**改写，新增了真正生效的 `methods` 调度逻辑（`inventory=policy_band`、`safety_stock=service_level`、`order_quantity=eoq`、`overstock=max_stock`，即 z·σ·√LT 安全库存 + EOQ，也就是原报告建议的"下一步 3B"）。
- 14:55 前后，notebook 01–05 被重新执行，`reports/phase3b1_before_after.csv` 显示当前 live 结果已变为：库存价值 **£1,805,589.48**、缺货风险 **536**、超储风险 **1,008**，并新增 `annual_holding_cost`（£451,397.56）、`eoq_capped_skus`（2,242）两个 3A 阶段不存在的指标。
- 15:19 前后，`docs/ai_workflow.md`、`docs/current_task.md`、`docs/handoff.md` 三个新文件出现，定义了 Claude→Codex 单写者交接协议，且 `docs/current_task.md` 明确将**本轮**范围限定为"仅第一阶段数据清洗收尾，不改动需求/模拟逻辑"——但 3B-1 的模拟改动已经先于这份任务书存在于工作区中。

结论：这不是某个报告"编造数据"，而是**多会话并行工作导致的时间错位**：一份对某一时刻真实准确的验收结果，在传递给用户之前，工作区已经被另一个会话推进到了下一阶段。已确认为 ISSUE-05、ISSUE-06。

---

## 业务错误（Business Errors）

### ISSUE-01：SKU 分类优先级 bug——"高收入优先"类别不检查短历史/高波动性

- **严重程度**：业务错误
- **位置**：`src/retail_analytics/demand.py:144-148`（`classify_skus` 中 `np.select` 的条件顺序）
- **触发条件与证据**：分类规则的判定顺序是 `[high_revenue, high_volume & volatile, high_volume, long_tail]`——`high_revenue` 无条件优先匹配，短历史/高波动检查根本不会被应用到高收入 SKU 上。对生产数据直接验证：**758 个"High-Revenue Priority" SKU 中有 27 个 `months_in_window < 3`**（例如 `23552`：`total_units=1863`，`demand_cv=0.000`，但 `short_history=True`——这个"零波动"读数其实只来自 1–2 个真实数据点，不代表真正稳定）。
- **对业务结果的影响**：下游任何消费 `avg_monthly_units`/`demand_cv` 的模块（已确认安全库存、EOQ、再订货点计算都会用到这两个字段）会对这 27 个 SKU 得到虚假的"低波动"信号，而 `short_history` 标记虽然写入了输出 CSV，但没有任何下游逻辑强制检查它。
- **状态**：已确认（27 个 SKU 的事实已通过直接计算验证；该信号是否被模拟层实际读取/是否造成后续数值错误已通过 ISSUE 相关模拟审查——模拟层确实使用 `avg_monthly_units`/`demand_cv`，但未见针对 `short_history` 的特殊处理）。
- **复现/验证方法**：
  ```python
  import pandas as pd
  df = pd.read_csv("outputs/sku_profile_classification.csv")
  df[(df.sku_class == "High-Revenue Priority") & (df.months_in_window < 3)]
  # 27 rows
  ```

### ISSUE-02：`docs/management_summary.md` 仓库分配策略表与当前实际输出完全不符

- **严重程度**：业务错误
- **位置**：`docs/management_summary.md:79-84`
- **触发条件与证据**：文档给出的 6 种仓库策略 SKU 数（如"Overstock Review / Reduce Replenishment | 1,086"、"External or Limited Stock Strategy | 177"、"Standard Replenishment Review | 1,501"）与当前 `outputs/sku_inventory_simulation.csv` 的 `warehouse_strategy` 列（3,790 行）实际分布完全不一致：Standard Replenishment Review 1,164；Overstock Review 1,008；Local Warehouse Priority 748；External or Limited Stock Strategy 626；Stable Local Warehouse Inventory 171；Small-Batch 73。根因是 ISSUE-05/06 描述的 3A→3B-1 模型切换尚未同步到文档，但这里单独列出，因为它是一张具体的、会被直接引用的管理层数字表格。
- **对业务结果的影响**：管理层读者今天看到的"External or Limited Stock Strategy 适用于 177 个 SKU"，实际是 626 个——低估约 3.5 倍；其余策略数字同样系统性错误。
- **状态**：已确认
- **复现/验证方法**：
  ```python
  import pandas as pd
  pd.read_csv("outputs/sku_inventory_simulation.csv")["warehouse_strategy"].value_counts()
  ```
  与 `docs/management_summary.md:79-84` 对比。

---

## 工程隐患（Engineering Risks）

### ISSUE-03：没有回归测试锁定文档中引用的清洗关键汇总数字

- **严重程度**：工程隐患
- **位置**：`tests/test_cleaning.py`（全文件，25 个测试）
- **触发条件与证据**：该文件对匹配算法本身的业务规则覆盖得很扎实（同价优先、最近优先、部分退货不冲抵、无客户号不匹配、每笔销售只用一次、customer 15098 键入错误场景等），但没有任何测试针对真实数据集断言"最终行数=519,627""收入=£9,818,872.18""同价/异价/人工冲正匹配=2,722/93/1"。这些数字目前确实是真实的（已通过独立重算核实），但只在实际跑一遍 notebook 01 处理 `data/raw/Online Retail.xlsx` 后才能验证。`grep -n "519627\|9818872\|2722" tests/test_cleaning.py` 无匹配。
- **对业务结果的影响**：若原始文件、`config/non_product_stock_codes.csv` 或 `config/manual_reversals.csv` 发生变化，pytest 会保持全绿，但这些标题数字可能悄悄漂移，README/runbook 也不会被任何测试检测为过时。
- **状态**：已确认（这是覆盖缺口，不是运行时错误）
- **复现/验证方法**：`grep -n "519627\|9818872\|2722" tests/test_cleaning.py` 返回空。

### ISSUE-04：没有测试覆盖"高收入且短历史/高波动"的 SKU 分类边界（与 ISSUE-01 配套）

- **严重程度**：工程隐患
- **位置**：`tests/test_demand.py:82-101`（`test_classification_uses_absolute_cv_and_short_history`）
- **触发条件与证据**：该测试的 5 条 fixture 数据中，唯一的短历史用例（行 "D"）收入很低，从未构造"高收入 + `short_history=True`"或"高收入 + 高 CV"同时出现的场景——恰好就是 ISSUE-01 中真实存在的情况。
- **对业务结果的影响**：ISSUE-01 描述的优先级行为完全没有测试断言；未来重构（比如调整 `np.select` 条件顺序）不会触发任何测试失败。
- **状态**：已确认
- **复现/验证方法**：在 `tests/test_demand.py` 增加一条 `total_revenue` 达标且 `short_history=True` 的 fixture 行，检查当前实现是否仍将其判为 `High-Revenue Priority`（目前代码库中没有任何位置断言这一点）。

### ISSUE-05：所有独立文档仍描述模拟层为 Phase 3A 模型，与当前 live 实现（Phase 3B-1）完全不符

- **严重程度**：工程隐患
- **位置**：`README.md:122,143-144,283`；`docs/runbook.md:294`；`docs/management_summary.md:68,90-92,106`；`CHANGELOG.md`（整个 "Phase 3A" 条目，无 3B-1 条目）；`reports/phase1_data_correctness.md:159`；`reports/phase3a_demand_and_simulation.md:71,90-93`
- **触发条件与证据**：`grep -rn "637,919\|1,326\|135,218\|does not yet\|Phase 3B" README.md CHANGELOG.md docs/*.md reports/*.md` 在全部六个文件中都命中旧模型的数字/表述（例如 `management_summary.md:106` 写着"safety stock does not yet use a service-level target"；`phase3a_demand_and_simulation.md:91` 写着"There is no order-quantity (EOQ) logic"）。但 `config/simulation_assumptions.json` 的 `methods` 块（今天 14:49:09 写入）已经将 `safety_stock` 设为 `service_level`、`order_quantity` 设为 `eoq`，`src/retail_analytics/simulation.py` 中 `service_level_safety_stock()`、`economic_order_quantity()` 均已实现并有单元测试（见"未发现问题"部分）。`reports/phase3b1_before_after.csv` 显示的真实 live 结果与文档描述相差约 2.8 倍（库存价值）。`annual_holding_cost`、`eoq_capped_skus` 两个新指标在任何独立文档中都查不到。
- **对业务结果的影响**：阅读 `management_summary.md`（面向管理层的交付物）的人会看到与当前代码实际产出相差约 2.8 倍的资金敞口数字；接手"Phase 3B"工作的人会误以为这项工作尚未开始。
- **状态**：已确认
- **复现/验证方法**：`diff reports/baseline_end_phase3a/simulation_assumptions_phase3a.json config/simulation_assumptions.json` 可见新增的 `methods` 块；`cat reports/phase3b1_before_after.csv` 可见 live 与 3A 快照的对比数字。

### ISSUE-06：`docs/current_task.md` 将本轮范围限定为"仅第一阶段清洗"，但工作区已包含大量未提交的 3B-1 实现——存在交接协议被破坏的风险

- **严重程度**：工程隐患
- **位置**：`docs/current_task.md:26-30`（"本轮不做：不重构月均需求、需求波动与库存模拟逻辑"）
- **触发条件与证据**：`config/simulation_assumptions.json`、`src/retail_analytics/simulation.py` 中的 service-level/EOQ 代码、`tests/test_simulation.py` 中 13 个 Phase-3B-1 专用测试、以及 `reports/phase3b1_*.csv` 均已存在于同一工作区，创建时间集中在今天 14:49–14:59，早于/独立于这份任务书声明的范围。`docs/ai_workflow.md` 规定"同一时间只有一个工具修改仓库"的单写者协议。
- **对业务结果的影响**：按照 `docs/ai_workflow.md` 描述的 Claude→Codex 协议，下一轮执行者如果只读 `current_task.md` 就开始工作，可能会重复实现已经存在的 3B-1 逻辑，或者误将这些已修改的模拟文件当作"范围外噪音"而回退/忽略，破坏正在进行中的工作。
- **状态**：已确认
- **复现/验证方法**：`stat -f "%Sm %N" config/simulation_assumptions.json docs/current_task.md` 对比两者时间戳与任务书declare的范围窗口。

### ISSUE-07：working capital notebook（05）未按 `methods` 分支读取假设参数，指向纯 Phase 3A 快照配置会直接崩溃

- **严重程度**：工程隐患
- **位置**：`notebooks/05_working_capital_impact.ipynb` 提取脚本第 103 行：`holding_rate = assumptions["order_quantity"]["annual_holding_rate"]`
- **触发条件与证据**：该行无条件读取，不检查 `assumptions["methods"]["order_quantity"]`。`src/retail_analytics/simulation.py`（文档字符串第 8–13 行、`VALID_METHODS`、`PHASE_3A_METHODS`）仍将 `order_quantity: "top_up"`（Phase 3A，无 EOQ）呈现为完全支持、经过校验的合法选项，notebook 04 的 `apply_replenishment_rules` 也确实正确按此分支处理。但如果 `config/simulation_assumptions.json` 指向一份真正的纯 Phase 3A 假设文件——例如仓库里现成的 `reports/baseline_end_phase3a/simulation_assumptions_phase3a.json`（没有 `order_quantity` 键）——notebook 04 能正常跑完，notebook 05 会在算 `annual_holding_cost` 之前直接抛出 `KeyError: 'order_quantity'`。已用独立脚本验证：
  ```python
  import sys; sys.path.insert(0, "src")
  from retail_analytics import simulation
  a = simulation.load_assumptions("reports/baseline_end_phase3a/simulation_assumptions_phase3a.json")
  a["order_quantity"]["annual_holding_rate"]  # KeyError: 'order_quantity'
  ```
  （`load_assumptions` 会把 `methods` 缺省填充为 `PHASE_3A_METHODS`，因此 `validate_assumptions` 会顺利通过，问题在校验之后才炸。）
- **对业务结果的影响**：`simulation.py` 文档字符串/`VALID_METHODS` 暗示的"通过 config 同时支持 Phase 3A 和 3B-1"的说法并未端到端成立——只有 notebook 04 真正遵守了这一点。任何人（包括 Codex）尝试从冻结快照重新生成真实的 Phase 3A working-capital 数字用于对比，都会遇到未处理的崩溃而非干净结果。`tests/test_simulation.py` 不会捕获这个问题，因为这段逻辑只存在于 notebook 里，没有进入 `src/`。
- **状态**：已确认
- **复现/验证方法**：如上代码片段，未修改任何仓库文件。

### ISSUE-08：`overstock="max_stock"` 未校验必须配合 `order_quantity="eoq"`，错配时会静默退化为更弱的超储阈值

- **严重程度**：工程隐患
- **位置**：`src/retail_analytics/simulation.py:86-88`（`validate_assumptions`，仅校验 `inventory=policy_band` 需要 `order_quantity=eoq`）对比 `:294-302`（`apply_replenishment_rules` 中 `excess_threshold = max(out["max_stock_level"].fillna(out["reorder_point"]), coverage_limit_units)`）
- **触发条件与证据**：`overstock: "max_stock"` 和 `order_quantity: "top_up"` 在 `VALID_METHODS`（第 49–54 行）中都是"合法"取值，可以同时设置且通过校验。但当 `order_quantity="top_up"` 时，`max_stock_level` 会被整列设为 `NaN`（第 258 行），随后 `.fillna(reorder_point)` 会静默地把超储阈值换成一个数值上明显更弱、不同含义的值，不会抛出任何错误或警告。当前 live 配置正确地把 `overstock=max_stock` 与 `order_quantity=eoq` 配对，因此**尚未被触发**，但任何人手动改 `config/simulation_assumptions.json`（比如只想回滚其中一个方法做对比）都很容易掉进这个坑，得到静默错误的超储/`excess_units`/`warehouse_strategy` 数字。
- **对业务结果的影响**：潜在（当前未触发）——一旦触发，超储风险判定和相关资金敞口会用错误的阈值计算，且不会报错。
- **状态**：已确认（代码路径已通过阅读两个函数交叉验证；当前数据未触发）
- **复现/验证方法**：
  ```python
  import copy
  assumptions = copy.deepcopy(loaded)
  assumptions["methods"]["order_quantity"] = "top_up"
  assumptions["methods"]["overstock"] = "max_stock"
  simulation.validate_assumptions(assumptions)  # 通过，无报错
  simulation.apply_replenishment_rules(profile, assumptions)  # max_stock_level 全 NaN，excess_units 仍被计算
  ```

### ISSUE-09：只有 `policy_band`+`eoq` 这一组跨字段依赖被校验/测试过，其余方法组合行为未知

- **严重程度**：工程隐患
- **位置**：`src/retail_analytics/simulation.py`（`VALID_METHODS`、`validate_assumptions` 约 51–57、87–88 行）；`tests/test_simulation.py:246-248`
- **触发条件与证据**：唯一被测试的跨字段校验是 `test_policy_band_requires_eoq`。没有测试覆盖诸如 `inventory=fixed_range` + `safety_stock=service_level`，或 `overstock=max_stock` + `inventory=fixed_range` 等其它混搭组合（ISSUE-08 是其中已确认有问题的一种；其余组合尚未逐一验证）。
- **对业务结果的影响**：未知/待验证——若未来配置出现其它不一致组合，是静默给出错误数字还是明确报错，目前没有任何测试或文档给出保证。
- **状态**：待验证假设
- **复现/验证方法**：在临时脚本中尝试 `simulation.with_methods(assumptions, inventory="fixed_range", safety_stock="service_level")` 等组合，观察是抛出异常还是静默计算出某个结果。

---

## 可选改进（Optional Improvements）

### ISSUE-10：5 个人工冲正候选中有 4 个仍未审核（涉及金额约 £32，影响很小）

- **严重程度**：可选改进
- **位置**：`data/processed/manual_credit_candidates.csv`（第 2–5 行）
- **触发条件与证据**：候选记录 C578073（£20.16）、C546870（£5.00，*存在歧义*——对应两条不同 stock_code 77101A/21390、金额相同的候选销售行）、C567867（£4.00）、C558712（£2.95），`reviewed_in_config=False`。这是按设计正确地"只报告、不擅自处理"（`cleaning.py:308-354`），不是 bug——但用户此前收到的交接报告完全没有提到这 4 条待审核记录的存在。
- **对业务结果的影响**：若未来审核后将其加入 `config/manual_reversals.csv`，收入会减少不超过 £32.11，`fully_reversed_sales_removed`/`manual_credit_reversals_removed` 计数会有微小变化。
- **状态**：已确认
- **复现/验证方法**：直接查看 `data/processed/manual_credit_candidates.csv` 第 2–5 行。

### ISSUE-11：`CHANGELOG.md` 低估了当前测试数量/覆盖范围

- **严重程度**：可选改进
- **位置**：`CHANGELOG.md:28`（"tests/test_simulation.py (7 tests)"）；`reports/phase3a_demand_and_simulation.md:91`（"43 tests pass"）
- **触发条件与证据**：`source .venv/bin/activate && python -m pytest -v` 当前显示 `tests/test_simulation.py` 有 20 个测试，总计 **59 个通过**（22 清洗 + 6 需求 + 3 repo_layout + 20 模拟 + 8 输入校验）。多出的 13 个模拟测试（`tests/test_simulation.py:93-260`）和 3 个 `tests/test_repo_layout.py` 测试是 Phase-3B-1 时期新增的，CHANGELOG 未同步记录。
- **对业务结果的影响**：不影响正确性，但会让审查者低估（未文档化的）3B-1 逻辑实际已有的测试覆盖程度。
- **状态**：已确认
- **复现/验证方法**：`source .venv/bin/activate && python -m pytest -v`（从仓库根目录运行）。

### ISSUE-12：归因表（attribution）的中间步骤容易被误读为回归

- **严重程度**：可选改进
- **位置**：`reports/phase3b1_attribution.csv`（第 0–4 行）
- **触发条件与证据**：该表按方法逐项切换、从 Phase 3A 走到 Phase 3B-1。若只单独打开"仅启用 `service_level` 安全库存"这一步（尚未切换 `inventory` 为 `policy_band`），缺货风险 SKU 数会飙升到 **1,855**——比 Phase 3A（1,326）和最终 3B-1（536）都更差，原因是旧的 `fixed_range` 当前库存随机取值（20–299 件）没有随新的、明显更高的再订货点（安全库存中位数从 10 升到 33 件）同步调整。只有第 4 步（把 `inventory` 也切到 `policy_band`，让当前库存与该 SKU 自己的再订货点挂钩）才会解决这个问题。
- **对业务结果的影响**：如果 Codex 或后续审查者只对比"切换前"与"切换后"两端数字，而不看完整的归因链条，可能会误以为中间引入了一次真实的模型回归。
- **状态**：已确认
- **复现/验证方法**：直接读取 `reports/phase3b1_attribution.csv` 第 0–4 行，对比 `stockout_risk_sku_count` 列。

---

## 已核实、未发现问题的部分（供参考，避免遗漏）

- 取消订单/冲正匹配算法本身（`src/retail_analytics/cleaning.py` 的 `match_full_cancellations`、`apply_manual_reversals`）：未匹配的取消订单不会静默影响收入；每笔销售只会被匹配一次；人工冲正校验失败会显式报错而非静默跳过。
- 非商品行排除清单（`config/non_product_stock_codes.csv`）与价格异常检测（`data/processed/price_anomalies.csv`）：分类互斥性、前缀规则校验、£649.50 键入错误重开发票场景均按文档描述正确处理。
- 需求计算的 12 个月窗口逻辑、首月对齐、截断月份补零（`src/retail_analytics/demand.py:29-58`）：与文档字符串一致，4 个单元测试覆盖，`90214U` 场景复现无误。
- CV 除零/单点标准差处理：显式处理，有测试覆盖。
- Phase 3A → 3B-1 的切换本身（`config/simulation_assumptions.json` 的 `methods` 字段与 `simulation.py` 的调度逻辑）：经代码交叉核实，`load_assumptions`/`simulate_inventory_fields`/`apply_replenishment_rules` 均真实按 `methods` 动态分支，配置文件是名副其实的唯一事实来源，不是摆设；`reports/phase3b1_attribution.csv` 逐步验证一致。**这是一次真实、正确实现的模型升级，不是 bug、缓存问题或被忽略的配置**。
- `z_score`/EOQ 的边界处理：服务水平校验域 `[0.5, 1)` 防止 `inv_cdf(1.0)` 产生 `inf`；EOQ 对零需求/零成本用 `errstate` + 掩码处理，不会泄漏 NaN/inf；180 天封顶保证 `max_stock_level ≥ reorder_point`。
- `policy_band` 库存位置的负值裁剪（`simulation.py:278`，`clip(0, None)`）：会正确把过低的 `p` 值地板到 0，进而被正确判定为缺货风险，符合设计意图。
- notebook 05 "重新模拟并与 04 保存结果做 `assert_frame_equal` 一致性检查"的说法：**已核实为真**，与之前报告的描述一致。
- KPI/资金指标聚合口径：库存总价值、缺货/超储资金敞口、风险 SKU 计数之和（536+1008+2246=3790）、仓库策略计数（6 类）在 `management_kpi_summary.csv`、`working_capital_summary.csv`、`inventory_value_by_sku_class.csv`、`inventory_value_by_warehouse_strategy.csv` 之间完全一致，无重复计算或聚合错误。
- 单位成本（`unit_cost = avg_unit_price × cost_ratio`）只计算一次，被 notebook 04、05 一致复用，无重复应用。
- 取消匹配数字（2,722 同价 / 93 异价 / 1 人工冲正）与收入（£9,818,872.18）、清洗后行数（519,627）在 README、runbook、management_summary、CHANGELOG、`docs/current_task.md`、`reports/phase1_data_correctness.md` 之间完全一致，也与 `data/processed/reversed_sales.csv` 实际内容吻合。`requirements-dev.txt` 的 `pytest>=8,<10` 约束与实际安装的 9.1.1 无冲突。

## 未覆盖 / 需要后续验证的边界

- ISSUE-09 所列的其它方法组合（除 ISSUE-08 已确认的 `max_stock`+`top_up`）尚未逐一验证行为。
- 原始 `data/raw/Online Retail.xlsx` 层面是否存在清洗规则之外的数据质量问题（如重复发票行、非 ASCII SKU 编码等）未在本轮深入排查，仅确认了现有测试对已知场景的覆盖情况。
- 本报告基于单一时间点快照；由于确认另一会话正在并行修改仓库，实际当前状态可能已经与本报告描述的又不相同，建议 Codex 接手前重新核对 `git status` 与关键文件时间戳。

## 后续处理

本报告不包含任何修复实现，按要求在完成诊断后停止。请交由 Codex 按 `docs/ai_workflow.md` 描述的流程独立复核，包括重新核实业务规则、边界情况与文档一致性；范围外问题（如 ISSUE-09 的完整组合验证）建议列入后续轮次。

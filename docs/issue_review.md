# 独立复核报告（Issue Review）

对 `docs/issue_audit.md` 的 12 项问题逐条独立复核。复核不预设原报告成立，逐项重新读代码、重新算数字、重新查文档，能推翻的就推翻，能证伪"遗漏"的就证伪。本轮**不修改任何业务代码**。

## 一、复核基线核对

- 分支：`phase1-data-correctness`，HEAD：`1e73781429f09d310a4c75e5e94eb085aa3b0fb1`（与诊断阶段一致，未变化）。
- `tmp/audit_snapshot_manifest.txt`（诊断阶段 15:31 记录的 7 个关键可变文件哈希）逐一比对：**全部一致，无变化**。补充用 `find . -newer tmp/audit_snapshot_manifest.txt` 扫描整个工作区（排除 `.git`/`.venv`/缓存目录），确认自 15:31 起唯一变化的文件是本会话自己新增/编辑的 `docs/issue_audit.md` 和 `docs/ai_workflow.md`——**没有第三方改动**，本次复核可以视为针对与诊断阶段相同的工作区状态。
- 当前实际启用的模型/配置：`config/simulation_assumptions.json` 的 `methods` 字段为 `inventory=policy_band`、`safety_stock=service_level`、`order_quantity=eoq`、`overstock=max_stock`，即诊断报告所称的 **Phase 3B-1**。`src/retail_analytics/simulation.py` 的 `load_assumptions`/`simulate_inventory_fields`/`apply_replenishment_rules` 均按此字段动态分支，配置文件是真实生效的事实来源（诊断阶段已核实，本次复核未发现相反证据）。
- 说明：manifest 只是一份哈希记录，其存在本身不代表诊断时使用了不可变快照——它能证明"截至目前没有第三方改动"，但不能替代对每项结论的重新验证；因此以下每一条仍然是独立重新取证，而非仅对照 manifest 后直接采信原文。

## 二、逐项复核结论

### ISSUE-01（原：业务错误——高收入分类忽略短历史/高波动）
**结论：部分成立**——原文把它定性为"分类逻辑 bug"是夸大的；这是一个**已在代码中写明的设计选择**，且受影响的标志位在下游完全没被使用。

- `src/retail_analytics/demand.py:126-133` 的函数文档明确写着"the first matching rule wins... 1. High-Revenue Priority: total revenue at or above the revenue quantile"——收入优先于波动性是文档化的既定顺序，不是笔误或条件顺序意外。notebook 03 的说明文字也只在 High-Turnover 层级讨论 `short_history`，从未暗示它应该反过来限制 Priority 分类。
- `short_history` 这个字段在 `src/` 下只出现在 `demand.py` 自身（定义、输出列、以及仅用于 High-Turnover Stable/Volatile 判定的一行），`simulation.py` 和 notebook 04 从未读取它——也就是说，即便分类顺序"有问题"，也没有任何下游安全库存/EOQ 逻辑会因此受到影响。
- 实测对比 27 个短历史高收入 SKU 与其余 731 个正常历史高收入 SKU：`safety_stock/avg_monthly_units` 中位数 0.90 对 0.88（并不更低），缺货风险占比 18.5% 对 20.9%（并不更高）——不存在原文暗示的"系统性偏弱的安全库存"。
- 唯一真实需要关注的是单个 SKU `23552`：仅 1 个月历史、`demand_cv=0.000`、`safety_stock=0.0`——这是货真价实的"数据点太少导致 CV 本身没有意义"的边界情形，但目前 `inventory_risk` 显示为 "Normal"，尚未造成可观测的错误结果。
- 处理建议：不作为"分类逻辑缺陷"修复，而是转化为一个业务口径问题（见下文"需要决定的业务口径 D1"）+ 一条测试补充（见 ISSUE-04）。

### ISSUE-02（原：业务错误——management_summary.md 仓库策略表与实际不符）
**结论：确认**——逐字重读 `docs/management_summary.md:79-84` 与独立重新计算 `outputs/sku_inventory_simulation.csv` 的 `warehouse_strategy` 分布，六个类别全部对不上（如 "External or Limited Stock Strategy"：文档写 177，实际 626），原文引用的具体数字准确无误，无需修正。

### ISSUE-03（原：工程隐患——清洗阶段无测试锁定关键汇总数字）
**结论：部分成立**——测试层面的缺口是真的，但原文"没有任何机制能发现漂移"的表述过于绝对，遗漏了已存在的人工兜底机制，也遗漏了库里已有可直接照抄的模板。

- 确认 `tests/test_cleaning.py`、`test_validate_input_data.py`、`test_repo_layout.py`、`conftest.py` 都不加载 `data/raw/Online Retail.xlsx` 或断言这些聚合数字，`grep` 全仓库测试文件仅在一处注释里出现相关数字。
- 但 `scripts/compare_to_baseline.py` + `reports/baseline_end_phase1`、`baseline_end_phase3a` 已经构成一套人工触发的基线比对机制——只是没有接入 pytest/CI（仓库里没有 `.github/workflows`、`Makefile`、`tox.ini`，`pytest.ini` 也没有关联它），需要人记得手动运行 `scripts/verify_pipeline.sh`。更准确的表述是"漂移检测存在但未自动化"，而不是"完全没有防护"。
- 库里已有现成先例可以直接照搬：`tests/test_simulation.py:213` 已经用 `@pytest.mark.skipif` + 对比 `reports/baseline_end_phase3a/outputs/sku_inventory_simulation.csv` 快照的方式，在 pytest 里锁定了模拟层的回归结果，且实测确实会真正执行（不是被跳过）。给清洗阶段加一条同类测试是照抄现成模式，不是要新建一种测试哲学，也不属于容易变得脆弱的"精确对拍活数据"反模式（因为 `Online Retail.xlsx` 是静态历史数据集，不会自己变化）。

### ISSUE-04（原：工程隐患——无测试覆盖"高收入+短历史/高CV"边界）
**结论：部分成立**——缺口比原文描述的窄。`tests/test_demand.py:82-101` 的 fixture "A"（`total_revenue=1000` 达标、`demand_cv=3.0`、`short_history=False`）其实已经断言"高 CV 也会被收入分类覆盖"，也就是说 ISSUE-01 讨论的这条优先级规则，**在"高 CV"这条路径上是有测试锁定的**；真正缺失的只是"短历史"这一条路径的对应用例。原文"该行为完全没有测试断言"的说法不准确，应改为"部分路径已覆盖，short_history 路径未覆盖"。

### ISSUE-05（原：工程隐患——所有文档都停留在 Phase 3A 描述）
**结论：部分成立**——对"活文档"成立，对两份历史阶段报告不成立。

- `README.md:283`、`docs/runbook.md:294`、`docs/management_summary.md:106`、`CHANGELOG.md`（完全没有 3B-1 相关条目）——这四份文档理应反映"当前状态"，逐一 grep 确认它们仍将 service_level/EOQ/policy_band/max_stock 描述为"计划中"或完全不提，而这些功能已经是 live 配置的默认值。
- 但 `reports/phase1_data_correctness.md`、`reports/phase3a_demand_and_snapshot.md`（原文一并列入）是**带日期的阶段性归档报告**，不是持续维护的文档——它们写作时 Phase 3B-1 确实还没发生，把"没提到后来才做的事"定性为"过时"并不公平。这两份报告应该从本条移除，标记为按设计如此，不需要修改。

### ISSUE-06（原：工程隐患——current_task.md 范围与工作区实际状态脱节）
**结论：部分成立，且根因需要改写**——原文认为是"任务书写完之后 3B-1 才悄悄出现"，实际时间线相反，根因应改为**分支治理问题**，而不是"文档没跟上"。

- 复核时间戳：`docs/current_task.md` 的 mtime 是 **15:19:28**，晚于 `config/simulation_assumptions.json`、`src/retail_analytics/simulation.py`（均为 14:49:09）和 `tests/test_simulation.py`（14:50:19）。也就是说，任务书是在 3B-1 的改动**已经存在于工作区之后**才写的，而且写完之后仍然明确把"重构需求/模拟逻辑"划为"下一轮"——这不是信息滞后，而是**同一个分支上同时存在两轮不同范围的工作**。
- `docs/ai_workflow.md` 自己第 2 条规则要求"每轮使用一个独立分支"，第 3 条要求"同一时间只有一个工具修改仓库"。当前工作区里，"本轮"（仅第一阶段清洗）与另一会话的 3B-1 实现明显是在同一个分支（`phase1-data-correctness`）上并行发生的，这直接违反了这两条协议自身的规则。这是一个需要人决定如何梳理的**流程治理问题**，不是"补一份文档"就能解决的，见下文"需要决定的业务口径 D2"。

### ISSUE-07（原：工程隐患——notebook 05 遇旧配置会 KeyError）
**结论：部分成立，定位和影响范围需要修正，且比原文更严重**——问题真实存在，但崩溃点、影响面都被原文说错了。

- 独立复现确认：`load_assumptions()` 对缺失 `order_quantity` 键的配置（如 `reports/baseline_end_phase3a/simulation_assumptions_phase3a.json`）确实会顺利通过 `validate_assumptions`，因为该函数只在 `methods.order_quantity=="eoq"` 时才检查 `order_quantity` 段是否存在（`simulation.py:109`），`top_up` 分支完全不做这个检查。
- 但**真正先崩溃的不是 notebook 05**，而是 `src/retail_analytics/simulation.py:252-253` 里的 `apply_replenishment_rules`——`oq = assumptions["order_quantity"]` 这一行在检查 `methods["order_quantity"]` 具体取值**之前**就无条件执行，而它算出来的 `annual_demand_units` 只在 `eoq` 分支（`simulation.py:261`）里被用到，`top_up` 分支下完全用不着。这明显是 3B-1 重构时把共享变量提到分支外面时漏改的遗留问题。**notebook 04 会先于 notebook 05 崩溃**，原文"notebook 04 能正常跑完，notebook 05 才崩溃"的说法是错的。
- 而且这个模式不止一处：`scripts/attribute_model_changes.py:60` 有完全相同的无条件读取，是第三个受影响的位置（原文只发现了 notebook 05 一处）。
- 触发条件也比原文描述的更宽：不需要真的去读取冻结快照文件——任何把 `methods.order_quantity` 设为 `"top_up"`（这是 `VALID_METHODS` 里完全合法、`simulation.py` 文档字符串里明确并列的选项，不是"遗留/不支持"格式）但配置里缺少 `order_quantity` 段的情况都会触发，而 `compare_to_baseline.py` 确认没有任何现成脚本会自动把冻结快照重新接回 live 模拟，所以触发方式确实需要人工改配置，但触发条件本身并不罕见或反常。

### ISSUE-08（原：工程隐患——overstock=max_stock 配 order_quantity=top_up 静默出错）
**结论：确认**——独立复现结果与原文完全一致，严重程度评估没有夸大。

- 独立构造该方法组合，确认 `validate_assumptions` 真的会放行，`max_stock_level` 真的会全部变成 `NaN`，随后被 `fillna(reorder_point)` 兜底。
- 进一步核实这个兜底值是否"合理但换了定义"还是"确实错误"：`config/simulation_assumptions.json` 自己注释的 `max_stock` 定义是 `max(reorder_point + EOQ, coverage_days of demand)`，而兜底之后变成 `max(reorder_point, coverage_days of demand)`——凭空少了 EOQ 这一项，EOQ 通常是几周到几个月的订货量，不是可以忽略的小数，所以这不是"换了个同样合理的定义"，而是有效超储门槛系统性偏低，会让更多 SKU 被误判为超储风险，且没有任何输出提示用了不同定义（零需求 SKU 是例外，因为此时 EOQ 本身就是 0，兜底值恰好与真实定义一致）。
- 核实这个组合目前是否真的没被触发：`scripts/attribute_model_changes.py` 里驱动 `reports/phase3b1_attribution.csv` 的步骤顺序，始终是先开 `order_quantity=eoq`（第 2 步）再开 `overstock=max_stock`（第 3 步），现有工具链确实从未走到过这个组合，原文"潜在、当前未触发"的判断准确。

### ISSUE-09（原：工程隐患/待验证假设——其它方法组合未验证）
**结论：部分成立，并入 ISSUE-08，不再作为独立事项**——实测了三个此前未验证的组合（`fixed_range`+`service_level`、`policy_band`+`coverage_only`、`volatility_factor`+`eoq`），全部通过校验且运行正常，没有发现新问题；唯一有问题的组合就是 ISSUE-08 已经确认的 `max_stock`+`top_up`。建议在最终清单中把 ISSUE-09 归并为 ISSUE-08 的补充证据，不再单列。

### ISSUE-10（原：可选改进——4 个人工冲正候选未被提及）
**结论：不成立（按原文的框架）**——"未被提及"这个具体说法是错的。`reports/phase1_data_correctness.md:144-148` 已经明确写道："`manual_credit_candidates.csv`: 5 candidates. `C556445` is reviewed and applied. The other 4 are worth £2.95–£20.16, and 3 of them match several sale lines, so they are left in place."——这份先于诊断报告存在的归档报告已经完整说明了这件事。£32 涉及金额、4 条未审核的事实本身没有错，但"此前的报告完全没提到"这个结论要撤回，不需要作为新发现处理。

### ISSUE-11（原：可选改进——CHANGELOG 测试数量过时）
**结论：确认**——独立重跑 `pytest --collect-only -q` 得到 22+6+3+20+8=59，与原文一致；`CHANGELOG.md:28` "tests/test_simulation.py (7 tests)" 逐字确认属实。唯一需要修正的是引用行号：`reports/phase3a_demand_and_simulation.md` 里 "43 tests pass" 实际在第 **87** 行，原文写的第 91 行有偏差。

### ISSUE-12（原：可选改进——归因表中间步骤易被误读）
**结论：确认**——`reports/phase3b1_attribution.csv` 第 1 行（仅启用 service_level，尚未切换 policy_band）确实显示缺货风险 1,855，比 Phase 3A（1,326）和最终 Phase 3B-1（536）都差，与原文描述完全一致。是否构成"问题"是个判断题，但考虑到这是一个会被保留、可能被后续审查者单独打开查看的真实产出文件，加一句说明性备注的成本很低，原文的可选改进定级合适，予以保留。

## 三、复核结论汇总表

| 编号 | 原定性 | 复核结论 | 说明 |
| --- | --- | --- | --- |
| ISSUE-01 | 业务错误 | 部分成立 | 是文档化设计，非 bug；`short_history` 未被下游使用；仅 1 个 SKU 是真实边界情形 → 转为业务口径问题 D1 |
| ISSUE-02 | 业务错误 | 确认 | 数字核对无误 |
| ISSUE-03 | 工程隐患 | 部分成立 | 已有人工兜底机制，且有现成 pytest 模板可抄 |
| ISSUE-04 | 工程隐患 | 部分成立 | 高 CV 路径已有测试，仅缺 short_history 路径 |
| ISSUE-05 | 工程隐患 | 部分成立 | 仅对活文档成立，两份历史阶段报告不应被认定为过时 |
| ISSUE-06 | 工程隐患 | 部分成立（根因改写） | 是分支治理问题，非文档滞后 → 转为业务口径问题 D2 |
| ISSUE-07 | 工程隐患 | 部分成立（定位修正，影响更大） | 实际先崩溃在 notebook 04/`simulation.py:252-253`，还有第三处同类隐患 |
| ISSUE-08 | 工程隐患 | 确认 | 复现一致，无需修正 |
| ISSUE-09 | 工程隐患/待验证假设 | 部分成立 → 并入 ISSUE-08 | 其余组合验证正常 |
| ISSUE-10 | 可选改进 | 不成立（按原框架） | 已在 `reports/phase1_data_correctness.md:144-148` 说明 |
| ISSUE-11 | 可选改进 | 确认（行号小修正） | — |
| ISSUE-12 | 可选改进 | 确认 | — |

## 四、方法说明

本轮复核由 4 个并行的独立读代码/重新取证过程完成，分别覆盖：分类逻辑（ISSUE-01/04/09/10）、模拟配置兼容性（ISSUE-07/08）、文档一致性（ISSUE-02/05/06/11/12）、测试覆盖框架判断（ISSUE-03）。每个过程都被要求不预设原结论成立，独立重新读取文件、重新运行只读验证（pytest、独立 Python 脚本核算），未对仓库做任何写入。

# 本轮交接

状态：本轮（实施 R1/T1/T2/E1，`audit/model-assumptions` 分支）Claude 实施已完成，等待 Codex 最终验收。模型假设诊断 + Codex 独立复核、以及更早的 R1–R8 实施 + Codex 验收（已提交 `50ce335`）记录完整保留在下方"历史交接"部分。

## 本轮交接：实施 R1/T1/T2/E1（模型假设诊断的复核后方案）

### Git 状态

- 分支：`audit/model-assumptions`（延续自诊断/复核轮，未新建分支）。起点仍为 `50ce335c2d5c8f20bbecc1e9eeae44745b076879`，本轮全程未变化。
- 开始前重新核实：`git status --short` 只有 `docs/current_task.md`、`docs/handoff.md` 被 Claude 修改，`docs/model_assumptions_audit.md`（Claude 诊断）、`docs/model_assumptions_review.md`、`docs/model_assumptions_plan.md`（均为 Codex 复核轮产物）未跟踪；暂存区为空——与 Codex 复核记录的交接状态一致。
- 本轮由本会话单独实施，未启动其他并行修改会话。
- 是否已 commit / push：否。本轮全程未修改任何正式 `config/`、notebook 或正式 `outputs/`/`data/processed/` 文件。

### 完成内容

| 文件 | 修改内容与理由 |
| --- | --- |
| `docs/model_assumptions_audit.md` | **R1**：顶部加入醒目横幅，标明结论已被 `docs/model_assumptions_review.md` 复核修正（含 MA-04 的 699/1,008 只属于固定库存实验这一关键澄清），链接到复核与方案文档；原文其余部分不改，作为诊断过程的历史记录保留。 |
| `docs/runbook.md` | **R1**：①纠正 `overstock_capital_exposure` 的定义（`## Metric Definitions`，原文误写为"超过 180 天需求的单位数"，改为当前 `max_stock` 方法的真实有效阈值 `max(ROP+Q, d×overstock.coverage_days)`，并与旧 `coverage_only` 方法的定义分开说明）；②在"Demand Basis and Classification"新增"What `demand_cv` actually measures"说明（含经验矩恒等式、r=0.840224、有效 3,789/3,790 SKU、撤回"主要衡量间歇性"的过度推断）和"`months_in_window==3` 不等于 `short_history`"的边界澄清；③在"Simulated Inventory Layer"新增"Parameter calibration status"段落，把 `ordering_cost_gbp`/`annual_holding_rate`/`max_order_coverage_days`/`overstock.coverage_days`/`supplier_lead_time_days`/服务水平标为"演示/待校准"，责任人与校准日期写明"未定"，不虚构；④在"Tests and Comparisons"新增 `scripts/model_assumptions_diagnostics.py` 的用法说明。 |
| `tests/test_demand_simulation_interface.py`（新建，8 个测试） | **T1**：0/1/2/3 个月观测通过真实 `full_months`/`build_demand_panel`/`build_sku_profile`/`classify_skus`/`simulation.simulate` 端到端验证——不手写跳过中间步骤的模拟输入。覆盖：仅截断月（`no_full_month_sales`，`zero_month_share` 为 NaN）、单月观测（`short_history=True`，std/CV 按约定置 0，注释明确"不代表已证明需求稳定"）、2 月与 3 月边界（3 月**不是** `short_history`，用非退化数据手算验证样本标准差）、高收入短历史通过真实分类流程仍得 Priority、零需求 SKU 库存 0/>0 分别得 Normal/Overstock Risk（用配置深拷贝固定 `policy_band.no_demand_units`，不改 live 参数）。 |
| `tests/test_simulation.py`（新增 12 个测试） | **T2**：EOQ 在整数化上限的相等边界（不封顶）与刚超过边界（封顶）；极小正需求下封顶值不为 0 的下限保护；订货成本提高不减少 EOQ、持有率或单位成本提高不增加 EOQ、放宽上限不减少最终订货量的单调性；当前库存恰等于再订货点（非缺货）、恰等于 `max_stock_level`（非超储）、超出一单位（超储）的严格比较边界；补货缺口超过封顶 EOQ 时用 `max(Q, shortfall)` 取缺口而非被 Q 的上限误伤；固定库存实验（`methods.inventory="fixed_range"` 跳过库存重写，ROP/SS/库存不变，仅阈值随配置变化）与完整重生成实验（`policy_position`/ROP/SS 不受上限影响，但库存随 EOQ 变化）的对照，証明两种实验方法论确实不同。所有新断言检验的是任意合法参数下的不变量，不锁定当前 `capped≈59%`、`699`、`1,008` 等诊断快照数字为跨配置的通用正确答案。 |
| `scripts/model_assumptions_diagnostics.py`（新建） | **E1**：显式接收 `--profile`/`--config`/`--output-dir`（必填），拒绝写入或指向仓库的 `outputs/`/`config/`/`data/`/`notebooks/`/`reports/`/`src/`/`tests/`/`docs/`/`scripts/`/仓库根目录本身（含这些目录的祖先路径）。支持固定库存实验 `A`（复用真实、未修改的 `simulation.apply_replenishment_rules`，通过 `methods.inventory="fixed_range"` 让函数跳过其库存重写分支，不重新实现任何业务逻辑）、完整重生成实验 `B`（真实 `simulation.simulate`），以及九个敏感性场景（`1a/1b/2a/2b/3a/3b/4a/4b/5`）。每个场景从基线配置的深拷贝构建，场景之间不共享可变状态。输出 `run_metadata.json`（代码提交号、工作区是否脏污及未提交文件列表/diff 哈希、输入 profile 与配置的 SHA-256、Python/numpy/pandas 版本、seed、每个场景的实际参数变化值）、`scenario_summary.csv`（每个场景的风险数量、缺货件数、补货总件数、库存价值、年度持有成本、缺货收入敞口、超储资金敞口、EOQ 封顶数——数量与金额总是一起报告）、`field_change_counts.csv`（关键字段变化的 SKU 数）、`risk_transitions/*.csv`（每个场景相对基线的风险转移矩阵）。不做任何参数寻优或"最佳参数"回写。 |

### 验证证据

| 时间与环境 | 实际命令 | 结果 |
| --- | --- | --- |
| 2026-09-17（延续），项目 `.venv`（Python 3.11.5, pandas 3.0.3, numpy 2.4.6, pytest 9.1.1） | `source .venv/bin/activate && python -m pytest -W error -ra -v` | **98 passed, 0 skipped**（78 基线 + 8 个 T1 + 12 个 T2）。 |
| 同上 | `python scripts/model_assumptions_diagnostics.py --profile outputs/sku_inventory_simulation.csv --config config/simulation_assumptions.json --output-dir /tmp/model_assumptions_diag_run1 --scenarios all` | 成功。先验证基线配置下 `simulate()` 与已保存的 `outputs/sku_inventory_simulation.csv` 逐字段一致，再输出全部场景。**基线、A、B 及九个敏感性场景的库存价值、风险数量、缺货件数、年度持有成本、缺货收入敞口、超储资金敞口，与 `docs/model_assumptions_review.md` 表 5.2/8.2 的数字逐项精确匹配**（例如 B 的库存价值 £1,927,678.57、缺货 565/超储 1,043、缺货收入敞口 £87,496.40，均与复核报告一致到便士）。风险转移矩阵同样精确匹配（A：超储→Normal 699；B：Normal→超储 35、Normal→缺货 29）；字段变化计数同样匹配（A 当前库存改变 0、B 当前库存改变 2,171；A/B 的 ROP/SS 改变均为 0）。 |
| 同上 | 用相同参数重跑一次（`--output-dir /tmp/model_assumptions_diag_run2`），`diff` 两次的 `scenario_summary.csv`、`field_change_counts.csv` | **逐字节一致**——满足"相同输入重跑结果一致"的验收标准。 |
| 同上 | 独立验证脚本内部对固定库存实验 A 的断言：`current_inventory` 在 A 中必须与输入完全一致，否则脚本自身 `raise SystemExit` | 通过；另外用 `field_change_counts.csv` 核实 A 的 `current_inventory_changed_skus=0`，B 的为 2,171——固定库存实验确实保持库存不变，完整重生成实验确实允许库存变化。 |
| 同上 | 尝试 `--output-dir outputs`、`config`、`outputs/subdir`、`.`（仓库根目录）、`data/processed` | 全部被拒绝并给出清晰错误信息，`echo $?` 确认退出码为 1（非 0）；确认防覆盖护栏对官方目录及其祖先路径均生效。 |
| 同上 | T1 变异验证（仅在 `/tmp/t1_mutation/` 临时副本中进行，未触碰仓库文件）：分别对 `demand.py` 的临时副本应用"移除首销前过滤（补零提前）""`full_months` 不再排除截断月""移除 `std_monthly_units` 的 NaN 填充""`short_history` 判定 `<3` 改为 `<=3`" 四处变异，用独立脚本加载变异后的模块并重跑对应断言 | **四处变异全部被对应的新测试断言捕获**（分别报告 `months_in_window=11`、`no_full_month_sales=False`、`std_monthly_units=nan`、`short_history=True`，均与预期的正确行为相反）。验证后临时目录已删除，未改动仓库内 `demand.py`。 |
| 同上 | T2 变异验证（仅在 `/tmp/t2_mutation/` 临时副本中进行）：对 `simulation.py` 的临时副本分别应用"超储判定 `>` 改为 `>=`""EOQ 封顶逻辑被误删（直接用未封顶值且 `eoq_capped=False`）" | **两处变异均被对应的新测试断言捕获**（分别报告恰好等于 `max_stock_level` 时被误判为 Overstock Risk、封顶应为 180 却返回未封顶的 190）。验证后临时目录已删除，未改动仓库内 `simulation.py`。 |
| 同上 | `git status --short`（本轮结束前） | 仅 `docs/current_task.md`、`docs/handoff.md`、`docs/runbook.md`、`tests/test_simulation.py` 为修改，`docs/model_assumptions_audit.md`（诊断轮遗留）、`docs/model_assumptions_plan.md`/`docs/model_assumptions_review.md`（复核轮遗留）、`scripts/model_assumptions_diagnostics.py`、`tests/test_demand_simulation_interface.py` 为新增；`config/`、`outputs/`、`data/`、`notebooks/` 均未出现在差异中——确认正式文件未被改写。 |

- **关键数据与比较基线：** E1 的全部场景以当前 live `config/simulation_assumptions.json`（未修改）与 `outputs/sku_inventory_simulation.csv`（未修改）为基线读取源；T1/T2 的新测试使用独立的合成 fixture 或对 `assumptions` 的深拷贝，不依赖也不修改这两个正式文件。
- **未执行的验证及原因：**
  - 未进入 B1（业务参数校准）或重开 B2/D1——按用户明确指令排除在本轮之外；`docs/model_assumptions_plan.md` §7–9 列出的业务决定事项均原样保留待用户决定。
  - 未对 T1/T2 之外的既有测试做变异验证（例如未重新验证 R1/R2 轮已经做过的变异测试）——那些在上一轮已完成并记录在"历史交接"中，本轮不重复。
  - 未修改 `docs/management_summary.md`/`README.md`——本轮 R1 的范围经用户信息聚焦于 runbook 的有效超储阈值定义纠正和参数校准状态标注；`docs/model_assumptions_plan.md` §3 提到的 README/management_summary 更新留待用户确认是否需要在下一轮一并处理（这两份文档目前没有与 runbook 相同的错误定义，只是不如 runbook 详细）。
- **已知问题与后续事项：** 无本轮新发现的业务代码缺陷（T1/T2 的边界测试全部通过，未发现违反既有合同的实际输出）。剩余事项与上一轮 Codex 方案一致：是否进入 B1 业务校准、是否重开 B2/D1，均待用户决定。
- **已停止修改，可以交给 Codex：** 是。本轮到此为止未再修改任何业务代码、notebook、正式配置或正式输出；本文件更新完成后不再变更。

## 历史交接：模型假设诊断 + Codex 独立复核与方案（`audit/model-assumptions` 分支，已完成）

### Git 状态

- 分支：`audit/model-assumptions`（本轮新建）。起点：`50ce335c2d5c8f20bbecc1e9eeae44745b076879`（上一轮已提交的成果，父提交 `1e73781`）。
- 开始前工作区状态：干净（`git status --short` 为空），与用户告知的"上一轮已提交"一致——已实际执行 `git status`/`git log`/`git branch -a` 重新核实，不是直接采信用户转述。`audit/model-assumptions` 分支此前不存在，无需检查既有用途，直接从 `50ce335` 创建。
- 本轮由本会话单独诊断，未启动其他修改会话（无并行写入需要检查）。
- 是否已 commit / push：否。本轮全程未修改任何业务代码、`config/`、notebook 或正式 `outputs/`/`data/processed/` 文件——只新增/修改了 `docs/model_assumptions_audit.md`（新建）、`docs/current_task.md`、`docs/handoff.md`（本文件）。

### 完成内容

| 文件 | 修改内容与理由 |
| --- | --- |
| `docs/model_assumptions_audit.md`（新建） | 完整诊断报告：基线/环境/实际命令、6 个编号问题（MA-01 至 MA-06，含类型区分：已确认问题/待验证假设）、3 项已确认无异常/已接受限制、9 组参数敏感性分析结果、5 项需要用户决定的业务口径（BD-1 至 BD-5）。 |
| `docs/current_task.md` | 顶部改为"模型假设诊断"范围，记录新基线（`50ce335`/`audit/model-assumptions`）；上一轮"实施修复方案"任务书整体移入历史背景 3。 |

### 验证证据

| 时间与环境 | 实际命令 | 结果 |
| --- | --- | --- |
| 2026-09-17（延续），项目 `.venv`（Python 3.11.5, pandas 3.0.3, numpy 2.4.6, pytest 9.1.1） | `git status --short`（分支创建前） | 空——工作区干净，与用户告知的基线一致。 |
| 同上 | `git checkout -b audit/model-assumptions` | 成功，无冲突。 |
| 同上 | `source .venv/bin/activate && python -m pytest -W error -ra` | **78 passed, 0 skipped**，本轮开始时重新实际运行确认，未直接采信历史记录。 |
| 同上 | 三个独立只读诊断过程：对 `data/processed/sku_month_demand.csv`、`outputs/sku_profile_classification.csv`、`outputs/sku_inventory_simulation.csv` 做 pandas 统计分析；对 `src/retail_analytics/simulation.py` 的 `economic_order_quantity`/`simulate` 等函数用真实 profile 数据在内存中重算（含移除 EOQ 封顶上限、逐项修改假设副本做敏感性分析） | 全部结果只写入 `/tmp`，未写入或覆盖仓库内任何文件。关键量化结果：`demand_cv` 与零售月份占比相关系数 0.84；180 天订货上限决定了当前 69.3%（699/1,008）的超储风险标记；封顶 SKU 未封顶前隐含覆盖天数中位数 450 天；9 组敏感性场景中，180 天上限和供应商交期是影响最大的两个参数。详见 `docs/model_assumptions_audit.md` 各条目。 |

- **关键数据与比较基线：** 全部诊断以当前 live 配置（`config/simulation_assumptions.json` 的 `methods` = `policy_band`/`service_level`/`eoq`/`max_stock`，与上一轮提交时一致，未变化）与真实的 `outputs/*.csv` 为基线；敏感性分析明确注明每个场景相对同一个 live 基线的变化，不是相对上一轮之前的任何历史基线。
- **未执行的验证及原因：**
  - 未重新执行完整流水线（`scripts/verify_pipeline.sh`）或任何 notebook——按用户要求"不为重复历史验收而重跑整个流水线"，且本轮不涉及任何业务代码改动，没有必要重新生成正式输出。
  - 敏感性分析脚本自算的基线数字与 `outputs/working_capital_summary.csv` 存在 £0.03–£0.06 的取整顺序差异（脚本先加总后取整，notebook 05 逐 SKU 先取整再加总）；已在 `docs/model_assumptions_audit.md` 第四节明确披露原因，未掩盖，也未重新调整脚本去凑正式数字（不影响任何结论的方向或量级）。
  - 未验证 MA-02/MA-03 提出的假设是否真实成立（例如短窗口高收入 SKU 未来是否真的会出现需求回落）——这需要更长时间的真实数据或业务判断，本轮已明确标注为"待验证假设"而非"已确认问题"。
- **已知问题与后续事项：** 全部记录在 `docs/model_assumptions_audit.md` 第五节"需要用户决定的业务口径"（BD-1 至 BD-5），核心是 `max_order_coverage_days`、`ordering_cost_gbp`、`supplier_lead_time_days`、`annual_holding_rate` 四个模拟参数均缺乏业务依据说明，且敏感性分析证实其中前两个（订货上限、供应商交期）对当前资金指标有实质性影响。
- **已停止修改，可以交给 Codex：** 是。本轮到此为止未再修改任何业务代码、notebook、正式配置或正式输出；本文件更新完成后不再变更。

### Codex 独立复核与方案（模型假设；2026-09-17）

**状态：已完成复核与方案，未实施修复，已停止修改。** 本节更新上方 Claude 本轮交接的“等待复核”状态；其原始诊断、交接及历史记录全部保留，不以本节文字覆盖。

#### 基线和改动边界

- 分支 `audit/model-assumptions`，HEAD `50ce335c2d5c8f20bbecc1e9eeae44745b076879`，与用户预期一致。
- 接手时 `docs/current_task.md`、本文件有 Claude 修改，`docs/model_assumptions_audit.md` 未跟踪；暂存区为空。已读仓库规范和任务文件，并检查实际 Git diff。
- 本轮只新增 `docs/model_assumptions_review.md`、`docs/model_assumptions_plan.md`，向本文件追加本节。Claude 的 current_task 和 audit 保持原样。本阶段以用户明确要求的“独立复核并制定方案”扩展诊断范围，不执行其后续修复。
- 实验只写 `/private/tmp/codex_model_assumptions_review/`。开始时记录 src/scripts/tests/config/notebooks/outputs/data/reports/docs 文件哈希；结束核对除本文件的追加与两份新文档外均不变。未改业务代码、正式配置、notebook、正式输出或测试，未暂存、commit、push。

#### 关键复核结论

| 事项 | 本轮结论 |
| --- | --- |
| MA-01 | 部分成立：Pearson r=0.840224，有效 3,789/3,790 SKU；零月占比和非零月波动共同进入 CV 的数学关系已验证。指标定义是补零月度销量相对波动，不能从相关性推出“主要衡量间歇性”或因果关系；不等同单笔订单量波动 |
| MA-02 | 部分成立：五个三月样本 short_history 都是 False，23392/23396 是 Regular；安全库存公式符合定义。短窗口有统计不确定性，但模拟 Normal 不能证明真实服务表现。D1 同时包含保留现有模拟规则，不能说额外保守化完全不涉及 D1 |
| MA-04 | 部分成立：A 固定库存时原 1,008 中 699 转 Normal，剩 309；B 完整重生成时原 1,008 全部保留、新增 35，总超储 1,043，缺货 565。B 的当前库存改变 2,171 个、Q/阈值改变 2,242 个；A/B 的 ROP、SS 均未改变。699 不是误报率，也不能代替 B 的结果 |
| MA-05 | 证据不足：实现隐含每 SKU 每次补货事件的固定成本 £25，无供应商合单分摊。封顶比例与覆盖天数复现，但单位成本低不能证明订货成本不合理或是唯一主因；实际参数待校准 |
| MA-03/06 | 部分成立：存在值得补的跨模块边界测试；但已有 3,000 SKU 合成 fixture，不仅单行样本。应补不变量与边界，不应将当前 capped≈59.16% 或相关系数0.84锁定为业务正确答案 |
| 敏感性 | 九场景可复现；高收入服务水平上调实际为0.98→0.995；交期实际为[10,21,32,45,68]。统一逐SKU舍入后基线资金指标与正式输出一致。结果限于选定范围一次一项试验，不能全局排名；订货成本减半/翻倍时缺货敞口−26.50%/+31.10%，即使缺货SKU数接近不变 |
| 额外文档问题 | runbook 的超储敞口定义仍只写180天需求；当前 max_stock 方法应使用 max(ROP+Q, d×180)。仅列入后续报告修正方案，本轮未改 runbook |

#### 实际验证与产物

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error /private/tmp/codex_model_assumptions_review/review_experiments.py`：成功。独立重建需求面板/profile、确认基线模拟、验证CV经验矩恒等式、核对具体SKU、执行A/B及九场景。所有临时配置为正式配置深拷贝，保留 SKU/seed/哈希抽样等控制条件。
- 隔离 `test_copy/` 中运行 demand/simulation 两个现有测试文件：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -W error -ra -p no:cacheprovider /private/tmp/codex_model_assumptions_review/test_copy/tests/test_demand.py /private/tmp/codex_model_assumptions_review/test_copy/tests/test_simulation.py` → **39 passed，0 skipped，1.43s**；另独立将真实 demand 输出经分类送入 simulate，衔接检查通过。没有在仓库新增或修改测试。
- 隔离证据：`results.log`、`correlations.csv`、`samples.csv`、`sample_months.csv`、`ma04_experiments.csv`、A/B 转移矩阵、`sensitivity.csv`、`rounding.csv`、九场景配置及基线副本、`pytest.log`、`before_hashes.json`。完整数值表、方法与单位已写进 review，临时文件无需加入提交。
- 资金差异来源独立验证：逐SKU舍入基线缺货/超储敞口 £84,414.16 / £53,315.26；先汇总后舍入为 £84,414.22 / £53,315.23。这里有直接算法证据，不归因于环境。
- `git diff --check` 及文档表格结构检查通过；Git staged diff 仍为空。

#### 方案与用户决定

方案按**报告解释 → 稳定测试/边界 → 可复现诊断工具 → 有依据的业务校准 → 经明确授权的短窗口策略研究**安排；当前无已确认业务代码缺陷，不更换任何参数。方案列出涉及内容、取舍及验收标准，不代表已经实施。

真正需要用户决定的是：是否从演示进入业务校准及相应数据负责人；进入校准时确认采购成本的真实事件/合单口径；若希望改变短窗口策略，是否明确重开 D1 的相关模拟规则。技术定义纠正不需业务投票，不要求用户凭空选新的 £25 替代值、持有率、覆盖上限或保守系数。

#### 未执行项与限制

- 未重跑全库78测试、清洗流水线或notebook：本轮无代码变更，选择了相关39测试及独立受控实验，避免把历史验收当作本轮证据；用户要求的六项复核均已完成。
- 未验证真实缺货/超储或真实最优订货参数：公开销售数据缺少实际库存、供应商到货与采购成本证据。未做全参数空间、需求扰动、多种子、交互分析，也不宣称现有九场景能替代这些分析。
- 不实施方案，不改既有D1。本节和两份新文档完成后停止修改，等待用户确定后续范围；未 commit、未 push。


## 历史交接：R1–R8 实施 + Codex 验收（已提交 `50ce335`）

### Claude 交接

### Git 状态

- 分支：`phase1-data-correctness`（未新建分支，遵守用户对业务口径 D2 的决定：接受现有工作区为整体验收基线，不拆分已有改动）。
- 起始提交：`1e73781429f09d310a4c75e5e94eb085aa3b0fb1`（本轮实施前后 HEAD 未变化，未 commit）。
- 是否有既有工作区修改：有，且全部保留。开始前的 `git status --short` 与本轮结束时的 `git status --short` 对比，除本轮新增/修改的文件外，其余条目完全一致（未 reset、未丢弃任何既有修改）。开始实施前已按用户要求确认另一并行会话已停止写入：`find . -newer tmp/audit_snapshot_manifest.txt` 在实施开始前只命中本会话自己此前写入的 `docs/issue_audit.md`、`docs/ai_workflow.md`、`docs/issue_review.md`、`docs/remediation_plan.md`、`docs/current_task.md`，没有第三方文件。
- 是否已 commit / push：否，均未执行。

### 完成内容

| 文件 | 修改内容与理由 |
| --- | --- |
| `src/retail_analytics/simulation.py` | **R1**：将 `oq = assumptions["order_quantity"]` 与 `annual_demand_units` 的计算移入 `methods.order_quantity == "eoq"` 分支内部（原来在分支判断之前无条件执行），`top_up` 分支下 `annual_demand_units` 显式设为 `NaN`。**R2**：`validate_assumptions` 新增 `methods.overstock == "max_stock"` 必须搭配 `methods.order_quantity == "eoq"` 的校验，否则 `raise ValueError`。两处改动均落实 D3：合法的精简 `top_up` 配置（不含 `order_quantity` 段）不再要求该段存在。 |
| `scripts/attribute_model_changes.py` | **R1**：`holding_rate = current["order_quantity"]["annual_holding_rate"]` 改为 `current.get("order_quantity", {}).get("annual_holding_rate")`，缺失时得到 `None`。`summarise()` 新增 `holding_rate is None` 分支，此时 `annual_holding_cost` 结果为 `None`（写入 CSV 后为空白），不再尝试用 `None` 乘法而崩溃，也不会被 pandas 默认求和逻辑悄悄变成 0。 |
| `notebooks/05_working_capital_impact.ipynb` | **R1 + D3**：`holding_cost_available = assumptions["methods"]["order_quantity"] == "eoq"` 门控 `annual_holding_cost` 的计算；不可用时该列整列为 `NaN`。两个 `groupby` 聚合表（按 SKU 分类、按仓库策略）在不可用时显式把汇总列强制设回 `NaN`，避免 pandas 对全 `NaN` 分组求和默认变成 `0.0` 而冒充真实数字。`working_capital_summary.csv` 的 `annual_holding_cost` 行、以及最终打印摘要，在不可用时输出 `"not_available (methods.order_quantity != eoq)"` 而不是数字。同时更新了相关 markdown 说明。 |
| `tests/test_simulation.py` | 新增 3 个测试：①`test_top_up_runs_without_an_order_quantity_section`（构造缺少 `order_quantity` 段的 `top_up` 配置，断言 `apply_replenishment_rules` 正常返回且相关字段为 `NaN`/`False`）；②`test_legacy_top_up_config_without_order_quantity_section_loads_and_simulates`（直接用仓库里现成的 `reports/baseline_end_phase3a/simulation_assumptions_phase3a.json` 通过 `load_assumptions`+`simulate` 端到端验证，文件不存在时自动跳过并在 pytest 输出中明确显示跳过原因）；③`test_max_stock_requires_eoq`（对应 R2 的校验）。 |
| `tests/test_attribute_model_changes.py`（新建） | 2 个测试，直接单测 `summarise()` 在 `holding_rate` 有值/为 `None` 两种情况下的行为，锁定"不可用时保留 `None`，不臆造 0"这条规则。 |
| `tests/test_cleaning_pipeline_regression.py`（新建） | **R7**：3 个测试，从真实的 `data/raw/Online Retail.xlsx` 出发，调用真实的 `scripts/standardize_raw_sales.standardize_sales` 与 `src/retail_analytics/cleaning.clean_transactions`，把中间标准化结果写入 `tmp_path`（pytest 临时目录，不写入 `data/interim/`），核对关键聚合值（519,627 行、£9,818,872.18、同价匹配 2,722、异价匹配 93、审核人工冲正 1）。第三个测试用一份**内存中的规则表副本**（`config/non_product_stock_codes.csv` 从未被写入或修改）删掉一条精确匹配规则，证明清洗结果确实会随规则变化，从而验证前两个断言不是摆设。原始数据缺失时（`data/raw/Online Retail.xlsx` 不存在）整个文件通过 `pytestmark = pytest.mark.skipif(...)` 跳过，并在跳过原因里写明具体缺失路径。 |
| `tests/test_demand.py` | **R8**：`test_classification_uses_absolute_cv_and_short_history` 增加第 6 行样本 `F`（高收入、`short_history=True`、`demand_cv=0.0`），断言其仍分类为 `High-Revenue Priority`，把 D1 决定保留的现有优先级行为用测试锁定，防止未来无意间改变。 |
| `README.md`、`docs/runbook.md`、`docs/management_summary.md` | **R3 + R4**：仓库分配策略表、库存风险计数、资金指标表全部替换为重新执行 notebook 04/05 后的真实当前数字；补充说明当前实际生效的模拟模型（`policy_band`/`service_level`/`eoq`/`max_stock`），保留旧模型（`fixed_range`/`volatility_factor`/`top_up`/`coverage_only`）仍受支持的事实；新增 `annual_holding_cost` 指标说明及其"不可用时留空、不冒充 0"的规则；补充 D1 决定保留的 short_history 分类局限说明。未在每份文档里机械塞入所有技术关键词——`docs/runbook.md` 承担最详细的方法说明，`README.md`/`docs/management_summary.md` 按各自原有详略程度更新。 |
| `docs/runbook.md`（对比脚本用法表） | 新增 `phase3b1` 前缀行（`baseline_end_phase3a` → `live`），并说明 `phase3a` 前缀继续对比到 `live` 而非冻结快照，提醒以后重跑会得到当时最新状态而非固定的 Phase 3A 结果。 |
| `CHANGELOG.md` | **R5 + R6**：新增两条 `Unreleased` 记录（置于文件最前）——一条补记 Phase 3B-1 模型本身此前从未被记录的变更（服务水平安全库存、EOQ、policy-band 库存、max-stock 超储，及数字前后对比），另一条记录本轮的修复/测试/文档工作，并给出当前真实测试数（67）。历史 "Phase 3A" 记录里的 "tests/test_simulation.py (7 tests)" **未改动**，按要求保留当时的真实记录。同时在补记的 Phase 3B-1 条目里加入了 R6 要求的归因表中间步骤说明（1,855 的中间峰值是隔离变量法的正常产物，不是回归）。 |
| `docs/current_task.md` | 顶部改为"实施修复方案"范围，记录 D1/D2/D3 三项用户决策原文，原"问题复核与方案设计"任务书整体移入历史背景 2。 |
| `notebooks/04_replenishment_warehouse_allocation.ipynb`、`notebooks/05_working_capital_impact.ipynb` | 用当前（合法、未改动的）`config/simulation_assumptions.json` 重新执行，验证 R1/R2 的代码改动在当前 live 配置下不改变业务结果（见"结果变化说明"）。 |

### 验证证据

| 时间与环境 | 实际命令 | 结果 |
| --- | --- | --- |
| 2026-09-17，项目 `.venv`（Python 3.11.5, pandas 3.0.3, numpy 2.4.6, pytest 9.1.1） | `source .venv/bin/activate && python -m pytest -W error -p no:cacheprovider -v` | **67 passed**（较本轮开始前的 59 个增加 8 个：`test_attribute_model_changes.py` 2 个、`test_cleaning_pipeline_regression.py` 3 个、`test_simulation.py` 新增 3 个；`test_demand.py` 保持 6 个但扩充了 1 条断言）。 |
| 同上 | `python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.kernel_name=ecommerce-venv notebooks/04_replenishment_warehouse_allocation.ipynb` 及同名命令对 notebook 05 | 均无错误执行完成（notebooks/01–03 本轮未修改代码，未重新执行）。 |
| 同上 | 执行前后对比 `outputs/working_capital_summary.csv`、`outputs/inventory_value_by_sku_class.csv`、`outputs/inventory_value_by_warehouse_strategy.csv`（`diff`） | **三个文件逐字节完全一致**——本轮代码修复对当前合法配置（`order_quantity=eoq`）的业务结果没有任何影响。 |
| 同上 | 对比 `outputs/sku_inventory_simulation.csv` 执行前后差异，并用 pandas 做容差比较 | 3,790 行中有 937 行存在纯浮点表示差异，**全部数值列的最大绝对差为 7.275957614183426e-12**（`annual_demand_units` 列），无任何分类/字符串列变化。已确认这是运行环境浮点噪声（数量级为 float64 精度极限），不是本轮代码逻辑的改动导致——本轮改动只搬动了代码位置，未改变任何算式；且该噪声同样出现在完全没有经过本轮改动代码路径的中间归因步骤里（见下一行）。 |
| 同上 | `python scripts/attribute_model_changes.py --output /tmp/phase3b1_attribution_recheck.csv` 后与已跟踪的 `reports/phase3b1_attribution.csv` 做 `diff`（输出到临时文件，未覆盖仓库内文件） | 第 0 行（Phase 3A 基准）与第 4 行（当前 live 配置）**逐字节一致**；中间第 1–3 行的 `stockout_revenue_exposure` 出现 `1296241.69` vs `1296241.7` 这类同一量级的浮点噪声（相对误差 ~7.7e-9），与上一行的噪声同源，同样不是本轮改动导致（这几个中间步骤走的是 `order_quantity=top_up`，根本不会执行本轮修改的 `eoq` 分支代码）。 |
| 同上 | 见下方"隔离验证"小节 | 用真实的 `reports/baseline_end_phase3a/simulation_assumptions_phase3a.json`（合法、缺少 `order_quantity` 段的精简配置）驱动 notebook 04/05 等价逻辑，输出只写入 `/tmp/legacy_config_check/`，未触碰正式 `config/` 或 `outputs/`：`load_assumptions`+`simulate` 正常完成、无 `KeyError`；`annual_holding_cost` 按预期整列为 `NaN`；`groupby` 汇总表也保持 `NaN`（不是被静默算成 `0.0`）。 |

- **关键数据与比较基线：** 本轮验证以复核阶段的快照（`tmp/audit_snapshot_manifest.txt`，`git status` 记录于 2026-09-16 15:31）以及当前 live `config/simulation_assumptions.json`（`methods` = `policy_band`/`service_level`/`eoq`/`max_stock`）为基线；清洗类基线数字（519,627 行、£9,818,872.18、2,722/93/1）另单独用真实原始数据重新验证，不依赖任何缓存 CSV。
- **未执行的验证及原因：**
  - 未通过 `jupyter nbconvert` 直接对 notebook 04/05 使用非官方配置文件重新执行——notebook 硬编码读取 `config/simulation_assumptions.json`，若临时替换该文件会违反"不修改正式配置"的要求，也有与另一并行会话产生冲突的风险（D2 强调单写者纪律）。改用等价的 Python 逻辑在隔离目录里验证（见上表最后一行），已覆盖 notebook 04（`load_assumptions`+`simulate`）和 notebook 05（`annual_holding_cost` 计算与分组聚合）的关键逻辑，但不是逐字节等价于真正跑一遍 notebook。
  - 未验证 `docs/remediation_plan.md` 中 ISSUE-09/D3 附带提到的"是否所有历史组合都有对称校验"这类超出 R1/R2 范围的问题（如 `overstock=max_stock` 以外的其它未校验组合），按范围要求列为后续事项。
  - 未重新执行 notebooks/01–03（本轮未修改其依赖的代码），其产出文件保持复核阶段的状态。
- **已知问题与后续事项：**
  - `outputs/sku_inventory_simulation.csv` 中约 937 行存在 <=7.3e-12 量级的浮点表示噪声，来源是运行环境本身（怀疑与 numpy/pandas 版本在不同时间点被更新有关），已确认不影响任何已发布的汇总指标；如需要完全消除，需要固定/复核 `.venv` 里 numpy/pandas 的具体版本号是否与历史生成这些文件时一致，这超出本轮范围。
  - `docs/remediation_plan.md` 中未实施的条目：D1/D2/D3 均已由用户决策并落实；R6 未新建独立报告文件，而是把归因表说明并入了 `docs/management_summary.md` 和 `CHANGELOG.md`，符合"避免重复创建报告"的要求。
  - 分支治理（D2）：用户已明确决定接受现状、不拆分支，此事项按此结论关闭，仅记录在案。
- **已停止修改，可以交给 Codex：** 是。本轮到此为止未再修改任何业务代码、notebook 或文档；`docs/handoff.md` 更新完成后不再变更。

### Codex 最终审查与验收（属于历史交接）

#### 结论与基线

- 2026-09-17 独立验收完成，可以进入用户审阅与提交准备阶段；未 commit、未 push、未合并。
- `pwd`：`/Users/yeternalh/ecommerce-inventory-warehouse-allocation`。分支仍为 `phase1-data-correctness`，HEAD 仍为 `1e73781429f09d310a4c75e5e94eb085aa3b0fb1`。
- 已阅读仓库工作流规范、current_task、issue_review、remediation_plan 和 Claude 交接；检查暂存/未暂存 diff、未跟踪 src/tests/config/scripts/reports/docs、notebook 源代码差异及生成数据。10 份 archive notebook 均与 HEAD 中对应原文件逐字节一致。`clean_sales.csv` 本地仍存在（约 67 MB），Git 索引已不再跟踪。
- 接受用户 D2 决策，保留原分支与全部已有工作。原 Claude 记录保留在上方；其中“环境导致浮点差异”“等价逻辑已覆盖 notebook”不作为本轮验收依据。

#### 独立发现及修复

1. **R1 第三处仍有端到端缺口。** `attribute_model_changes.py` 虽使用 `.get()` 读取持有率，后续仍固定进入 EOQ 步骤，精简历史配置会在该步骤失败。改为仅启用目标配置指定的方法；历史配置只输出 Phase 3A 行，不虚构 EOQ 参数。增加真实 CLI 路径测试，核对缺失年度持有成本导出为空。
2. **真实数据收入断言容差过宽。** `pytest.approx(..., abs=0.01)` 仍带默认相对容差，对 £9.82M 实际可容忍约 £9.82。改为 `rel=0, abs=0.01`，保留一便士绝对容差。
3. **验证脚本可能假成功。** 加入 `pipefail`、以累计 `status` 退出、收入检查失败计入状态；不再过滤 notebook WARNING。首次被沙箱阻止内核启动时，脚本确实退出 1；授权重跑后退出 0。
4. **补齐 R2 正向覆盖。** 参数化测试覆盖全部 10 个合法方法组合（top_up 两个组合均删除 order_quantity 配置段后运行），与已有 max_stock + top_up 拒绝测试共同验证。
5. **文档与实跑不一致。** README/runbook 的 Phase 3A 命令改为两个冻结快照对比，与验证脚本一致；修正把 top_up 写成 fixed-quantity 的描述。CHANGELOG 区分 notebook 的方法门控与归因表使用同一持有率比较各步的口径，更新当前测试数为 78，撤回未经证明的环境/版本归因；Phase 3A/Phase 1 历史记录（包括当时 7 tests）未改。
6. **归因报告的便士差异。** 当前脚本重跑第 1–3 步的 stockout_revenue_exposure 都为 £1,296,241.69，旧报告为 £1,296,241.70。仅刷新 `reports/phase3b1_attribution.csv` 这三个值；没有以相对误差小为由忽略一便士的已舍入金额变化。历史生成原因没有足够证据，仍明确未确认。

#### 实际执行与证据

环境：项目 `.venv`，Python 3.11.5、pandas 3.0.3、NumPy 2.4.6、pytest 9.1.1。隔离副本根目录为 `/private/tmp/codex_inventory_acceptance`（以下称 `$CHECK`）。该副本复制实际工作区，包括未跟踪的新模块和原始 Excel，不是 git HEAD 导出。

| 验证 | 实际命令／执行方式 | 结果 |
| --- | --- | --- |
| 严格测试，开始时 | `.venv/bin/python -m pytest -W error -ra` | 67 passed，0 skipped，47.61s |
| 严格测试，修复后 | `.venv/bin/python -m pytest -W error -ra` | **78 passed，0 skipped，49.09s**；日志 `$CHECK/final_pytest.log`。新增 1 个归因 CLI 测试 + 10 个合法组合参数用例 |
| 完整流水线 | 在 `$CHECK` 执行 `VENV=/Users/yeternalh/ecommerce-inventory-warehouse-allocation/.venv IPYTHONDIR=/private/tmp/codex_inventory_acceptance/ipython bash scripts/verify_pipeline.sh` | **退出 0**。validate、standardize、01–05 全部实际执行。日志 `$CHECK/pipeline_authorized.log`；隔离副本创建时的 67 tests 也全部通过，无跳过；最终仓库 78 tests 的结果见上一行 |
| 实际 notebook 执行证据 | 同一脚本逐个调用 `python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.kernel_name=ecommerce-venv --ExecutePreprocessor.timeout=600 notebooks/0N_*.ipynb` | 01/02/03/04/05 分别有 11/8/8/9/9 个已执行代码单元，所有代码单元 execution_count 非空，无 error 输出 |
| 相关比较 | 脚本实际执行 compare_to_baseline：before_phase1 → end_phase1，end_phase1 → end_phase3a，end_phase3a → live；另执行 attribute_model_changes 和 check_simulation_stability | 均成功。哈希模拟的删首 SKU、删中间 SKU、重排行顺序三场景，Phase 3A 与当前模型的字段和风险变化比例均为 0 |
| 精简历史配置的真实 04、05 | `.venv/bin/python /private/tmp/codex_inventory_acceptance/legacy_check.py`，内部逐个使用 nbconvert 执行 `$CHECK/legacy/notebooks/04_*.ipynb`、`05_*.ipynb` | **均成功**。只替换隔离副本 config 为原样复制的历史 JSON；原 notebook 所有单元均执行，05 末尾额外附加断言单元，没有用复制逻辑替代 notebook。随后实际运行归因 CLI 成功 |
| 缺失成本各层检查 | 上述 05 的追加单元检查明细、两类分组、总计、两个分组 CSV、总计 CSV；另把内核内真实明细导出 acceptance_detail.csv 后重读 | 明细与分组全 NaN；总计为 not_available；所有导出一致，没有变成 0。日志 `$CHECK/legacy_authorized.log` 和执行后 05 的末尾输出含 `LEGACY_DETAIL_GROUP_TOTAL_EXPORT_ASSERTIONS_PASSED` |
| 正常 EOQ 成本 | 按完整流水线实际模拟明细逐行重算 `round(round(inventory × unit_cost, 2) × 0.25, 2)`，核对两个分组及总计 | 两个分组精确相等，总计 **£451,397.56**；既有 EOQ 手算、上限和补货规则测试通过 |
| 真实规则变异 | `$CHECK/mutation` 单独复制当前清洗代码、测试、原始 Excel、配置，删除副本规则 POST；运行 `python -m pytest -W error -ra .../mutation/tests/test_cleaning_pipeline_regression.py -k final_row` | **预期失败，退出 1**：520,730 != 519,627。证明原汇总断言会捕获真实规则变化；日志 `$CHECK/mutation.log`。未改正式规则、原始数据或生成数据 |
| 数据保护 | 对验收前记录的 data/config/outputs/notebooks/reports 文件 SHA-256 进行核对 | 所有正式 data/config/outputs/notebooks 均保持原样；reports 只主动更新上述归因报告三个便士值。正式数据未被测试或隔离流水线写入 |
| 差异完整性 | `git diff --check`；archive 对比 HEAD；检查 staged clean_sales 删除与本地文件 | 通过 |

首次沙箱内运行 Jupyter 时得到 `PermissionError: Operation not permitted`，未把那次生成目录里保留的 CSV 算作重跑结果；经工具权限审批后重新实际执行成功。首次 IPython home 不可写提示通过为后续运行指定隔离的 IPYTHONDIR 解决，未隐藏警告。

#### 数字、浮点、分类、排序与汇总

- 真正重跑后比较 30 个 `data/processed`、`outputs` CSV；行数、列、非数值列、NaN 位置、原有行顺序均核对。逐列数值采用 `rtol=1e-12, atol=1e-9`：为 CSV/float64 表示误差留余量，远小于便士和库存整数阈值；分类、风险、布尔标记和 stock_code 顺序要求精确一致。另对资金总计及两张资金分组表做精确比较，均通过。脚本及结果在 `$CHECK/compare_outputs.py`、`comparison.json.log`。
- 26 个 CSV 逐字节一致；其余为 sku_month_demand、sku_profile_classification、sku_inventory_simulation 的极小数值差异，以及 warehouse_allocation_summary 的文本表示差异（解析后数值完全相等）。本轮最大解析后绝对差为 **9.094947017729282e-13**。没有分类、风险、补货决策、榜单/推荐排序变化，当前资金汇总逐字节相同。这里描述实测差异，不推断历史环境来源。
- 对比报告中 phase1_top20_revenue_rank_changes 的最大解析后差为 7.275957614183426e-12，排名、SKU 顺序不变；Phase 3B-1 归因中间金额差一便士单独处理如上，不套用宽泛金额相对容差。当前输入同时用默认/round_trip CSV 解析及当前内存重建均得到 .69，不能据此声称已找到旧 .70 的历史原因。
- 清洗：519,627 行，收入 **£9,818,872.18**；取消匹配同价 2,722、异价 93，审核人工冲正 1。真实 Excel 回归测试未跳过。
- 当前模拟：3,790 SKU；Normal 2,246、Stockout 536、Overstock 1,008；库存价值 £1,805,589.48、年度持有成本 £451,397.56、缺货收入敞口 £84,414.16、超储资金敞口 £53,315.26、EOQ capped 2,242。
- 仓库策略实测分布：Standard 1,164；Overstock Review 1,008；Local Priority 748；External/Limited 626；Stable Local 171；Small-Batch 73。README、runbook、管理层摘要当前数字与输出相符。
- short_history 测试锁定“高收入 + 短历史 + CV=0 仍为 High-Revenue Priority”，并锁定短历史高周转不能分类为 Stable；不改变 D1。实测高收入短历史 27 个，其中 1 个安全库存为零；README、runbook、管理层摘要明确说明统计不可靠，未新增库存下限。

#### 未完成项与限制

- **用户指定的验收步骤没有未完成项。** R1 三处、R2 正反路径、缺失年度成本全链路、真实数据规则变异、short_history、文档数字及历史记录均已验收。
- 旧归因报告中间步骤 .70 的历史生成原因仍不能确认；本轮使用实际重跑 .69 更新当前报告，保留上方 Claude 原始说法供追溯，但不采信其环境归因。没有旧中间步骤逐 SKU 快照，不能声称验证了该历史中间态逐 SKU 排序；当前完整模型及当前输出排序已核对不变。
- 原始 Excel 或冻结快照缺失的其他环境仍可能触发现有显式 skip；本次环境全部存在，跳过数为 0。库存仍是模拟数据，短历史统计局限按用户 D1 保留。
- 临时日志、执行 notebook 与对照脚本位于 `/private/tmp/codex_inventory_acceptance`，不加入提交。准备提交时应人工审阅整个已接受工作区，继续保持单写者；本轮没有执行任何提交或推送。

## Codex 最终验收（本轮修正后）

本节是对上方 Claude 原始交接的独立补充；原始记录保留，不以其中较早的测试数量替代本节结果。分支仍为 `audit/model-assumptions`，HEAD 仍为 `50ce335c2d5c8f20bbecc1e9eeae44745b076879`，未 commit、未 push。

### 本轮修正

- 补强 R1 入口：README、管理层摘要和历史审计报告的 MA-04 原文旁均明确链接复核结论；保留历史数字，但说明 69.3% 只回答固定库存实验 A 的分类敏感性，不是误报比例。同步说明 CV 的定义、3 个月边界、短历史局限、£25 的单位和九场景资金敞口。
- T1/T2 修正了原本不触发上限的边界样例，并增加独立手算的需求统计→安全库存→再订货点断言、覆盖阈值严格边界和非整数 EOQ 上限边界。
- E1 诊断工具拒绝未知/重复场景和非兼容配置，拒绝已存在目录及其符号链接别名，采用临时目录原子发布并检查输入是否在运行中改变；元数据现在包含暂存 diff、未跟踪文件内容、源文件哈希、实际配置和比较容差。补充了保护、失败路径、确定性和种子覆盖测试。

### 实际验证

| 验证 | 结果 |
| --- | --- |
| `.venv/bin/python -m pytest -W error -ra` | **127 passed, 0 skipped**。 |
| E1 真实 CLI 两次运行，真实 `outputs/sku_inventory_simulation.csv` 与 live config，A/B + 1a–5 全部场景 | 两次 `scenario_summary.csv`、`field_change_counts.csv` 和风险转移结果逐字节一致；A 的库存变化为 0，B 的库存变化为 2,171。 |
| 独立结果对比 | 基线、A/B 和九场景的数量、金额、推荐量、封顶数及风险转移与独立复核 CSV 全部一致；按每 SKU 先取到便士再汇总，浮点中间值使用 `rtol=1e-12, atol=1e-9`。 |
| 变异验证（隔离副本） | 首销过滤、截断月过滤、样本标准差填充、`short_history` 边界、超储严格比较、EOQ 封顶六种变异均使对应测试失败；未写回正式代码。 |
| 正式文件保护 | `config/`、`data/`、`outputs/`、`notebooks/` 及相关正式文件 138 个哈希保持不变；`git diff --check` 通过。 |

### 未完成项

没有发现需要改变既定业务公式或参数的问题。未实施业务参数校准，也未改变 live 配置、notebook 或正式输出；£25、服务水平、覆盖天数和交期仍是待业务数据校准的演示参数。未 commit、未 push，可进入提交准备。

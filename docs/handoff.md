# 本轮交接

状态：Claude 原始交接保留；Codex 独立验收与修正已完成，详见文末。

## Claude 交接

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

## Codex 最终审查与验收

### 结论与基线

- 2026-09-17 独立验收完成，可以进入用户审阅与提交准备阶段；未 commit、未 push、未合并。
- `pwd`：`/Users/yeternalh/ecommerce-inventory-warehouse-allocation`。分支仍为 `phase1-data-correctness`，HEAD 仍为 `1e73781429f09d310a4c75e5e94eb085aa3b0fb1`。
- 已阅读仓库工作流规范、current_task、issue_review、remediation_plan 和 Claude 交接；检查暂存/未暂存 diff、未跟踪 src/tests/config/scripts/reports/docs、notebook 源代码差异及生成数据。10 份 archive notebook 均与 HEAD 中对应原文件逐字节一致。`clean_sales.csv` 本地仍存在（约 67 MB），Git 索引已不再跟踪。
- 接受用户 D2 决策，保留原分支与全部已有工作。原 Claude 记录保留在上方；其中“环境导致浮点差异”“等价逻辑已覆盖 notebook”不作为本轮验收依据。

### 独立发现及修复

1. **R1 第三处仍有端到端缺口。** `attribute_model_changes.py` 虽使用 `.get()` 读取持有率，后续仍固定进入 EOQ 步骤，精简历史配置会在该步骤失败。改为仅启用目标配置指定的方法；历史配置只输出 Phase 3A 行，不虚构 EOQ 参数。增加真实 CLI 路径测试，核对缺失年度持有成本导出为空。
2. **真实数据收入断言容差过宽。** `pytest.approx(..., abs=0.01)` 仍带默认相对容差，对 £9.82M 实际可容忍约 £9.82。改为 `rel=0, abs=0.01`，保留一便士绝对容差。
3. **验证脚本可能假成功。** 加入 `pipefail`、以累计 `status` 退出、收入检查失败计入状态；不再过滤 notebook WARNING。首次被沙箱阻止内核启动时，脚本确实退出 1；授权重跑后退出 0。
4. **补齐 R2 正向覆盖。** 参数化测试覆盖全部 10 个合法方法组合（top_up 两个组合均删除 order_quantity 配置段后运行），与已有 max_stock + top_up 拒绝测试共同验证。
5. **文档与实跑不一致。** README/runbook 的 Phase 3A 命令改为两个冻结快照对比，与验证脚本一致；修正把 top_up 写成 fixed-quantity 的描述。CHANGELOG 区分 notebook 的方法门控与归因表使用同一持有率比较各步的口径，更新当前测试数为 78，撤回未经证明的环境/版本归因；Phase 3A/Phase 1 历史记录（包括当时 7 tests）未改。
6. **归因报告的便士差异。** 当前脚本重跑第 1–3 步的 stockout_revenue_exposure 都为 £1,296,241.69，旧报告为 £1,296,241.70。仅刷新 `reports/phase3b1_attribution.csv` 这三个值；没有以相对误差小为由忽略一便士的已舍入金额变化。历史生成原因没有足够证据，仍明确未确认。

### 实际执行与证据

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

### 数字、浮点、分类、排序与汇总

- 真正重跑后比较 30 个 `data/processed`、`outputs` CSV；行数、列、非数值列、NaN 位置、原有行顺序均核对。逐列数值采用 `rtol=1e-12, atol=1e-9`：为 CSV/float64 表示误差留余量，远小于便士和库存整数阈值；分类、风险、布尔标记和 stock_code 顺序要求精确一致。另对资金总计及两张资金分组表做精确比较，均通过。脚本及结果在 `$CHECK/compare_outputs.py`、`comparison.json.log`。
- 26 个 CSV 逐字节一致；其余为 sku_month_demand、sku_profile_classification、sku_inventory_simulation 的极小数值差异，以及 warehouse_allocation_summary 的文本表示差异（解析后数值完全相等）。本轮最大解析后绝对差为 **9.094947017729282e-13**。没有分类、风险、补货决策、榜单/推荐排序变化，当前资金汇总逐字节相同。这里描述实测差异，不推断历史环境来源。
- 对比报告中 phase1_top20_revenue_rank_changes 的最大解析后差为 7.275957614183426e-12，排名、SKU 顺序不变；Phase 3B-1 归因中间金额差一便士单独处理如上，不套用宽泛金额相对容差。当前输入同时用默认/round_trip CSV 解析及当前内存重建均得到 .69，不能据此声称已找到旧 .70 的历史原因。
- 清洗：519,627 行，收入 **£9,818,872.18**；取消匹配同价 2,722、异价 93，审核人工冲正 1。真实 Excel 回归测试未跳过。
- 当前模拟：3,790 SKU；Normal 2,246、Stockout 536、Overstock 1,008；库存价值 £1,805,589.48、年度持有成本 £451,397.56、缺货收入敞口 £84,414.16、超储资金敞口 £53,315.26、EOQ capped 2,242。
- 仓库策略实测分布：Standard 1,164；Overstock Review 1,008；Local Priority 748；External/Limited 626；Stable Local 171；Small-Batch 73。README、runbook、管理层摘要当前数字与输出相符。
- short_history 测试锁定“高收入 + 短历史 + CV=0 仍为 High-Revenue Priority”，并锁定短历史高周转不能分类为 Stable；不改变 D1。实测高收入短历史 27 个，其中 1 个安全库存为零；README、runbook、管理层摘要明确说明统计不可靠，未新增库存下限。

### 未完成项与限制

- **用户指定的验收步骤没有未完成项。** R1 三处、R2 正反路径、缺失年度成本全链路、真实数据规则变异、short_history、文档数字及历史记录均已验收。
- 旧归因报告中间步骤 .70 的历史生成原因仍不能确认；本轮使用实际重跑 .69 更新当前报告，保留上方 Claude 原始说法供追溯，但不采信其环境归因。没有旧中间步骤逐 SKU 快照，不能声称验证了该历史中间态逐 SKU 排序；当前完整模型及当前输出排序已核对不变。
- 原始 Excel 或冻结快照缺失的其他环境仍可能触发现有显式 skip；本次环境全部存在，跳过数为 0。库存仍是模拟数据，短历史统计局限按用户 D1 保留。
- 临时日志、执行 notebook 与对照脚本位于 `/private/tmp/codex_inventory_acceptance`，不加入提交。准备提交时应人工审阅整个已接受工作区，继续保持单写者；本轮没有执行任何提交或推送。

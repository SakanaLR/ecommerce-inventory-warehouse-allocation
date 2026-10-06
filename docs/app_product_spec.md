# 商户库存分析 App：产品规格（信息架构 + 只读 MVP）

> 分支 `feature/merchant-analytics-mvp`，从 `audit/model-assumptions` 的 `9cb8932` 切出。本规格先于实现编写，实现应以本文件为准；如实现中发现需要偏离本规格，应先更新本文件再改代码，不允许代码和规格长期不一致。

## 一、目标用户与经营问题

**目标用户：** 非技术背景的商户/运营人员——不写 SQL、不看 Jupyter notebook、不熟悉"服务水平""EOQ"这类术语，但需要每天/每周快速判断"哪些商品需要我关注"。不是数据分析师或工程师（他们已经有 notebook 和 CSV 可以用）。

**要回答的经营问题**（对齐 `README.md`"Business Questions"，但用商户能听懂的语言重新表述）：

1. 我的生意整体表现如何？清洗后的真实收入、SKU 数量、SKU 组合是什么样的？
2. 有哪些 SKU 现在（在模拟库存下）看起来会缺货，需要马上补货？
3. 有哪些 SKU 看起来库存压得太多，占用了不该占用的资金？
4. 具体到某一个 SKU，它的历史销售是什么样的？模拟出来的库存/安全库存/建议补货量是多少？这些数字有多可信？
5. 这些"风险""建议"背后用的是什么规则？哪些是真实历史数据，哪些是模拟出来的、还没有真实业务参数校准的假设？

**不回答的问题**（明确排除，见"本轮非目标"）：参数如果调整会怎样、要不要登录、要不要接入商户自己的系统、要不要部署到公网。

## 二、页面与交互

Streamlit 多页应用，三个页面，左侧导航栏切换，无登录、无个性化设置：

### 页面 1：经营总览（`app/streamlit_app.py`，默认首页）

- 顶部：**历史 vs. 模拟**的醒目分区标签（见第四节），所有下方指标按这两类分区展示，不混排。
- 历史区：清洗后总收入（GBP）、有效 SKU 数、SKU 分类分布（表格 + 条形图）。
- 模拟区：库存风险三态计数（Normal / Stockout Risk / Overstock Risk）、模拟库存总价值、缺货收入敞口、超储资金敞口、仓库策略分布（表格 + 条形图）。
- 交互：无筛选（总览页是全局快照）；每个模拟指标旁有一个 `ℹ️` 提示（Streamlit `help=` 参数或 `st.caption`），点开/悬停显示"这是模拟数据，见模型与数据说明页"。

### 页面 2：SKU 分析器（`app/pages/1_SKU_Analyzer.py`）

- 筛选栏（侧边栏或页面顶部）：`stock_code`/描述关键字搜索框、SKU 分类多选、库存风险多选、仓库策略多选。筛选之间是"与"（AND）关系。
- 命中列表：表格展示筛选后的 SKU，列包括 `stock_code`、描述、SKU 分类、收入、销量、有效月份数（`months_in_window`）、`short_history` 标记、`demand_cv`、风险状态、仓库策略。
- 选中单个 SKU 后展开详情：
  - 月度销量趋势折线图（历史，来自 `sku_month_demand.csv`，含零填充月份，标明哪些是零填充）。
  - 模拟区块：当前模拟库存、安全库存、再订货点、EOQ（`economic_order_qty`）、建议补货量、库存覆盖天数。
  - 若该 SKU `short_history=True`：显式提示"历史不足 3 个月，以下统计量（尤其 `demand_cv`）可信度低，不代表已验证的稳定需求"。
  - 若该 SKU `inventory_risk="Normal"`：显式提示"该状态是模拟策略在当前假设下的判定结果，不代表已验证的真实经营表现良好"（对齐 `docs/model_assumptions_review.md` 的措辞纪律，不做过度解读）。
- 空筛选结果：显示"没有匹配的 SKU"提示 + 当前筛选条件回显，不报错、不显示空表格的裸 traceback。

### 页面 3：模型与数据说明（`app/pages/2_Model_and_Data_Notes.py`）

- 数据截止日期与截断月份：从 `data/processed/month_coverage.csv` 读取，明确标出哪个月是截断月（当前是 2011-12，只到 9 号）。
- 清洗规则摘要：对齐 `docs/runbook.md`"Cleaning Rules"一节，用一段通俗语言概括（去重、剔除非商品行、取消订单匹配、人工冲正），并链接到 `docs/runbook.md` 完整版。
- 模型通俗解释：服务水平安全库存、EOQ、`max_stock` 超储阈值，各配一句"大白话"解释 + 精确公式（对齐 `docs/runbook.md`"Simulated Inventory Layer"表格），避免只讲人话导致误解、也避免只贴公式让人看不懂。
- 演示参数与待校准状态：直接复用 `docs/runbook.md`"Parameter calibration status"段落的内容（订货成本、持有率、订货上限、超储覆盖天数、交期分布、服务水平表——责任人和校准日期均为"未定"）。
- 数据隐私说明：见第五节，列出 App 绝不展示什么。
- 模型限制：链接/摘录 `README.md`"Assumptions and Limitations"和 `docs/model_assumptions_review.md`的关键结论（699/1,008 只在固定库存实验下成立、demand_cv 的真实含义、九场景敏感性的适用范围）。
- 入口链接：`docs/runbook.md`、`docs/management_summary.md`、`docs/model_assumptions_review.md`（用 `st.markdown` 展示相对路径提示，因为 Streamlit 本身不能直接渲染仓库内任意文件为可点击链接跳转到另一个进程，这里做法是展示文件路径 + 内容摘要，不是可点击的本地文件超链接）。

## 三、指标定义、单位与数据来源

所有金额单位 GBP，所有数据来源均为**只读**、已经过清洗/模拟流水线生成的 CSV，App 不重新计算业务规则，只做展示层的聚合（求和、计数、分组），不重新实现 `src/retail_analytics/` 里的任何公式。

| 指标 | 定义 | 数据来源 | 类别 |
| --- | --- | --- | --- |
| 清洗后总收入 | `sku_inventory_simulation.csv` 的 `total_revenue` 求和 | `outputs/sku_inventory_simulation.csv` | 历史 |
| 有效 SKU 数 | 行数 | 同上 | 历史 |
| SKU 分类分布 | 按 `sku_class` 分组计数/求和 | 同上 | 历史 |
| 月度销量趋势 | 单个 SKU 的 `monthly_units`/`monthly_revenue` 按月 | `data/processed/sku_month_demand.csv` | 历史（含零填充标记） |
| Stockout/Overstock/Normal 计数 | 按 `inventory_risk` 分组计数 | `outputs/sku_inventory_simulation.csv` | 模拟 |
| 模拟库存总价值 | `outputs/working_capital_summary.csv` 的 `total_estimated_inventory_value` | 同上 | 模拟 |
| 缺货收入敞口 / 超储资金敞口 | 同上文件的 `stockout_revenue_exposure` / `overstock_capital_exposure` | 同上 | 模拟 |
| 仓库策略分布 | 按 `warehouse_strategy` 分组计数 | `outputs/sku_inventory_simulation.csv` | 模拟 |
| 安全库存 / 再订货点 / EOQ / 建议补货量 | `safety_stock` / `reorder_point` / `economic_order_qty` / `recommended_replenishment_qty` 列 | 同上 | 模拟 |
| `demand_cv` / `short_history` / `months_in_window` | 直接读取列 | 同上 | 历史统计量（但解释见下方"区别"一节，不是模拟） |

App 不重新计算任何风险判定、分类阈值或补货公式——这些字段全部直接来自已生成的 CSV，只做筛选、分组、格式化和图表渲染。

## 四、历史事实与模拟指标的区别

这是 P0 优先级要求，贯穿所有三个页面：

- **历史事实**：直接来自清洗后的真实交易（`total_revenue`、`total_units`、月度销量、`sku_class` 的收入/销量输入、`demand_cv` 等需求统计量本身）。这些是真实发生过的销售的聚合结果。
- **模拟指标**：`current_inventory`、`safety_stock`、`reorder_point`、`economic_order_qty`、`inventory_risk`、`warehouse_strategy`、库存价值/资金敞口——这些全部来自 `src/retail_analytics/simulation.py` 用假设参数（交期分布、订货成本、持有率、服务水平）生成的模拟层，不是真实库存记录。数据集本身没有真实库存/成本/交期数据。
- **展示规则**：
  1. 每个页面用视觉分区（不同背景色块或明确的小节标题"历史数据" vs "模拟数据"）区分两类指标，不在同一个数字旁边混用。
  2. 模拟数值旁一律有简短说明或 `help=` 提示，指向"演示假设，未经业务校准"。
  3. 不使用"库存""缺货"这类词汇时不加"模拟"前缀——所有模拟相关的标签统一带"模拟"二字或等价说明（如"Simulated"）。
  4. `inventory_risk="Normal"` 不得被解释为"经营良好"；`short_history` SKU 的统计量旁必须有不确定性提示。这两条直接对齐 `docs/model_assumptions_review.md` 的复核纪律，不允许 App 的文案比源文档更激进。

## 五、隐私边界

- **绝不呈现原始明细**：页面绝不接收或展示 `customer_id`、`invoice_no`、`invoice_date`、原始逐行交易明细或原始 Excel 文件。已核实 App 计划读取的所有数据源（`outputs/sku_inventory_simulation.csv`、`outputs/sku_profile_classification.csv`、`data/processed/sku_month_demand.csv`、`data/processed/month_coverage.csv`、`data/processed/data_quality_summary.csv`、`outputs/management_kpi_summary.csv`、`outputs/working_capital_summary.csv`、`outputs/warehouse_allocation_summary.csv`）逐一检查过表头，均为 SKU 级或更粗粒度的聚合数据，本身不包含这些字段。
- **纵深防御和 allowlist**：数据适配层会先读取原始 CSV 表头并检查"禁止列"（`customer_id`、`invoice_no`、`invoice_date`、逐行订单号等）；命中即直接报错。只有通过检查后，才复制各加载器所列的必需聚合列到返回 DataFrame。这样新增的未知列也不会因未来页面渲染改动而到达页面。
- **不提供下载原始数据**：App 不提供任何"下载 Excel"或"导出原始明细"按钮；如果未来要加导出，只能导出当前页面已经聚合、已经过隐私检查的表格。
- **不连接外部服务**：App 不发起任何出站网络请求（不接第三方分析、不调用外部 API），纯本地读文件、本地渲染；`.streamlit/config.toml` 将 `browser.gatherUsageStats` 设为 `false`，关闭 Streamlit 使用统计。
- **面向未来商户本地聚合文件的数据契约**：`dashboard_data.py` 里定义的 `REQUIRED_SKU_PROFILE_COLUMNS` 等 schema 常量，就是这份契约——未来如果商户自己生成一份符合同样列名/类型的聚合 CSV（同样只到 SKU 级别，不含客户/订单明细），可以直接替换数据源路径使用，不需要改 App 逻辑。这份契约本身也是隐私边界的一部分：它只列出聚合字段，不包含也不允许包含任何逐行/逐客户字段。

## 六、空数据、缺列和输出过期时的行为

- **文件不存在**（例如还没跑过 notebook 04/05）：加载函数抛出一个带清晰指引的错误（"未找到 X，请先运行 notebooks/0N...ipynb 或 scripts/verify_pipeline.sh"），页面捕获后用 `st.error` 展示这条消息和缺失的文件路径，不展示 Python traceback，不让整个 App 崩溃到白屏。
- **文件存在但缺少必需列**：加载函数做 schema 校验，列出缺失的具体列名，同样通过 `st.error` 展示，不静默用 `NaN`/0 填充继续渲染。
- **文件存在但是空表**（0 行）：页面正常渲染，指标显示为"暂无数据"或 0，不报错；SKU 分析器的筛选结果为空时提示"没有匹配的 SKU"（见页面 2 交互）。
- **输出过期**（`outputs/` 里的文件时间戳早于 `data/processed/`，或几份文件之间总数对不上，例如 `sku_inventory_simulation.csv` 的行数与 `sku_profile_classification.csv` 不一致）：模型与数据说明页展示一个"数据生成时间"信息条（基于文件的最后修改时间），如果检测到明显的行数不一致，显示一条警告，但不阻止其它页面使用——这是提示性的，不是阻断性的验证（阻断性验证已经在 pytest 的回归测试里做了，App 层只做轻量提示）。

## 七、本轮非目标（明确不做）

- 不做参数场景比较（不集成 `scripts/model_assumptions_diagnostics.py` 的 A/B/九场景到 App 里）。
- 不做登录、鉴权、多商户隔离。
- 不做云部署、容器化、CI 里的 App 部署流水线。
- 不做小程序/移动端适配。
- 不提供任何写入/编辑功能——纯只读。
- 不重新执行清洗/模拟流水线（notebook 01–05）——App 只读已经生成的 CSV。
- 不修改 `src/retail_analytics/{cleaning,demand,simulation}.py`、`config/`、`data/`、`outputs/`、notebook 或历史基线报告。
- 不做除"提示性时间戳/行数校验"之外的自动化数据新鲜度监控或告警通道。

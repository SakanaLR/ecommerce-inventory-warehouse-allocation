# 商户库存分析 Dashboard 交付与展示优化：方案（经 Codex 复核）

> 对应 `docs/dashboard_delivery_audit.md` 的复核结果。本文件只提出方案，不代表已实施；本轮不修改 `app/`、`src/`、`tests/`、`.github/`、依赖文件、`.streamlit/`、`config/`、`data/`、`outputs/`、`notebooks/`、`reports/`。实施继续保持"Claude 实施、Codex 独立验收"的流程。

## 一、修复方案（按优先级排序）

### P0 — 低风险、高价值，建议下一轮最先做

#### P0-1 对应 F2：Overview 页补齐 Stockout/Overstock Risk 的模拟数据提示

- **涉及路径**：`app/streamlit_app.py`（`rc2`/`rc3` 两个 `st.metric` 调用，约第 67-68 行）。
- **方案**：给 `rc2`/`rc3` 补上 `help=` 参数，内容对齐 `docs/app_product_spec.md` 原文"这是模拟数据，见模型与数据说明页"，可以复用或新增 `dashboard_data.py` 里的一个简短常量/函数（例如 `simulated_metric_hint()`），避免在三处硬编码同一句英文/中文文案。
- **验收标准**：`tests/test_app_pages.py` 新增断言，验证 Overview 页渲染出的 `at.metric` 中 Stockout Risk / Overstock Risk 两项的 `help` 非空，且包含"simulated"或等价措辞。
- **测试方式**：`AppTest`（现有框架，无需新依赖）。
- **隐私影响**：无——纯文案改动，不涉及任何数据选择或列暴露。

#### P0-2 对应 F1：修正来源时间语义，再补充可信的快照信息

- **涉及路径**：`docs/app_product_spec.md`、`app/pages/2_Model_and_Data_Notes.py`；如果采用持久化运行元数据，再单独设计流水线输出，本轮不改正式输出。
- **方案**：不要把部署文件的 `mtime` 称为数据生成时间。当前最小实现展示已经可靠的交易覆盖截止日期，并标注这是随仓库发布的公共演示快照；可同时显示构建提交。真正的"生成时间"应等流水线以后写入持久化元数据后再展示。若保留 `freshness["files"]`，标签必须明确为"当前部署副本中的文件修改时间"。
- **验收标准**：页面不把 clone/部署产生的时间戳表述为分析生成时间；新增 AppTest 锁定所选文案和不泄露绝对路径。
- **测试方式**：AppTest；在临时 clone/复制目录运行，确认时间变化不会被解释为业务数据更新。
- **隐私影响**：无——只显示公开演示快照的覆盖信息、相对路径或提交标识，不显示本机绝对路径。

#### P0-3 对应 F9：README 把 App 介绍提前，并加目录/锚点

- **涉及路径**：`README.md`。
- **方案**：
  1. 在文件最前面（`## Overview` 之后或之前）新增一个简短的"Try the interactive dashboard"小节/一行加粗提示，指向现有的"Merchant analytics app"小节（锚点链接），不需要移动或重写现有内容本身，只加一个前置指引 + 目录。
  2. 加一个轻量目录（Markdown 列表 + 锚点链接），方便访客跳转到 Data Source、Assumptions and Limitations、Merchant analytics app 等关键小节。
  3. 在页面改动稳定后补至少一张本地生成的产品截图；无需 Claude in Chrome 扩展。若即将部署，也可以等稳定 URL 产生后再截取最终版本。
- **验收标准**：人工审阅 README 渲染效果（GitHub 预览或本地 Markdown 预览），确认开头 30 行内能看到 App 的存在和一个可点击入口。
- **测试方式**：无自动化测试（README 是文档），人工检查即可；不引入新依赖。
- **隐私影响**：无。

### P1 — 中等工作量，直接提升 SKU Analyzer 可用性

#### P1-1 对应 F3：SKU Analyzer 详情页六个模拟指标补齐行内解释

- **涉及路径**：`app/pages/1_SKU_Analyzer.py`（`sim1`~`sim6`，约第 115-132 行）；可能需要在 `dashboard_data.py` 新增类似 `normal_risk_disclaimer()` 的简短说明函数（例如每个指标一句"大白话"，与 Model & Data Notes 页的公式说明保持一致但更短）。
- **方案**：给六个 `st.metric` 分别加 `help=`，内容可以是 Model & Data Notes 页现有公式解释的一句话摘要（避免重复定义两套话术——建议从 `2_Model_and_Data_Notes.py` 现有 markdown 提炼成共享常量/函数，两个页面都调用）。
- **验收标准**：`AppTest` 断言六个 `metric` 元素均有非空 `help`；人工审阅措辞与 Model & Data Notes 页不冲突。
- **测试方式**：`AppTest`。
- **隐私影响**：无。

#### P1-2 对应 F4：SKU Analyzer 增加首次使用引导文案

- **涉及路径**：`app/pages/1_SKU_Analyzer.py`（筛选栏上方，约第 30-31 行）。
- **方案**：在 `st.header("Filters")` 下方加一行 `st.caption`，提示"未筛选时显示全部 SKU；可尝试按库存风险筛选，快速找到需要关注的商品"。是否额外预置一个默认筛选值（例如默认只勾选 Stockout Risk + Overstock Risk）需要用户确认——默认收窄结果可能更友好，但也可能让用户误以为"Normal"的 SKU 被隐藏了、找不到全量视图；本方案建议**只加提示文案，不改默认筛选值**，把"要不要预置默认筛选"列为需要用户确认的小决定（风险低，可在实施前用一句话问用户）。
- **验收标准**：`AppTest` 断言新增的提示文案存在；人工检查提示语气是否符合"非技术商户"受众。
- **测试方式**：`AppTest`。
- **隐私影响**：无。

#### P1-3 对应 F5：SKU 详情选择器显示"代码 — 描述"

- **涉及路径**：`app/pages/1_SKU_Analyzer.py`（`st.selectbox` 调用，约第 85-87 行）。
- **方案**：给 `st.selectbox` 加 `format_func`，从 `filtered` 里按 `stock_code` 查出对应 `description` 并拼成 `"{code} — {description}"` 展示，选中后仍用原始 `stock_code` 做后续查找（`format_func` 不改变底层 value，只改变显示文本）。
- **验收标准**：`AppTest` 断言选择器的可见选项文本包含某个已知 SKU 的描述片段；现有的"选中后渲染详情"断言应继续通过（`sku_detail_selector` 的值仍是 `stock_code`，不破坏现有测试假设）。
- **测试方式**：`AppTest`。
- **隐私影响**：无——`description` 已经是现有 allowlist 字段，本来就会渲染在结果表里，这里只是换了个展示位置。

### P2 — 健壮性与小幅一致性修正，公网演示前应完成

#### P2-1 对应 F7：先用异常 fixture 验证真实缺口，再选择加载层或页面层修复

- **涉及路径**：`tests/test_dashboard_data.py`、`tests/test_app_pages.py`；只有复现失败后才改 `dashboard_data.py` 或页面。
- **方案**：用临时数据覆盖必需字段为空、布尔值为空、描述为空和月份异常等边界。月份异常目前已在 loader 中阻断，不要重复包裹。若复现出页面异常，优先在数据契约入口拒绝不完整数据；只有需要恢复展示的错误才在页面捕获 `DashboardDataError`。不要捕获宽泛 `Exception`。
- **验收标准**：测试证明所有通过 loader 的数据可安全经过筛选、提示和趋势函数；被拒绝的数据产生清晰 `DashboardDataError`；页面不出现未处理异常。
- **测试方式**：数据层单元测试 + AppTest monkeypatch。
- **隐私影响**：无——只影响错误处理路径，不改变任何数据选择逻辑。

#### P2-2 对应 D5：补一句"SKU = 商品"的说明

- **涉及路径**：`app/streamlit_app.py`（首次出现"SKU"处，或页面顶部 caption）。
- **方案**：在 Overview 页顶部 caption 或 "Active SKUs" 指标旁加 `help="SKU（商品/库存单位）："` 之类的简短说明。
- **验收标准**：人工审阅；可选加一个 `AppTest` 断言确认该说明文本存在。
- **隐私影响**：无。

## 二、暂不处理 / 推迟事项（及理由）

| 事项 | 对应发现 | 推迟理由 |
| --- | --- | --- |
| README 截图/GIF | F9 的一部分 | 不需要 Claude 浏览器扩展；在本地页面改动稳定后或部署 URL 确定后制作，以免截图立即过期 |
| 部署依赖配置 | F8 | 当前本地/CI 拆分已验证；目标平台确定后按其官方构建规则显式安装 App 依赖并做全新构建，不预先断言必须合并 requirements 文件 |
| Overview 页三列指标窄屏复核 | D2 | 需要实际截图对比，本轮无浏览器工具；建议与 README 截图任务一起做 |
| 历史/模拟区块加色块视觉分区 | D1 | 规格本身允许仅用文字分区，属于锦上添花，优先级低于上面的功能性缺口 |
| Model & Data Notes 路径改为可点击链接 | D3 | 仓库已经 Public，可以在实现轮使用稳定的 GitHub `blob/main/...` 链接；部署 URL 不是前置条件 |
| 补充"空表"场景的 AppTest 覆盖 | D4 | 用 monkeypatch 返回临时空 DataFrame 即可，不修改正式数据；建议与本轮页面测试一起补齐 |
| `demand_cv` 展示格式 | F6 / U2 | 纯粹的呈现风格判断，需要用户先选一个方向 |
| 是否预置 SKU Analyzer 默认筛选值 | P1-2 的子决定 | 风险低但改变默认行为，建议实施前用一句话问用户，不在本轮方案里擅自决定 |

## 三、适合公开演示的最小交付范围（Minimal Scope）

如果用户决定"先做一个干净、可以公开演示的最小版本"，建议只包含：

1. P0-1、P0-2、P0-3（Overview 提示补齐、Model & Data Notes 可信来源信息、README 前置入口+目录）——不涉及业务公式或敏感数据；P0-2 必须避免把文件 mtime 错称为生成时间。
2. P1-1、P1-3（SKU 详情页行内解释、选择器显示描述）——同样是纯展示层改动。
3. P2-1（异常 fixture 与数据契约加固）——先证明真实失败路径，再做最小修复。

**不建议**包含在"最小范围"里的（即使很想做）：

- README 截图/GIF 不阻塞代码改动，但应在页面稳定后、提交前完成；部署依赖配置等待平台确定。
- P1-2 的默认筛选值变更——涉及一个需要用户确认的产品行为决定，不应该在"最小范围"里顺手改掉。

## 四、部署前检查清单（不选择、不执行任何具体收费服务）

> 以下只是一份清单，供用户在真正决定部署时逐项核对；本轮不执行其中任何一项。

- [ ] **数据可用性**：已核实 `outputs/` 和 `data/processed/` 下 App 依赖的全部 CSV（`sku_inventory_simulation.csv`、`sku_month_demand.csv`、`month_coverage.csv`、`data_quality_summary.csv`、`management_kpi_summary.csv`、`working_capital_summary.csv`）及 `data/raw/Online Retail.xlsx` 均已随仓库提交（非仅本地生成），全新 clone 后无需重跑 notebook 即可读到数据——**本轮已核实，无需重新检查**。
- [ ] **依赖安装**：决定部署平台后，按其官方构建规则显式安装 `requirements.txt` 与 `requirements-app.txt` 中的运行时依赖，确保 `streamlit>=1.49.0`，并用全新构建验证；不要把含 Jupyter/pytest 的 `requirements-dev.txt` 当生产依赖。
- [ ] **公开内容审阅**：仓库已经是 Public。决定是否精简过程性交接文档，并确认 README、截图和 App 文案适合作品集访客。
- [ ] **错误处理健壮性**：完成 P2-1 的异常 fixture；仅对实际复现的缺口实施最小数据契约或页面边界修复。
- [ ] **隐私回归**：部署前重跑一次 `tests/test_app_pages.py` 里"从不渲染禁止列"的测试，并人工过一遍三个页面，确认没有新引入的字段/文案泄露本机路径或内部配置细节。
- [ ] **Streamlit 使用统计**：确认 `.streamlit/config.toml` 的 `gatherUsageStats = false` 随仓库一起部署（这是仓库文件，正常情况下会自动生效，部署后应用 `curl`/界面核对一次）。
- [ ] **健康检查**：确认部署平台会使用或至少不会被 Streamlit 自带的 `/_stcore/health` 端点干扰（本轮本地验证过该端点返回 200，行为正常）。
- [ ] **截图/GIF**：页面稳定后用本地浏览器、现有 UI 工具或手工方式截取；不依赖 Claude in Chrome 扩展。
- [ ] **回归测试**：部署前最后一次运行 `python -m pytest -W error -ra`，确认仍为全绿、0 skipped。

## 五、与"本阶段 vs. 业务参数校准后"的范围边界（回应任务书第 12 条）

本阶段（本文件列出的所有 P0/P1/P2）全部是**展示层**改动：文案、提示、链接、错误处理、README 结构。没有一项涉及：

- 修改 `src/retail_analytics/{cleaning,demand,simulation}.py` 的任何公式；
- 修改 `config/simulation_assumptions.json` 里任何演示/待校准参数（订货成本、持有率、交期、服务水平等）；
- 新增业务参数滑块或"最佳补货参数"建议；
- 接入真实商户数据或客户/订单级字段。

这些都已经被 `docs/app_product_spec.md`"本轮非目标"和本次任务书明确排除，本方案没有触碰，也不建议在业务参数校准（`docs/model_assumptions_plan.md` 的 B1）完成前触碰——即使实施了上面所有展示层改动，App 页面上"demonstration / pending calibration"的措辞仍然原样保留，不会因为这轮优化而被削弱或移除。

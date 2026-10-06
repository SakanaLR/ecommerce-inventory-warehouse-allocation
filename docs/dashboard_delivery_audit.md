# 商户库存分析 Dashboard 交付与展示审查（Claude 诊断，Codex 独立复核）

> 分支 `feature/dashboard-delivery`，审查起点 HEAD `ce86de6`（与 `origin/main` 一致）。本文件只做诊断，未修改 `app/`、`src/`、`tests/`、`.github/`、依赖文件、`.streamlit/`、`config/`、`data/`、`outputs/`、`notebooks/`、`reports/`。Codex 已对 Claude 的条目逐项复核并修正过度结论。

## 零、基线核实

- 分支：`feature/dashboard-delivery`；HEAD：`ce86de65e329e33a93e07e7dbdfcb9cf2e41aced`；与 `git rev-parse origin/main` 一致；`git status --short` 为空。
- `python -m pytest -W error -ra` → **182 passed, 0 skipped**（与用户告知基线一致）。
- 本地冒烟：`streamlit run app/streamlit_app.py --server.headless true --server.port 8765` 后，HTTP 外壳和 `/_stcore/health` 均返回 200；进程随后停止且端口不再响应。Streamlit 路由返回 200 不能单独证明各页完成渲染，三页真实执行证据来自现有 `AppTest`。
- 本轮没有做截图级视觉复核。用户只是拒绝安装 Claude in Chrome 扩展；这不妨碍后续使用本地浏览器、现有 UI 工具或手工截图，因此不能把截图列为外部阻塞项。

## 一、审查条目（含 Codex 复核状态）

Codex 复核后，F1–F5 与 F9 属于确认的产品/规格缺口；F6 是呈现决策；F7 与 F8 是部署前设计风险，不是当前已复现故障。

### F1（中，确认但方案需修正）Model & Data Notes 页缺失规格要求的来源时间信息

- **证据**：`src/retail_analytics/dashboard_data.py:394-433` 的 `data_freshness_notes()` 收集了 `notes["files"]`（每个被监控文件的 mtime），但 `app/pages/2_Model_and_Data_Notes.py:49-51` 只读取并渲染了 `freshness["row_count_warning"]`，从未渲染 `freshness["files"]`。
- **复现步骤**：阅读 `2_Model_and_Data_Notes.py` 全文，搜索 `freshness[` 只出现一次（`row_count_warning`），没有任何 `st.write`/`st.caption` 引用 `freshness["files"]`。
- **用户影响**：规格要求的来源/新鲜度信息没有呈现。但 `mtime` 在新 clone 或部署环境中可能只是检出、复制时间，不能可靠地称为"数据生成时间"。直接把现有 `notes["files"]` 接到页面会制造错误的可信度信号。
- **复核结论**：规格缺口成立；"后端已经算好数据生成时间、只需接线"不成立。实施前应先修正规格，选择明确的来源语义：显示数据覆盖截止日期与构建提交，或让流水线以后生成持久化运行元数据；若暂时展示 `mtime`，必须标成"部署副本中的文件修改时间"。

### F2（中）Overview 页 Stockout Risk / Overstock Risk 指标没有模拟数据提示

- **证据**：`app/streamlit_app.py:63-68`：
  ```python
  rc1.metric("Normal", f"{risk_counts.get('Normal', 0):,}", help=dd.normal_risk_disclaimer())
  rc2.metric("Stockout Risk", f"{risk_counts.get('Stockout Risk', 0):,}")
  rc3.metric("Overstock Risk", f"{risk_counts.get('Overstock Risk', 0):,}")
  ```
  只有 `rc1`（Normal）带 `help=`，`rc2`/`rc3` 完全没有 `help` 参数。
- **规格依据**：`docs/app_product_spec.md` §2 页面 1："模拟区：...每个模拟指标旁有一个 ℹ️ 提示（Streamlit `help=` 参数或 `st.caption`），点开/悬停显示'这是模拟数据，见模型与数据说明页'。"
- **用户影响**：这两个数字恰恰是商户最可能据此做决策的指标（"有多少 SKU 缺货/超储"），却是全页唯一没有任何模拟数据提示的两个模拟指标，打破了页面其余部分建立的"模拟数值旁一律有提示"的一致模式。

### F3（低-中，确认）SKU Analyzer 详情页六个模拟指标缺少逐项解释

- **证据**：`app/pages/1_SKU_Analyzer.py:115-132`（`sim1`~`sim6` 六个 `st.metric` 调用：当前库存、安全库存、再订货点、EOQ、建议补货量、库存覆盖天数）全部没有 `help=` 参数；对比 `app/streamlit_app.py:71-85` 的工作资本三个指标全部带 `help=`。
- **用户影响**：页面已经用小节标题、标签中的 `simulated` 和一条总说明明确这些指标是演示模拟，因此不是"毫无解释"；缺口是 EOQ、再订货点等术语没有逐项 `help`，非技术用户仍需跳到说明页理解。

### F4（低-中，确认）SKU Analyzer 默认展示全部 3,790 个 SKU，但缺少首次使用引导

- **证据**：`app/pages/1_SKU_Analyzer.py:30-53`，三个 `st.multiselect` 和一个 `st.text_input` 默认都是空/`None`；`filter_sku_profile` 在所有筛选参数为空时返回原始 `profile`（`dashboard_data.py:315-337`）。首次打开页面即渲染"Matching SKUs (3,790 of 3,790)"的全量表格和同样大小的 selectbox。
- **用户影响**：全量目录本身可以是合理默认行为，不能直接认定为缺陷；确认的问题是页面没有告诉首次使用者如何用搜索与三个 AND 筛选器缩小结果。优先补引导，不擅自预置某个风险筛选。

### F5（低-中）SKU 详情选择器只显示裸 `stock_code`，没有描述

- **证据**：`app/pages/1_SKU_Analyzer.py:85-87`：
  ```python
  selected_code = st.selectbox(
      "Select a SKU for detail", filtered["stock_code"].tolist(), key="sku_detail_selector"
  )
  ```
  下拉框选项就是原始字符串如 `85123A`，没有拼接商品描述。
- **用户影响**：用户在上方表格里看到一个感兴趣的商品后，往下滚动到选择器时，只能靠记住一串字母数字代码去匹配，容易选错或需要反复上下滚动核对。

### F6（低-中，可能是设计选择而非缺陷，列为需要确认）`demand_cv` 用百分比格式展示，与仓库自身文档的约定不一致

- **证据**：`app/pages/1_SKU_Analyzer.py:74`：`display["demand_cv"] = display["demand_cv"].map(dd.format_percent)`，表格列标题为"Demand CV (monthly sales)"，数值会显示成类似"101.0%"。而 `README.md`"SKU portfolio"一节原文："median CV of 1.01"——仓库自己的文档把这个量当作无单位比值（而非百分比）呈现。
- **用户影响**：同一个统计量在 App 里是百分之几百，在 README 里是 1 点几，两者对不上，容易让同时看两份材料的人（例如作品集访客）产生"这是不是算错了"的疑惑。这更像是一个呈现风格的判断题，不是明显的程序错误，列入下文"需要用户决定"。

### F7（未确认故障，降级为健壮性建议）SKU Analyzer 后续纯函数没有额外页面级异常边界

- **证据**：`app/pages/1_SKU_Analyzer.py:23-28` 只对 `dd.load_sku_profile`/`dd.load_sku_month_demand` 做了 `try/except DashboardDataError`；第 98 行的 `dd.sku_month_trend(month_demand, selected_code)`、第 45 行的 `dd.filter_sku_profile(...)`、第 93 行的 `dd.short_history_notice(row)` 均未被保护。
- **复核结论**：`load_sku_month_demand()` 已在返回前验证月份格式，所以所述 `sku_month_trend()` 失败路径无法由通过加载器的当前数据触发；筛选与提示函数也没有正常数据下的已知 `DashboardDataError` 路径。无需为了形式统一而给每个纯函数套 `try/except`。下一轮应先用含空值/异常值的临时 fixture 证明真实失败，再决定是在加载层收紧非空约束还是在页面层增加边界。

### F8（部署兼容性风险，未确认故障）运行时依赖拆分需要与目标平台配置对齐

- **证据**：已读取三份依赖文件原文——
  - `requirements.txt`：仅 `pandas>=2.2.3`、`numpy>=1.26.0`、`openpyxl>=3.1.0`。
  - `requirements-app.txt`：`streamlit>=1.49.0`（App 专用）。
  - `requirements-dev.txt`：`-r requirements.txt` + `-r requirements-app.txt` + `jupyter`/`ipykernel`/`pytest`/`nbconvert`。
  当前拆分对本地开发和 CI 是清晰且已验证的。
- **复核结论**：未选择目标平台、也未按该平台的官方构建规则试部署，不能断言"默认一键部署无法运行"。真实风险是目标平台必须安装 `requirements-app.txt` 或等价依赖，并遵守 `streamlit>=1.49.0`。平台确定后再按官方配置做一次全新构建验证。

### F9（中-高，确认）README 顶部没有展示交互式 App；仓库没有产品截图或目录

- **证据**：
  - `grep -n "Streamlit\|streamlit\|app/" README.md` 的第一个命中在第 239 行（"Merchant analytics app"小节，位于"How to Run"深处），文件总长约 328 行。
  - 文件开头的 `## Overview`（第 1-24 行，GitHub 访客打开仓库第一眼看到的内容）只描述了 notebook/数据流水线，完全没有提到存在一个可交互的 Streamlit Dashboard。
  - `grep -ni "screenshot" README.md` 无命中；`find . -iname "*.png" -o -iname "*.jpg" -o -iname "*.gif"`（排除 `.venv` 第三方资源）无任何仓库自有的图片文件。
  - README 没有目录（Table of Contents）。
- **用户影响**：直接命中审查角度 #11——这正是本轮任务书点名的目标（"商户库存分析 Dashboard 的交付与展示优化"），但目前一个只读 README 顶部的作品集访客完全不会知道这个 App 存在，更看不到它长什么样，必须读完大半篇技术性很强的 notebook 流水线说明才会偶然发现。

## 二、设计建议（非确认缺陷，供下一轮取舍）

- **D1** 历史/模拟数据的视觉区分目前完全依赖文字标题和列名后缀（如"(simulated)"），没有背景色块或侧边色条；`docs/app_product_spec.md` §4 原文允许"不同背景色块**或**明确的小节标题"二选一，所以不算违规，但 SKU Analyzer 的结果表把历史列（SKU class、Historical revenue、Demand CV…）和模拟列（Inventory risk (simulated)、Warehouse strategy (simulated)）混排在同一张表里，只靠列名后缀区分——快速扫一眼表格时视觉上不会自然分区，值得在下一轮加轻量的列分组或色条。
- **D2** Overview 页的两组三列指标（`rc1/rc2/rc3`、`wc1/wc2/wc3`）在"普通笔记本但浏览器窗口不是全宽"的场景下，参照 SKU 详情页此前被 Codex 从四列改两列的先例，可能同样偏窄；本轮未获浏览器工具授权，无法截图实证，列为"待可视化验证"而非确认问题。
- **D3** Model & Data Notes 页引用的仓库内路径是纯文本、不可点击。仓库当前已经是 Public，因此无需等待仓库公开；可以在部署前改成稳定的 GitHub `blob/main/...` 链接，同时保留路径文字。
- **D4** `docs/app_product_spec.md` §6 的"空表（0 行）正常渲染"目前只在纯函数层覆盖，页面级 AppTest 没有覆盖。无需修改真实 `data/`/`outputs/`：下一轮可用 monkeypatch 替换加载器返回临时空 DataFrame，安全验证页面行为。
- **D5** "SKU"这个词在三个页面反复出现（页面标题"SKU Analyzer"、"SKU class"、"Active SKUs"等），面向规格书明确定义的"非技术商户"受众，全程没有被解释成"商品"；Model & Data Notes 页也没有补一句说明。建议在 Overview 页该词第一次出现处加一句簡短说明。

## 三、待用户决定事项

- **U1** 是否要在"作品集访客可见"的分支/发布形态里精简或隐藏过程性协作日志（`docs/current_task.md`、`docs/handoff.md`）——这两份文件记录了多轮 Claude/Codex 协作细节，对协作过程有价值，但对只想看成品的访客可能是噪音。`docs/pr_delivery.md` 此前已把这个问题列为未决项，本轮确认仍未解决，且因为本轮审查对象明确包含"作品集浏览者"，这个决定变得更直接相关。
- **U2** F6 提到的 `demand_cv` 展示格式：维持百分比（当前实现）还是改成与 README 一致的纯小数比值——这是呈现风格判断，不是对错问题。
- **U3** README 截图/GIF 的补充时机：在本地完成页面修改后生成，还是等有稳定部署地址后再生成。它不依赖 Claude in Chrome 扩展。
- **U4** 部署平台的选择与实际执行时机——本轮任务书明确要求"评估"但"不得实际部署、登录外部服务、创建云资源",所以这里只给出技术checklist（见 `docs/dashboard_delivery_plan.md`），平台选择本身留给用户。

仓库已经是 Public，因此仓库可见性不是待决事项；U1 应按当前公开状态直接处理。

## 四、本轮实际检查范围

- 代码：`app/streamlit_app.py`、`app/pages/1_SKU_Analyzer.py`、`app/pages/2_Model_and_Data_Notes.py`、`src/retail_analytics/dashboard_data.py`（全文）。
- 测试：`tests/test_app_pages.py`、`tests/test_dashboard_data.py`（全文阅读，未修改，用于判断已有覆盖和盲区）。
- 配置：`.streamlit/config.toml`、`.github/workflows/tests.yml`、`requirements.txt`、`requirements-app.txt`、`requirements-dev.txt`、`.gitignore`。
- 文档：`docs/app_product_spec.md`、`docs/current_task.md`、`docs/handoff.md`（全文）、`docs/pr_delivery.md`、`README.md`（全文）。
- 数据可用性核查：`git ls-files outputs/ data/processed/ data/raw/`，确认 App 依赖的全部 CSV（含 `outputs/sku_inventory_simulation.csv`、`data/processed/sku_month_demand.csv` 等）和原始 `data/raw/Online Retail.xlsx` 均已随仓库提交（不是仅本地生成、未跟踪），这意味着"全新克隆即可跑 App"这一点本身没有问题。
- 本地动态验证：严格测试 `python -m pytest -W error -ra`（182 passed, 0 skipped）；Streamlit HTTP 外壳/健康端点检查；三页真实执行由现有 AppTest 覆盖。
- 未做（且本轮范围不允许做）：截图级视觉复核、notebook 重跑、真实部署尝试、修改任何业务代码/依赖/测试/配置文件。

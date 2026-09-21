# 当前任务：商户库存分析 App —— 信息架构与只读 MVP

> 本文件已从"交付基线收口与自动化验证"改为"商户库存分析 App"。上一轮（交付基线收口）已完成并已提交、已 push 到 `origin/audit/model-assumptions`（HEAD `9cb8932`）。本轮是**新分支**（`feature/merchant-analytics-mvp`，从 `9cb8932` 切出），实现一个面向商户的只读 Streamlit 分析 App，**不修改模型公式、`config/`、`data/`、`outputs/`、notebook 或历史基线报告**。原任务书作为历史背景保留在下方。

## 基线核实结果（本轮开始前重新核实）

- 分支：`audit/model-assumptions`；HEAD：`9cb8932149507c19747c5873a34c3ad871182f4a`；工作区干净；`origin/audit/model-assumptions` 已存在——均已用 `git status`/`git branch -a`/`git rev-parse HEAD`/`git log` 实际核实，与用户告知的状态一致。
- 测试基线：`python -m pytest -W error -ra` → **127 passed, 0 skipped**（本轮开始前重新运行确认）。
- 从 `9cb8932` 新建 `feature/merchant-analytics-mvp` 分支，本轮全程在该分支上单独写入，未启动其他修改会话。

## 本轮范围与产出

只做信息架构 + 只读 MVP，不做参数场景比较、登录、云部署或小程序（详见 `docs/app_product_spec.md`"本轮非目标"）：

1. **`docs/app_product_spec.md`（新建，先于实现编写）：** 目标用户与经营问题、三个页面的页面与交互、指标定义/单位/数据来源、历史事实与模拟指标的区别、隐私边界、空数据/缺列/输出过期时的行为、本轮非目标。
2. **`src/retail_analytics/dashboard_data.py`（新建）：** 只读数据适配层，与页面逻辑完全分离。定义 `REQUIRED_SKU_PROFILE_COLUMNS` 等 schema 常量（未来商户本地聚合文件的数据契约）和 `FORBIDDEN_COLUMNS`（`customer_id`/`invoice_no`/`invoice_date`/`cancel_invoice_no`/`credit_invoice_no`）隐私拒绝名单。读取后先检查原始表头的禁止列，随后只返回明确 allowlist 的聚合字段；同时校验数值/布尔类型和唯一键，拒绝会导致重复聚合的 SKU 或 SKU×月记录。缺文件、零字节文件、缺列、错误类型、重复键或含禁止列均抛出 `DashboardDataError`，带清晰指引信息。聚合函数（历史指标、模拟风险计数、筛选、月度趋势、`short_history` 提示文案、`Normal` 风险免责声明、数据新鲜度提示）都是不依赖 Streamlit 的纯函数。
3. **`app/` 目录（新建）：** 三个 Streamlit 页面——`app/streamlit_app.py`（经营总览，入口）、`app/pages/1_SKU_Analyzer.py`（SKU 分析器）、`app/pages/2_Model_and_Data_Notes.py`（模型与数据说明）。所有路径通过 `Path(__file__).resolve()` 相对仓库根解析，不依赖启动时的 shell 目录。
4. **`requirements-app.txt`（新建）：** `streamlit>=1.49.0`——这不是随意选的下限，是因为 `app/*.py` 用到的 `st.dataframe(..., width="stretch")` 里 `width` 参数接受字符串枚举值是从 Streamlit 1.49.0 才开始支持的（1.48.x 及更早版本只接受 int/None，传字符串会直接 `TypeError`），逐版本二分实测确认。`requirements-dev.txt` 新增 `-r requirements-app.txt`，因为 pytest 的 `tests/test_app_pages.py` 需要它。
5. **测试（新增 55 个：`tests/test_dashboard_data.py` 41 个、`tests/test_app_pages.py` 14 个）：** 覆盖数据加载/schema 校验、指标聚合与格式化、SKU 搜索与组合筛选、空筛选/零字节文件/缺列/禁止列/错误类型/重复键的失败行为、allowlist 和非共享 DataFrame、`short_history` 提示逻辑、历史指标与模拟指标不会互相污染（用变异测试证明）、隐私列的显式拒绝测试（对 `FORBIDDEN_COLUMNS` 逐个参数化）、三个页面的 Streamlit `AppTest` 冒烟测试、组件 key、Streamlit 使用统计关闭配置、从仓库外 `cwd` 启动时路径仍正确。
6. **README：** 新增"Merchant analytics app"一节（启动命令、三个页面简介），更新仓库结构树。

## 验收结果

Codex 定向验收新增输入隐私、allowlist、类型/重复键、组件 key、展示格式和 Streamlit 使用统计关闭的覆盖后，两个全新 Python 3.11 临时环境分别按 `requirements-dev.txt` 的最新解析版本和全部声明下限（含 `streamlit==1.49.0`）运行 `python -m pytest -W error -ra`，均为 **182 passed, 0 skipped**。CI workflow 的 pip 缓存键也纳入 `requirements-app.txt`，安装使用 `python -m pip`。`git diff --check` 通过。`config/`、`data/`、`outputs/`、`notebooks/`、`reports/` 均未出现在本轮 `git status --short` 差异中——正式文件未被改写；受保护的 129 个已跟踪路径已在验收前后以 SHA-256 复核。AppTest 实际执行了三个页面及其关键筛选/空状态/短历史交互，未使用仅检查 HTTP 200 来代替页面验收。

## Git 基线

分支 `feature/merchant-analytics-mvp`，起点 `9cb8932149507c19747c5873a34c3ad871182f4a`（本轮全程未变化，未 commit、未 push）。

---

## 历史背景 6：交付基线收口与自动化验证（上一轮，已完成、已提交、已 push）

> 该轮把 `docs/current_task.md`/`docs/handoff.md`/`CHANGELOG.md` 的顶部状态与实际提交（`bfdc558`）对齐，新增 GitHub Actions（`.github/workflows/tests.yml`，JUnit XML 校验 0 skipped）、依赖版本下限（`requirements.txt` 只保留 `pandas`/`numpy`/`openpyxl`，`jupyter`/`ipykernel`/`nbconvert`/`pytest` 移到 `requirements-dev.txt`，移除未使用的 `matplotlib`）、核实数据集许可（UCI Online Retail 数据集为 CC BY 4.0）与代码许可现状（无 LICENSE 文件，未替用户选择）、新增 `CITATION.cff` 和 `docs/pr_delivery.md`。过程中发现并修正了一处会在全新 CI 检出下必定失败的测试断言（`untracked_file_sha256` 非空检查）。本轮结束时该分支已提交并 push 到 `origin/audit/model-assumptions`（HEAD 演进为 `9cb8932`：这是 Codex 在该轮基础上进一步调整 CI 校验方式为 JUnit XML、拆分依赖文件、修改 `CITATION.cff` 作者字段后的提交，细节见 `docs/handoff.md`"历史交接：交付基线收口与自动化验证"）。完整记录见 `docs/handoff.md` 与 `CHANGELOG.md`。

---

## 历史背景 5：实施 R1/T1/T2/E1 + Codex 验收强化（上一轮，已提交为 `bfdc558`）

> 该轮完成了 `docs/model_assumptions_plan.md` 的 R1（文档纠正）、T1（`tests/test_demand_simulation_interface.py`，8 个测试）、T2（`tests/test_simulation.py` 新增 12 个测试）、E1（`scripts/model_assumptions_diagnostics.py`），随后 Codex 独立验收并加固了 E1（原子写入、拒绝已存在目录/符号链接、配置兼容性校验、更完整的元数据字段）、新增 `tests/test_model_assumptions_diagnostics.py`，最终测试数到 127，提交为 `bfdc558`（未 push）。完整记录（含逐项数字对照、变异测试证据）见 `docs/handoff.md`"历史交接：实施 R1/T1/T2/E1"及其后的 Codex 验收章节。未实施 B1（业务参数校准），未重开 B2/D1（短窗口保守策略研究）。

## 历史背景 4：模型假设诊断轮 + Codex 独立复核与方案（更早一轮，已完成）

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

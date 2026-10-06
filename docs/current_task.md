# 当前任务：交付基线收口与自动化验证

> 本文件已从"实施 R1/T1/T2/E1"改为"交付基线收口与自动化验证"。R1/T1/T2/E1 的实施（Claude）与 Codex 的独立验收强化（提交 `bfdc558`：E1 加固、新增 `tests/test_model_assumptions_diagnostics.py`、127 个测试）均已完成并已提交到本地分支（未 push）。本轮只处理交付文档一致性、CI 自动化和依赖可复现性，**不修改业务模型、正式参数、notebook、`data/processed/`、`outputs/` 或历史基线报告**。原任务书作为历史背景保留在下方。

## 基线核实结果（本轮开始前重新核实，未直接采信预期状态）

- 分支：`audit/model-assumptions`；HEAD：`bfdc5586f751f6e9d43063e642a7dd6b6f336018`；工作区在本轮开始前干净；未 push（`git status -sb` 无 ahead/behind 上游信息）——以上均与用户告知的预期状态一致，已用 `git status`/`git branch --show-current`/`git rev-parse HEAD`/`git log` 实际核实。
- **测试基线有出入，已发现并修正**：直接运行 `python -m pytest -W error -ra` 得到 **126 passed, 1 failed**（`tests/test_model_assumptions_diagnostics.py::test_cli_scenarios_are_independent_deterministic_and_described` 失败在 `assert metadata['code']['untracked_file_sha256']`）——不是"127 passed, 0 skipped"。根因：该断言要求诊断脚本的 `run_metadata.json` 里 `untracked_file_sha256` 字段非空，但这个字段的值取决于当前工作区**恰好有没有**未跟踪文件；本轮开始前工作区是干净的（Codex 验收记录时工作区里还有临时产物，断言当时能通过），在一个全新 CI 检出（永远没有未跟踪文件）下这条断言会**必定失败**。已将断言改为检查字段类型（是 dict）而非非空，不改变诊断脚本本身的行为。修正后重新运行：**127 passed, 0 skipped**，此后本文件里的"127 passed"均指修正后的结果。

## 本轮范围与产出

只处理交付、CI 和可复现性，不改业务模型/正式参数/notebook/`data/processed/`/`outputs/`/历史基线报告：

1. **状态文档收口：** 本文件与 `docs/handoff.md`、`CHANGELOG.md` 更新为与 `bfdc558`/127 passed/已提交未 push 一致，历史记录全部保留在下方，不再让顶部状态显示旧基线（`50ce335`/98 passed 等）。
2. **GitHub Actions（`.github/workflows/tests.yml`）：** Python 3.11，全新检出安装 `requirements-dev.txt`，运行 `python -m pytest -W error -ra --junitxml=pytest-results.xml`，并读取 JUnit XML 的机器可验证 skipped 计数；任何跳过即失败。用 pip 缓存和最小 `contents: read` 权限，不引入发布/打包流程。
3. **依赖可复现性：** `requirements.txt`/`requirements-dev.txt` 从"完全不锁版本"改为"仅设下限，不设上限"；运行时文件只保留代码实际导入的 `pandas`、`numpy`、`openpyxl`，notebook 执行所需的 `jupyter`、`ipykernel`、`nbconvert` 单独放在 `requirements-dev.txt`；移除了项目中实际未被任何代码或 notebook 引用的 `matplotlib`。运行时下限（`pandas>=2.2.3`、`numpy>=1.26.0`、`openpyxl>=3.1.0`、`pytest>=8.0.0`）在全新临时环境中实际装到这些精确版本并跑过 `pytest -W error -ra`（127 passed, 0 skipped）；notebook 依赖本轮验证了安装，但未以最低版本执行 notebook，已在文件注释中明确注明。
4. **许可与数据归属：** 核实仓库当前没有任何 LICENSE 文件（默认视为保留所有权利）；核实 `data/raw/Online Retail.xlsx` 来源于 UCI Machine Learning Repository 的 "Online Retail" 数据集（Daqing Chen 捐赠，DOI 10.24432/C5BW33），该数据集页面明确以 **CC BY 4.0** 授权，允许再分发和商业使用（需署名）——已通过 `WebFetch` 实际访问 UCI 页面核实，不是凭记忆断言。README 新增"License"与"Data Source"下的许可/引用说明；新增 `CITATION.cff`（只记录稳定仓库 URL，以 CFF schema 要求的非个人占位作者 `Repository maintainers` 代替未经确认的个人身份，数据集引用取自 UCI 页面原文）。**代码本身该用什么许可证留给用户决定**，未替用户选择。
5. **`docs/pr_delivery.md`（新建）：** 问题、最终行为、主要阶段、验证证据、已知限制、审查建议，明确库存/成本/交期/服务水平仍是演示/待校准参数。

## 验收结果

详见 `docs/handoff.md` 本轮交接（完整命令、干净环境安装与测试证据、CI 工作流内容、依赖下限验证方法、许可核实过程、正式文件哈希不变的证据）。摘要：`pytest -W error -ra` 在项目 `.venv` 与两个独立的全新临时环境（当前锁定版本的环境、依赖下限版本的环境）中都是 **127 passed, 0 skipped**（前提是先修正了下方发现的一处测试基线问题）；`git diff --check` 通过；`config/`、`data/`、`outputs/`、`notebooks/` 及历史基线报告哈希在本轮前后不变。

## Git 基线

分支 `audit/model-assumptions`，HEAD `bfdc5586f751f6e9d43063e642a7dd6b6f336018`（本轮全程未变化，未 commit、未 push）。

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

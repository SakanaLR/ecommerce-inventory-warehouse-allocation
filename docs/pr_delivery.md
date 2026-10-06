# PR 交付草稿（Delivery Draft）

> 本文件是提交前的复核材料，不代表已经 push 或已创建 PR。分支 `audit/model-assumptions`，HEAD `bfdc5586f751f6e9d43063e642a7dd6b6f336018`，未提交到远端。目标合并分支由用户决定（分支是从 `phase1-data-correctness` 上的 `50ce335` 切出的，是否直接合并回 `phase1-data-correctness`、`main`，还是先合并中间分支，需要用户审阅整条提交历史后决定）。

交付边界：`bfdc558` 是已经提交的 R1/T1/T2/E1 基线；本轮 CI、依赖、引用和状态文档修改仍在工作区，尚未包含在该提交中，也未 push。只有本轮审查完成并经用户批准后，才可组织下一次提交。

## 问题（What was broken / missing）

这条分支承接了一系列多轮 Claude↔Codex 协作诊断出的问题，本 PR 是其中"模型假设审计 + 交付收口"两轮的成果：

1. **模拟模型的关键参数（`ordering_cost_gbp`、`max_order_coverage_days`、`supplier_lead_time_days`、服务水平表）此前没有任何来源说明**，容易被误当成已校准的业务参数，而实际都是演示假设。
2. **多处文档定义与代码实际行为不一致**：`docs/runbook.md` 把 `overstock_capital_exposure` 描述成"超过 180 天需求的单位数"，但当前 `max_stock` 方法的真实有效阈值是 `max(reorder_point + EOQ, daily_demand × coverage_days)`；`demand_cv` 此前没有准确定义，容易被误解为"订单量波动"而非"含零月份的月度销量相对波动"。
3. **一份内部诊断报告（`docs/model_assumptions_audit.md`）的措辞超出了证据范围**：把"固定库存重算超储阈值后 699/1,008 个 SKU 变为 Normal"这一结果，写成了通用的"误报比例"，但独立复核证明这只在"固定当前库存快照、只换阈值"这一种实验方法下成立；换成"完整重新生成库存"的方法，结果方向相反（超储数不降反升）。
4. **`src/retail_analytics/demand.py`→`simulation.py` 的短历史/边界情形缺少端到端测试**（0/1/2/3 个月观测、EOQ 封顶整数边界、超储阈值严格边界），只在各自模块内部有零散覆盖。
5. **没有可复现、带完整元数据的方式**去重新生成"固定库存 vs. 完整重生成"两种实验和九个参数敏感性场景的结果——此前只有一次性的分析脚本产出的报告文字，没人能独立重跑验证。
6. **没有 CI**：所有验证都靠人在本地手动跑 `pytest`，也没有人检查过"假设原始数据文件缺失，测试会不会静默跳过而不是报错"。
7. **依赖版本完全没有下限**（`requirements.txt`/`requirements-dev.txt` 只写包名），无法保证在别人的机器或 CI 上装到能跑通的版本组合；同时 `matplotlib` 被列为依赖但项目里完全没用到。
8. **仓库既没有代码许可证，也没有说明 `data/raw/Online Retail.xlsx` 的来源和许可**，无法判断这份数据能不能合法地留在一个可能公开的仓库里。

## 最终行为（What it does now）

- 文档准确描述当前生效的模拟模型（`policy_band`/`service_level`/`eoq`/`max_stock`）及其真实公式，标注哪些参数是"演示/待校准"，不虚构责任人或校准日期。
- `docs/model_assumptions_audit.md` 保留作为历史材料，顶部有醒目横幅链接到独立复核（`docs/model_assumptions_review.md`）和后续方案（`docs/model_assumptions_plan.md`），避免读者直接采信未经复核的原始措辞。
- `scripts/model_assumptions_diagnostics.py`：一个显式接收 `--profile`/`--config`/`--output-dir` 的诊断 CLI，可以随时重新生成"固定库存实验 A"、"完整重生成实验 B"和九个敏感性场景，附带完整元数据（代码提交号、工作区脏污状态、输入哈希、依赖版本、seed、每个场景的实际参数变化值），拒绝写入任何正式目录，不做参数寻优。
- 新增 27 个测试（T1 8 个、T2 12 个、Codex 加固时新增的 CLI 安全性测试若干），覆盖需求短历史/边界情形端到端衔接、EOQ 封顶整数边界、超储阈值严格边界、固定库存与完整重生成两种实验方法论的对照。
- 新增 GitHub Actions（`.github/workflows/tests.yml`）：全新检出、Python 3.11、装 `requirements-dev.txt`、跑 `pytest -W error -ra --junitxml=pytest-results.xml`，并读取 JUnit XML 的 skipped 计数；跳过即视为失败。workflow 只声明 `contents: read` 权限。
- `requirements.txt`/`requirements-dev.txt` 改为只设下限、不设上限的版本约束；运行时文件只含 pandas、NumPy、openpyxl，Jupyter/nbconvert/ipykernel 单独放入开发与 notebook 执行依赖；下限版本经过干净临时环境实测验证；移除未使用的 `matplotlib`。pytest 不再保留没有独立兼容依据的 `<10` 上限。
- README 新增"License"（如实说明代码目前没有许可证，默认保留所有权利，选择许可证留给仓库所有者决定）和"Data Source"下的数据集许可/引用说明（核实为 CC BY 4.0，附官方引用文本）；新增 `CITATION.cff`。

## 主要阶段（Phases this PR's history covers）

1. **模型假设诊断**（Claude）：短历史需求统计、EOQ 封顶行为、参数敏感性分析，产出 `docs/model_assumptions_audit.md`。
2. **独立复核**（Codex）：逐项复核诊断结论，多处从"已确认"降级为"部分成立"或"证据不足"并给出更准确的措辞，产出 `docs/model_assumptions_review.md` 和后续方案 `docs/model_assumptions_plan.md`。
3. **实施 R1/T1/T2/E1**（Claude）：按复核后的方案纠正文档、补充边界测试、实现可复现诊断工具；不进入业务参数校准（B1），不重开短窗口策略研究（B2/D1）。
4. **验收强化**（Codex，提交 `bfdc558`）：加固诊断工具（原子写入、拒绝已存在目录/符号链接、配置兼容性校验）、补充 CLI 安全性测试，测试数到 127。
5. **交付基线收口与自动化验证**（本轮，Claude）：状态文档与实际提交对齐、新增 CI、依赖版本下限、许可与数据归属核实、本 PR 草稿。

更早的阶段（清洗规则修正、需求口径重算、Phase 3A→3B-1 模拟模型升级等）记录在 `docs/handoff.md` 更靠后的"历史交接"部分和 `CHANGELOG.md` 更靠下的条目里，本 PR 不重复其内容。

## 验证证据（Verification evidence）

| 验证 | 环境 | 结果 |
| --- | --- | --- |
| 严格测试（项目 `.venv`） | Python 3.11.5, pandas 3.0.3, numpy 2.4.6, pytest 9.1.1 | **127 passed, 0 skipped**（修正一处会在全新检出下必定失败的测试断言后） |
| 严格测试（全新克隆 + 全新 venv，锁定版本） | Python 3.11.5, pandas 3.0.6, numpy 2.4.6, openpyxl 3.1.5, pytest 9.1.1, nbconvert 7.17.1 | **127 passed, 0 skipped** |
| 严格测试（全新 venv，依赖下限版本） | Python 3.11.5, **pandas 2.2.3, numpy 1.26.0, openpyxl 3.1.0, pytest 8.0.0** | **127 passed, 0 skipped** |
| JUnit XML skipped 计数于以上两次全新环境的 pytest 输出 | — | 均为 0 |
| `git diff --check` | — | 通过，无空白符问题 |
| 正式文件哈希 | `config/`、`data/`、`outputs/`、`notebooks/`、历史基线报告 | 本轮前后一致，`git status --short` 未显示任何这些路径下的改动 |
| 数据集许可核实 | `WebFetch` 直接访问 `https://archive.ics.uci.edu/dataset/352/online+retail` | CC BY 4.0，创建者 Daqing Chen（London South Bank University），DOI 10.24432/C5BW33 |
| E1 诊断工具复现独立复核数字 | 见上一轮 `docs/handoff.md` | 基线、A、B、九场景的库存价值/风险计数/缺货件数/资金敞口与 `docs/model_assumptions_review.md` 表格逐项精确匹配；两次重跑结果逐字节一致 |

## 已知限制（Known limitations）

- **库存、成本、交期和服务水平仍然是演示/待校准参数**：`ordering_cost_gbp`（£25/次补货事件）、`annual_holding_rate`（25%）、`max_order_coverage_days`（180 天）、`overstock.coverage_days`（180 天，含义与前者不同）、`supplier_lead_time_days`（7–45 天加权分布）、各类别服务水平，均未经真实采购/仓储/供应商数据校准，不能用于真实经营决策；`docs/model_assumptions_plan.md` §7（B1）列出了校准所需的业务依据，尚未启动。
- 未进行业务参数校准（B1），也未重新讨论是否给短历史 SKU 增加保守安全库存系数（B2/D1）——这两项都需要用户先做业务口径决定。
- `jupyter`/`ipykernel`/`nbconvert` 的依赖下限是按惯例设置的，没有像 `pandas`/`numpy`/`openpyxl`/`pytest` 那样在干净环境里逐一实测下限版本（因为它们只用于跑 notebook，不在 pytest 覆盖范围内）。
- 代码本身的许可证仍未选择——本 PR 只如实记录了"目前没有许可证"这一事实和数据集自身的 CC BY 4.0 授权，没有替用户做许可证选择。
- 本 PR 涉及的是 `audit/model-assumptions` 分支相对其起点 `50ce335` 的改动；再往前（Phase 1 清洗修正、需求口径重算、Phase 3A→3B-1 模拟模型升级）的历史改动包含在同一分支里，一并成为这次合并的一部分，审阅时需要注意范围。

## 审查建议（Suggested review focus）

1. 先看 `docs/model_assumptions_review.md`（独立复核）和 `docs/model_assumptions_plan.md`（方案），了解哪些诊断结论被修正、修正成了什么，再看原始诊断 `docs/model_assumptions_audit.md`（现在顶部有横幅指向前两者）。
2. 重点复核 `scripts/model_assumptions_diagnostics.py` 的目录保护逻辑（`_ensure_safe_output_dir`）和 `tests/test_model_assumptions_diagnostics.py` 里对应的安全性测试，确认拒绝写入正式目录的护栏没有遗漏路径。
3. 确认 `.github/workflows/tests.yml` 里的"0 skipped"检查逻辑符合团队对 CI 失败阈值的预期（目前读取 JUnit XML 的 skipped 计数，任何一个跳过就失败）。
4. 确认 `requirements.txt`/`requirements-dev.txt` 的下限版本选择可接受；如果团队有更保守或更激进的版本策略偏好，这是可以讨论调整的一处。
5. **许可证决定**：README 和 `CITATION.cff` 如实记录了现状（代码无许可证、数据为 CC BY 4.0），但代码本身要不要加许可证、加哪种，需要仓库所有者决定——这不是本 PR 能替用户做的判断，建议作为一个独立的、明确的审查/决策项。
6. 确认是否需要在合并前把 `docs/current_task.md`/`docs/handoff.md` 这类过程性交接文档从最终发布分支中精简或移除（它们对协作过程有记录价值，但对最终读者可能是噪音）——这也是一个留给用户的取舍，本 PR 未做任何删减。

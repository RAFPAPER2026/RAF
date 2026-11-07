# RAF 框架

RAF（Rubric Auto-generation Framework）解决的是长程 Agent 评测中的量规构建问题：细粒度量规区分度高，但逐例设计成本高，而既有自动生成流程又缺少对量规质量本身的验证。RAF 把“LLM 生成”与“与人类偏好的一致性验证”耦合起来，使量规质量从“假设成立”变为“经验证”。

本篇说明 RAF 的方法与工程实现；平台使用见 [raf/README.zh-CN.md](../raf/README.zh-CN.md)，评测执行见 [评测流程](evaluation.zh-CN.md)。

## 核心思想

- **AND–OR 量规树**：每个任务配一棵量规树，叶子是二元、可客观判定的检查项，内部节点用 AND / OR 组合。AND 表达“同一实体/同一决策下多个条件必须同时满足”，OR 表达“多条可接受路径”。
- **完成与质量分离**：完成量规只问“目标达成了吗”（二元），质量量规只问“过程有多好”（加权连续分），两者边界严格区分。
- **以人类偏好为准绳**：量规的最终验收指标不是主观印象，而是量规评分与人工偏好金标的一致性（Alignment = 0.8 × Pearson + 0.2 × QWK）。
- **可审计的迭代**：每一次修改都可追溯到一次专家审核或一次定量诊断；循环在一致性达标后终止。

## RAF 五步

论文中 RAF 的流程是：

| 步骤 | 论文中的动作 | 平台实现 |
|---|---|---|
| 1. 生成（Generation） | LLM 依据设计好的 prompt 生成初始 AND–OR 量规 | 量规构建页 / `generate_rubric.py` / 批量生成，使用内置 prompt 版本 |
| 2. 专家审核（Expert review） | 专家检查重大缺陷（意图覆盖缺失、不可判定项）；发现问题则直接跳到第 5 步 | 审核页（1–5 星 + 备注）；优化实验中的人工质量初筛（approved / rejected） |
| 3. 评分记录（Score recording） | 裁判在当前量规下给该 case 的轨迹打分，并与人工标注的偏好金标比较 | 评分页逐叶子勾选；优化实验提交“gold + 多位评分者”的评分表 |
| 4. 终止判定（Termination） | 计算 Alignment：高于阈值则接受量规，否则把不一致归因后送入第 5 步 | 优化实验的“中止判断”（`check_stopping` / `/check-stop`） |
| 5. 建议、采纳与精炼（Suggestion, adoption, refinement） | LLM 根据专家报告或定量诊断提出修改建议；专家逐条审核；LLM 按采纳建议精炼，然后回到第 2 步 | RIFT 诊断生成建议 → 人工勾选采纳 → 逐模块精炼生成新 prompt 版本 |

> 实现说明：平台中第 5 步的精炼对象是**生成量规的 prompt**（PROMPT-R），采纳建议后精炼对应 prompt 模块并保存为新版本，下一轮用新版本重新生成量规；论文第 5 步的表述是对量规本身做精炼。二者目标一致——都作用于量规的生产过程，并在下一轮重新审核与验证。

## AND–OR 量规结构

一条量规（`QueryRubric`）包含两棵独立的树：

```
completion_rubric: [RubricNode, ...]                     # 完成量规，顶层项无权重
quality_rubric:    [{weight, node: RubricNode}, ...]     # 质量量规，顶层项带权重
```

节点结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 节点 id，形如 `node-xxxxxxxxxxxx`；全量规内唯一 |
| `type` | `leaf` / `group` | 叶子或分组 |
| `name` | string | 检查项描述；叶子使用可判定的正面断言 |
| `combinator` | `and` / `or` | 仅 group 有意义 |
| `children` | RubricNode[] | leaf 为空数组；group 非空 |
| `tags` | string[] | 能力项标签，仅 leaf 填写；group 恒为空 |

结构约束：

- **禁止单子节点 group**：遇到单个子节点时直接把子节点提升到父级。
- **AND 组**：同一实体或同一决策下需要同时满足的多个条件，如“冲突处理”=“识别了冲突”且“给出了调整方案”。
- **OR 组**：同一目标存在多条可接受路径，如“有冲突时调整日程”或“无冲突时创建提醒”。条件分支、成功/失败分支、用户确认/直接执行等场景都用 OR 组表达。
- **AND 组 vs 独立顶层项**：多个检查点评价“同一个东西”时用 AND 组聚合；分属不同执行环节或评价维度时拆为独立顶层项。不同交付物（文档、表格、图片等）各自独立成组。
- **权重**：质量顶层项的权重 = 重要性（1/2/3）× 难度（1/2），合法值仅 `{1, 2, 3, 4, 6}`，对应 `1×1`、`1×2`（或 `2×1`）、`3×1`、`2×2`、`3×2`。

## 完成与质量分离

这一原则对应七模块 prompt 第 2 节的“原则 4”，是评分可信度的基础：

| 维度 | 检查的问题 | 判定 | 示例 |
|---|---|---|---|
| 完成量规 | 目标达成了吗（what） | 二元 | “读取了本周日程安排” |
| 质量量规 | 执行过程有多好（how） | 连续 0–1 | “没有漏判任何时间重叠的会议，也没有误报不存在的冲突” |

典型错误：在完成量规里写“步骤清晰”（质量判断）；在质量量规里重复“正确读取了日程”（目标达成）。此外：

- 完成量规只判断“是否完成某个动作/行为/状态”，不评价结果质量；质量量规不重复检查目标是否达成。
- 质量叶子使用正面断言（勾选 = 达到该要求），不用疑问句或“若/当/如果”条件前缀；条件场景用 OR 组表达。
- 交付物“是否生成”属于完成量规；“生成的文件是否可用、可读”属于质量量规。

## 评分公式

### 完成度（二元）

对完成量规的每个顶层项求布尔值：叶子由勾选结果决定，OR 组为任一子节点为真，AND 组为全部子节点为真。**所有顶层项全部通过**才记任务完成：

```
completed = ∧_{i} top_item_i(leaf results)
complete_flag = 1 if completed else 0
```

### 质量分（论文口径 `paper`，默认）

叶子得分 `s_leaf ∈ {0, 1}`；组按节点类型与口径聚合；顶层按权重加权平均：

```
OR 组:   s = max(s_child)
AND 组:  s = 1  if 所有子节点 s == 1 else 0        # paper 口径
质量分:  score = Σ_i (w_i × s_i) / Σ_i w_i
```

其中 `w_i` 为质量量规第 i 个顶层项的权重。即论文中的权重加权平均形式：AND 组作为整体只在全部通过时得分，避免“部分完成”被平均成看似合格的分数。空组按 0.0 计（质量分）；完成量规中的空组按 `all([]) == True` 处理。

`legacy_mean` 为兼容早期实现的替代口径：OR 组仍取最大值，但 AND 组改为取子节点均值（部分得分），顶层仍加权平均。同一份勾选结果在两种口径下会得到不同分数，因此报告中必须注明口径；两个组件默认都使用 `paper`。

### 完成率与总分

- `completion_rate` = 通过的叶子数 / 叶子总数（ClawBench 实现按叶子统计，属于参考指标，不参与通过判定）。
- `score` = 质量分 `quality_score`（0–1）。
- 通过判定：`complete_flag == 1`；无该字段的旧数据回退 `score >= 0.75`（见 [评测流程](evaluation.zh-CN.md)）。

## 指标与终止判定

### 一致性指标

以“人工偏好的 gold 分数”与“量规评分（评分者均值）”为两条序列：

| 指标 | 定义 | 作用 |
|---|---|---|
| Pearson r | 线性相关系数 | 是否保持人类偏好的排序 |
| Spearman ρ | 秩相关系数 | 排序一致性的稳健补充 |
| QWK | 二次加权 Kappa：分数离散到 5 级后计算等级一致性 | 绝对评分是否与人类一致 |
| Alignment / Composite | `0.8 × Pearson + 0.2 × QWK` | 综合验收指标 |
| 逐 query 偏差 | 评分者均值 − gold（按 query） | 定位异常样本 |

Pearson 权重更高（0.8），因为模型比较最终依赖排序；QWK 捕捉绝对评分的等级一致性，避免“排序正确但分数不连贯”的量规被接受。一次批量至少需要 2 条已评分量规才能计算相关系数；单条量规的轮次仍可直接用 RIFT 诊断走质量分支。

### 终止条件

论文口径：**Alignment 高于阈值 0.8 即接受量规**；低于阈值时把不一致归因后进入“建议/采纳/精炼”。

平台实现（`raf/rubric/optimizer.py` 的 `DEFAULT_THRESHOLDS`）在达到主目标的同时还检查收敛、预算与退化：

| 条件 | 阈值 | 含义 | 运行状态 |
|---|---|---|---|
| 达标 | Pearson ≥ 0.85 且 QWK ≥ 0.75 | 两个子指标同时达标即停止 | `converged` |
| 收敛 | 至少 3 个已评分轮次，且最近 2 次 Composite 改善均 < 0.02 | 继续迭代收益过小 | `converged` |
| 预算 | 轮次 ≥ 10 | 强制停止 | `stopped` |
| 退化 | 最新 Composite 比历史最佳低 0.05 以上 | 停止（不回退，由人工决定是否采用历史最佳版本） | `stopped` |

> 说明：论文的验收口径是 Alignment ≥ 0.8；平台优化工作台的 `check_stopping` 以 Pearson / QWK 的分项阈值作为“达标”的工程化实现（0.85 / 0.75），并把 Alignment（Composite）用于收敛与退化判断。两者都记录在代码中，引用具体数字时请注明出处。

## 七模块 Prompt 设计

生成 prompt 由 7 个模块按固定顺序拼接，每个模块可独立编辑、diff、克隆与版本化：

| 顺序 | 模块 | 定位 | 职责 |
|---|---|---|---|
| 1 | `role` | 角色定义 | 一句话锚定“量规设计专家”身份 |
| 2 | `structure` | 量规结构 | 完成/质量两树、AND/OR 规则、权重规则、叶子要求、拆分方法 |
| 3 | `principles` | 设计原则 | 针对 RIFT 失败模式反写的设计原则（客观可判定、原子化、自包含、目标-过程分离、意图全覆盖、行为导向、区分力、无冗余、交付物可用性） |
| 4 | `examples` | 示例 | 完整示例（如日程冲突处理、旅行行程）的分析思路 + JSON 输出 |
| 5 | `constraints` | 输出前自检清单 | 数据结构、命名、边界、标签、区分力等自检项 |
| 6 | `capabilities` | 能力项与标签 | 12 项能力列表，运行时替换 `{capabilities}` 占位符 |
| 7 | `output` | 输出要求 | 重申规范与输出格式（先分析思路，再输出 JSON） |

其他工程约束：

- 输出用严格 JSON Schema（`strict: true` + `$defs` + `additionalProperties: false`）约束：节点必须包含 `type/name/combinator/tags/children`，权重枚举 `[1,2,3,4,6]`。
- 生成流程：结构化输出 → 失败降级为 JSON 模式 → 再失败重试（最多 3 次）→ Pydantic 校验 → 规范化（折叠单子 group、去重、清空 group tags）→ 检查叶子 tags。
- 能力项列表：`raf/data/capabilities.txt`（中文，12 项）与 `raf/data/capabilities.en.txt`（英文，12 项）。

## Prompt 版本：v5.1 与 v5.10

| 版本 | 父版本 | 说明 |
|---|---|---|
| `v5.1` | `v5` | 微调 AND 组使用规则：明确 AND 组聚合同一实体/维度的多条件，不同环节的检查项拆为独立顶层项。版本记录中的迭代指标为 Pearson 0.65 / QWK 0.57 / Composite 0.634（50 条 query、3 位评分者）。**ClawBench 全部 121 个任务的量规均由该版本生成** |
| `v5.10` | `v5.9` | 最新版本，默认活跃版本；由 PROMPT-R 精炼多个模块（量规结构、设计原则、自检清单、输出要求）得到 |

- 版本文件：`raf/data/prompt_versions/v5.1.json`、`v5.10.json`；英文版为同名 `.en.json`（缺失时回退中文）。
- 每个版本记录包含 `version`、`parent_version`、`created_at`、`change_description`、可选的 `metrics_summary` 与 7 个模块文本。
- 活跃版本记录在 `raf/data/active_prompt_version.txt`（默认 `v5.10`），可在平台“Prompt 版本”页切换。

## RIFT 诊断与 PROMPT-R 迭代

### RIFT 失败模式

RIFT 把量规缺陷归为 8 种失败模式，分属三组效度：

| 分组 | 失败模式 | 含义 |
|---|---|---|
| 可靠性 | Subjective（主观） | 检查项依赖主观判断，不同评分者结论不一致 |
| 可靠性 | Non-Atomic（非原子） | 一个叶子捆绑多个条件 |
| 可靠性 | Ungrounded（无依据） | 检查项依赖轨迹中无法获得的外部信息 |
| 内容效度 | Misaligned（目标-过程混淆） | 完成与质量边界被打破 |
| 内容效度 | Missing Criteria（意图遗漏） | 用户意图未被覆盖 |
| 后果效度 | Hackable（可 hack） | 可通过非目标行为满足 |
| 后果效度 | Low Signal（低区分） | 对所有轨迹都同分，无区分力 |
| 后果效度 | Redundant（冗余） | 与其他检查项语义重复 |

诊断分两步：先对每条量规调用 LLM 逐树检测失败模式，再聚合诊断一次，把系统性问题归因到 prompt 模块并给出可执行的修改建议。

### 一轮优化循环

1. 创建运行：选择 query 集合、评分者（含 gold）与初始 prompt 版本。
2. 开始轮次：用当前 prompt 版本批量生成量规。
3. 人工质量初筛（整批一次判断）：`approved` 进入评分；`rejected` 跳过评分与指标，直接解锁 RIFT 诊断。
4. 提交评分：gold + 多位评分者逐条打分。
5. 计算指标：Pearson / QWK / Composite 与逐 query 偏差（不调 LLM）。
6. RIFT 诊断：逐量规检测 + 聚合诊断，输出归因到模块的建议。
7. 采纳与精炼：人工勾选建议 → LLM 逐模块精炼 → 保存为新 prompt 版本。
8. 中止判断：达标 / 收敛 / 预算 / 退化；未达标则用新版本进入下一轮。

轮次状态流转：`generating → generated / generate_error → (scored → metrics → analyzed) / rejected → refined`。初筛结论在进入评分或诊断后锁定；被否决的轮次没有指标，也不参与达标/收敛判断，但同样消耗轮次预算。运行状态由中止判定更新为 `converged`（达标/收敛）或 `stopped`（预算/退化），中止结果与所用阈值会随运行记录保存，可随时重新检查。

## 双语运行

| 资产 | 中文 | 英文 | 回退 |
|---|---|---|---|
| Prompt 版本 | `data/prompt_versions/<version>.json` | `data/prompt_versions/<version>.en.json` | 英文 → 中文 |
| 能力项列表 | `data/capabilities.txt` | `data/capabilities.en.txt` | 英文 → 中文 |
| 生成语言 | `RAF_LANG=zh`（默认） | `RAF_LANG=en` 或 `--lang en` | — |

量规记录生成时所用 prompt 资产的语言（`language` 字段），因此同一 prompt 版本的中文与英文产出可以在平台中共存。

## 实现位置

| 能力 | 代码 |
|---|---|
| 数据模型（节点/量规/审核） | `raf/rubric/models.py`、`raf/rubric/models_optim.py` |
| 评分（完成/质量，paper / legacy_mean） | `raf/rubric/scoring.py`（前端镜像 `raf/frontend/src/lib/scoring.ts`） |
| 一致性指标 | `raf/rubric/metrics.py` |
| Prompt 模块与版本管理 | `raf/rubric/prompt_modules.py`、`raf/data/prompt_versions/` |
| 单条/批量生成 | `raf/generate_rubric.py`、`raf/batch_generate.py` |
| PROMPT-R 优化编排 | `raf/rubric/optimizer.py` |
| RIFT 诊断 | `raf/rubric/diagnostics.py` |
| Prompt 精炼 | `raf/rubric/refiner.py` |
| REST API | `raf/rubric/routes.py` |
| 服务入口 | `raf/app.py`（端口 8081） |

## 相关文档

- [ClawBench 评测集](benchmark.zh-CN.md)
- [数据格式](data_format.zh-CN.md)
- [评测流程](evaluation.zh-CN.md)
- [raf/README.zh-CN.md](../raf/README.zh-CN.md)

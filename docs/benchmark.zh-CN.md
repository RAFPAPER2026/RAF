# ClawBench 评测集

ClawBench 是论文 **《RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents》** 配套发布的 Agent 评测集：**121 个长程个人助理任务**，全部来自真实 OpenClaw 使用场景，每个任务都带有经过 RAF 生成与一致性校验的 AND–OR 量规。所有任务均按量规人工评分或由裁判 agent 评分，不使用脚本规则自动打分。

本篇说明评测集的构成、分类、统计与约定；任务与结果字段见 [数据格式](data_format.zh-CN.md)，评测执行见 [评测流程](evaluation.zh-CN.md)。

## 概览

- **任务来源**：2026 年 3–7 月真实 OpenClaw 用户的 query，经筛选后保留 121 个可复现的长程任务。
- **初始环境**：每个任务附带一个初始环境快照 `init_env/`（文档、表格、日历、图片、压缩包等），评测时拷贝进隔离容器。
- **量规**：每个任务内嵌一棵 AND–OR 量规树（完成量规 + 质量量规），由 RAF 的 `v5.1` prompt 版本生成，并经过人工审核与对齐验证。
- **评分方式**：全部为 `verifier_type: "manual"`，即由人工或裁判 agent 按量规逐叶子判定；框架负责采集轨迹、交付物与评分记录。

## 关键统计

| 指标 | 数值 |
|---|---|
| 任务数 | 121 |
| 二元叶子总数 | 1,920 |
| 完成侧叶子 | 666 |
| 质量侧叶子 | 1,254 |
| 内部 AND/OR 组节点 | 533（AND 523、OR 10） |
| 每任务顶层项数（均值 / 范围） | 8.43 / 6–12 |
| 每任务叶子数（均值 / 范围） | 15.87 / 6–33 |
| 完成量规顶层项 | 每任务 2–4 个 |
| 质量量规顶层项 | 每任务 3–8 个（合计 657 个） |
| 质量顶层项权重取值 | 1、2、3、4、6（两层级：重要性 × 难度） |
| 量规 prompt 版本 | `v5.1`（全部 121 个任务） |

## 分类体系

每个任务带四个维度的标签：场景、能力、难度、环境复杂度。

### 场景（3 个主场景）

| 主场景 | English | 任务数 |
|---|---|---|
| 个人生活助手 | Personal Life Assistant | 46 |
| 学习与知识管理 | Learning and Knowledge Management | 44 |
| 基础办公与效率 | Basic Office and Productivity | 31 |

3 个主场景下分 13 个子场景：

| 子场景 | English | 任务数 |
|---|---|---|
| 会议协同 | Meeting Coordination | 8 |
| 知识沉淀 | Knowledge Capture | 10 |
| 流程自动化 | Process Automation | 10 |
| 创意生成 | Creative Generation | 6 |
| 数据分析 | Data Analysis | 2 |
| 财务咨询 | Financial Advisory | 17 |
| 日程规划 | Schedule Planning | 18 |
| 学习辅助 | Learning Assistance | 22 |
| 信息检索 | Information Retrieval | 2 |
| 资料获取 | Resource Acquisition | 10 |
| 文档处理 | Document Processing | 8 |
| 邮件管理 | Email Management | 3 |
| 出行建议 | Travel Planning | 5 |

### 能力（5 个父类，多标签）

| 父类 | English | 带该父类标签的任务数 | 示例能力项 |
|---|---|---|---|
| 工具调用 | Tool Calling | 101 | 工具使用、CLI 调用、API 调用、Skill 使用、环境配置 |
| 任务规划 | Task Planning | 52 | 任务分解、约束满足与调度、数值分析与推理 |
| 上下文管理 | Context Management | 42 | 长上下文理解、上下文压缩、长文档关键信息提取、状态跟踪 |
| 指令遵循 | Instruction Following | 24 | 指令遵从、内容约束与条件筛选 |
| 反思与修复 | Reflection & Repair | 21 | 异常识别、异常处理与修复、结果验证与自检 |

- 任务为**多标签**：一个任务可同时带多个能力项，因此上表计数不求和到 121。
- `taxonomy.json` 共定义 5 个父类、21 个叶子能力标签；任务配置中同时保留原始标签 `ability_category` 与规范 key `ability_category_canonical`（如 `plan.decompose`）。

### 难度与环境复杂度

| 维度 | 取值 | 任务数 |
|---|---|---|
| 难度 | Easy | 14 |
| 难度 | Medium | 58 |
| 难度 | Hard | 49 |
| 环境复杂度 | Simple | 14 |
| 环境复杂度 | Moderate | 63 |
| 环境复杂度 | Complex | 44 |

任务配置还包含 `timeout_seconds` 字段：91 个任务为 300 秒、25 个任务为 600 秒、4 个任务为 500 秒、1 个任务为 120 秒。

## 任务目录

```
clawbench/tasks/
└── <task_id>/
    ├── config.json        # 中文任务定义（prompt + 内嵌量规）
    ├── config.en.json     # 英文翻译（同 id、树结构、权重）
    └── init_env/          # 初始环境与输入文件（中文，不翻译）
        ├── ...            # 输入文件（Markdown/Office/PDF/ics/eml/图片…）
        ├── .skills/       # 可选：任务所需技能（不随仓库分发）
        ├── .preset/       # 可选：沙箱预设（挂载进容器）
        └── .scripts/      # 可选：初始化脚本（在宿主机执行）
```

- 目录名即任务 id（`config.id == 目录名`），也是 `rubric.query_id` 的取值。
- 任务目录中**没有** `verifier/` 脚本目录；评分统一由人工或裁判 agent 完成。
- 少数任务没有输入文件（`init_env_state = no_input`，共 24 个）。空目录不入 git，因此这些任务的 `init_env/` 可能为空或不存在。
- 输入文件保持中文，不做翻译；英文 `config.en.json` 的 prompt 中会出现中文文件名/路径，这是预期行为。
- 单个任务可用 `config.json` 顶层的 `openclaw_config_path` 覆盖整批共享的 `tasks/openclaw.json`，为它指定独立的沙箱模型配置。

## 初始环境

每个任务有一个初始环境快照，即普通目录树而不是不透明镜像：

- 97 个任务需要输入，共 **475 个输入文件、约 117 MB**；其余 24 个任务不需要输入文件（`init_env_state: "no_input"`），另有 6 个任务显式设置 `env_init_needed: false`。
- 文件格式包括 Markdown、文本、Word、Excel、PowerPoint、PDF、日历（`.ics`）、邮件（`.eml`）、CSV/JSON/JSONL、图片、HTML、ZIP 压缩包，以及少量音视频文件。
- 部分文件是为任务虚构合成的文档，部分使用公开文档作为真实输入；第三方文件版权归原作者，见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
- 评测时 `init_env/` 会拷贝进容器工作区（`.skills/`、`.preset/` 挂载、`.scripts/` 在宿主机执行），详见 [评测流程](evaluation.zh-CN.md)。

## 双语约定

| 文件 | 语言 | 说明 |
|---|---|---|
| `config.json` | 中文 | 权威任务定义，`language: "zh"` |
| `config.en.json` | 英文 | 翻译版，`language: "en"`；`config.en.json` 缺失时 `--lang en` 回退读取中文 |

英文版必须与中文版保持**结构一致**：

- 相同的 rubric 节点 id、`type`、`combinator`、树结构与权重序列；
- `prompt` 与 `rubric.query` 均为英文且两者完全一致；
- 能力标签使用英文能力项名称；`ability_category` 翻译为英文标签，`ability_category_canonical` 保持规范 key 不变；
- 输入文件与其中的中文文件名/路径保持原样。

## 脱敏说明

- 121 个任务均经过脱敏：移除个人身份信息（PII）、账号凭据、敏感内容，并对真实事件做虚构化改写。
- 任务输入中的第三方文件（如公开论文、公开报告）保留原版权，仅作为任务输入随仓库分发；详见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
- 仓库测试会对配置中的敏感标识做回归检查，避免敏感信息被重新带入。

## 技能需求

部分任务需要预置技能才能完成：

| 技能 | 需要的任务数 | 用途 |
|---|---|---|
| `baidu-search` | 12 | 联网检索 |
| `rapid-ocr-reader` | 1 | 图片文字识别 |

- 技能**不随仓库分发**。使用前把技能目录放到对应任务的 `init_env/.skills/<skill>/` 下；评测时该目录会挂载到容器 `/root/.openclaw/workspace/skills`。
- 每个任务的技能需求记录在 `metadata/tasks.jsonl` 的 `required_skills` 字段，任务配置中对应 `skills` 字段。
- 共 13 个任务带技能需求；其余任务无需预置技能。

## 元数据

### `metadata/taxonomy.json`

中英对照的分类词表，包含：`scenes`（3 个主场景）、`sub_scenes`（13 个子场景）、`competency_parents`（5 个能力父类）、`competencies`（能力标签及父子关系）、`capabilities`（12 个 rubric 能力项）、`skills`（2 个技能）、`difficulty`、`complexity`。

### `metadata/tasks.jsonl`

每行一个任务的索引，共 121 行，字段如下：

| 字段 | 说明 |
|---|---|
| `id` / `name` | 任务 id 与展示名 |
| `primary_scenario` / `secondary_scenario` | 主场景 / 子场景 |
| `ability_category` / `ability_category_canonical` | 原始能力标签 / 规范能力 key（多标签数组） |
| `difficulty` / `environment_complexity` | 难度 / 环境复杂度 |
| `timeout_seconds` | 任务预期时长（秒） |
| `required_skills` | 所需技能列表（如 `["baidu-search"]`） |
| `init_env_state` | `has_input` 或 `no_input` |
| `init_env_files` / `init_env_bytes` | 输入文件数 / 总字节数 |
| `rubric` | 量规摘要：`prompt_version`、`completion_leaves`、`quality_leaves`、`top_entries`、`and_groups`、`or_groups` |

## 任务设计参考

ClawBench 的部分任务场景参考或改编自公开的 Agent 评测项目：

- **Claw-Eval** — <https://github.com/claw-eval/claw-eval>
- **PinchBench** — <https://github.com/pinchbench/skill>

以上仅为任务设计参考与致谢；这些项目的代码与数据不随本仓库分发。

## 评测协议速览

- 所有任务的 `verifier_type` 恒为 `manual`：不附带规则验证或 LLM 校验器的自动打分；任务通过人工打分页或裁判 agent 评分。
- 每个 run 的 `complete_flag` 由量规完成度决定（全部完成量规顶层项通过为 1）；`--runs k` 时任务级取 **pass^k**（k 轮全部通过才为 1），并记录 `pass_at_1` 与 `pass_rate_over_runs`。
- 质量分按评分时选择的 `paper` / `legacy_mean` 口径计算，并随 run 持久化（`scoring_mode`）。
- 旧数据没有 `complete_flag` 时，默认按 `score ≥ 0.75` 判定通过（`clawbench/configs/trace_config.json`）。

## 许可与引用

- 评测数据、标注与 prompt 资产：**CC BY 4.0**（[`LICENSE-DATA`](../LICENSE-DATA)）；
- 评测代码：**Apache-2.0**（[`LICENSE`](../LICENSE)）；
- `init_env/` 中第三方输入文件的版权与许可归原作者，见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)；
- 仓库地址：<https://github.com/RAFPAPER2026/RAF>，引用元数据见 [`CITATION.cff`](../CITATION.cff)。

## 相关文档

- [数据格式](data_format.zh-CN.md)
- [评测流程](evaluation.zh-CN.md)
- [RAF 框架](framework.zh-CN.md)
- [clawbench/README.zh-CN.md](../clawbench/README.zh-CN.md)

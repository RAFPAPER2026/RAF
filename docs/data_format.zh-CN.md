# 数据格式

本仓库涉及三类数据：ClawBench **任务定义**（`clawbench/tasks/`）、任务**元数据**（`clawbench/metadata/`）与评测**结果**（`clawbench/results/`）。本篇给出字段级说明；评测集构成见 [ClawBench 评测集](benchmark.zh-CN.md)。

## 约定

- 所有 JSON 文件均为 UTF-8 编码，中文内容不转义。
- 路径相对于仓库根目录；`<task_id>` 指任务目录名。
- 中文任务定义 `config.json` 是权威版本，英文 `config.en.json` 是其翻译，两者共享同一套量规节点 id 与树结构。
- 输入文件（`init_env/`）保持中文，不翻译。

## 目录总览

```
clawbench/
├── tasks/<task_id>/
│   ├── config.json          # 中文任务定义（含 rubric）
│   ├── config.en.json       # 英文任务定义（含 rubric 翻译）
│   └── init_env/            # 初始环境与输入文件（可选 .skills/、.preset/、.scripts/）
├── metadata/
│   ├── taxonomy.json        # 中英对照的分类词表
│   └── tasks.jsonl          # 每行一个任务的索引
└── results/                 # 评测输出（不入库）
```

## 任务配置 `config.json`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 任务 id，等于目录名 |
| `name` | string | 是 | 任务展示名（`5g-test-meetings-extraction` 这类短标题） |
| `version` | string | 是 | 任务版本，当前均为 `"1.0"` |
| `primary_scenario` | string | 是 | 主场景（中文，3 个之一） |
| `secondary_scenario` | string | 是 | 子场景（中文，13 个之一） |
| `ability_category` | string[] | 是 | 原始能力标签（中文，可多值） |
| `ability_category_canonical` | string[] | 是 | 规范能力 key（如 `plan.decompose`、`tool.cli`） |
| `difficulty` | string | 是 | 难度：`easy` / `medium` / `hard` |
| `environment_complexity` | string | 是 | 环境复杂度：`simple` / `moderate` / `complex` |
| `timeout_seconds` | number | 是 | 任务预期时长（秒，120–600） |
| `verifier_type` | string | 是 | 固定为 `"manual"`（人工或裁判 agent 评分） |
| `env_init_needed` | bool | 是 | 是否需要初始环境（数据集描述字段） |
| `skills` | string[] | 是 | 任务所需技能（如 `["baidu-search"]`），无则空数组 |
| `language` | string | 是 | 任务定义语言：`zh` |
| `prompt` | string | 是 | 发给 Agent 的用户请求（中文） |
| `rubric` | object | 是 | 内嵌量规，见下节 |
| `note` | string | 否 | 任务一句话说明（72 个任务有） |
| `env_description` | string | 否 | 初始环境说明（21 个任务有） |
| `openclaw_config_path` | string | 否 | 单任务模型配置覆盖：指向另一份 `openclaw.json`，优先级高于 tasks 目录顶层的共享配置 |

约束：`prompt` 与 `rubric.query` 必须完全一致；`id` 必须等于目录名；`ability_category` 与 `ability_category_canonical` 一一对应。

## 量规 `rubric`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 量规 id，形如 `rubric-xxxxxxxxxxxx` |
| `query` | string | 生成量规所用 query，等于任务 `prompt` |
| `query_id` | string | 关联的 query id，等于任务 id |
| `prompt_version` | string | 生成量规使用的 prompt 版本，ClawBench 全部为 `v5.1` |
| `language` | string | 量规语言：`zh` / `en` |
| `completion_rubric` | RubricNode[] | 完成量规顶层项（无权重） |
| `quality_rubric` | WeightedItem[] | 质量量规顶层项（带权重） |

### 节点 `RubricNode`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 节点 id，形如 `node-xxxxxxxxxxxx`；全局唯一（跨 121 个任务也不重复） |
| `type` | string | `leaf`（叶子）或 `group`（分组） |
| `name` | string | 检查项描述；叶子为可判定的正面断言 |
| `combinator` | string | `and` 或 `or`；仅 `group` 有意义 |
| `children` | RubricNode[] | 子节点；`leaf` 恒为空数组 |
| `tags` | string[] | 能力项标签；仅 `leaf` 填写，`group` 恒为空数组 |

校验规则（`clawbench/src/rubric/models.py`）：

- `group` 节点必须至少有一个子节点，且 `tags` 必须为空；
- `leaf` 节点不允许有子节点，且应填写 `tags`；
- 禁止单子节点 group（数据已规范化）。

### 质量顶层项 `WeightedItem`

| 字段 | 类型 | 说明 |
|---|---|---|
| `weight` | number | 权重，取值 `1` / `2` / `3` / `4` / `6`（重要性 × 难度） |
| `node` | RubricNode | 该顶层项的根节点（leaf 或 group） |

示例（结构示意，非完整任务）：

```json
{
  "id": "rubric-d8ee193a6b54",
  "query": "……",
  "query_id": "5g_test_meetings_extraction",
  "prompt_version": "v5.1",
  "language": "zh",
  "completion_rubric": [
    {
      "id": "node-c8bcddc65366",
      "type": "leaf",
      "name": "正确读取了桌面 calendar_extraction_task/work_calendar_2023.ics 日历文件",
      "combinator": "and",
      "children": [],
      "tags": ["意图理解", "工具使用", "事实准确性"]
    }
  ],
  "quality_rubric": [
    {
      "weight": 6.0,
      "node": {
        "id": "node-abf6a0235392",
        "type": "group",
        "name": "会议筛选判断质量",
        "combinator": "and",
        "children": [
          {
            "id": "node-61848d4fdd13",
            "type": "leaf",
            "name": "准确识别了会议标题和描述字段中的关键词匹配条件",
            "combinator": "and",
            "children": [],
            "tags": ["意图理解", "条件判断", "信息筛选"]
          }
        ],
        "tags": []
      }
    }
  ]
}
```

> 上例为节省篇幅只保留了组内的一个子节点；实际数据中不存在单子节点 group。

## 英文配置 `config.en.json`

字段与 `config.json` 一一对应，差异如下：

| 项 | 中文版 | 英文版 |
|---|---|---|
| 文件名 | `config.json` | `config.en.json` |
| `language` | `zh` | `en` |
| `name`、`prompt`、`note`、`env_description` | 中文 | 英文 |
| `primary_scenario` / `secondary_scenario` | 中文标签 | 英文标签（取自 `taxonomy.json`） |
| `ability_category` | 中文标签 | 英文标签 |
| `ability_category_canonical` | 规范 key | **保持不变** |
| `rubric.query` / 节点 `name` / 叶子 `tags` | 中文 | 英文 |
| `rubric.language` | `zh` | `en` |
| rubric 节点 `id`、`type`、`combinator`、`children`、权重 | — | **与中文版完全一致** |
| `skills`、`difficulty`、`environment_complexity`、`timeout_seconds` | — | 保持不变 |

英文 prompt 中保留中文文件名/路径字面量（输入文件不翻译）。

加载器会保留未知的额外键（`extra="allow"`），因此后续新增的注记字段不会破坏加载。

## 初始环境 `init_env/`

```
clawbench/tasks/<task_id>/
├── config.json          # 中文任务定义
├── config.en.json       # 英文翻译
└── init_env/            # 评测时初始化到 agent 桌面
    ├── <输入文件>        # Markdown / Office / PDF / ics / eml / 图片 …
    ├── .skills/         # 可选：外部技能，挂载进沙箱
    ├── .preset/         # 可选：沙箱预设，挂载进沙箱
    └── .scripts/        # 可选：初始化脚本，在宿主机执行
```

| 特殊目录 | 评测时的处理 |
|---|---|
| `init_env/.skills/<name>/` | 挂载到沙箱 `/root/.openclaw/workspace/skills`（不拷贝进 agent 工作区） |
| `init_env/.preset/` | 挂载到沙箱 `/root/.openclaw/workspace/presets` |
| `init_env/.scripts/` | 不拷贝；`.sh` 用 `bash`、`.py` 用 `python3` 在宿主机的 worker 目录中执行，之后才发送任务 |

没有输入文件的任务（24 个，`init_env_state: "no_input"`）`init_env/` 为空或不存在；空目录不被 git 跟踪，检出后为空即表示“无输入文件”。

## 元数据

### `metadata/taxonomy.json`

| 键 | 内容 |
|---|---|
| `version` | 词表版本（`"1.0"`） |
| `scenes` | 3 个主场景：中文标签 → `{id, en}` |
| `sub_scenes` | 13 个子场景：中文标签 → 英文标签 |
| `competency_parents` | 5 个能力父类：key → `{zh, en}` |
| `competencies` | 21 个叶子能力：规范 key → `{parent, zh, en}` |
| `capabilities` | 12 个 rubric 能力项：中文 → 英文 |
| `skills` | 2 个技能（`baidu-search`、`rapid-ocr-reader`）的说明 |
| `difficulty` / `complexity` | 难度 / 环境复杂度的中英对照 |

### `metadata/tasks.jsonl`

每行一个 JSON 对象，共 121 行：

| 字段 | 说明 |
|---|---|
| `id` / `name` | 任务 id / 展示名 |
| `primary_scenario` / `secondary_scenario` | 主场景 / 子场景（中文） |
| `ability_category` / `ability_category_canonical` | 原始能力标签 / 规范 key |
| `difficulty` / `environment_complexity` | 难度 / 环境复杂度 |
| `timeout_seconds` | 任务预期时长 |
| `required_skills` | 所需技能列表 |
| `init_env_state` | `has_input`（97 个）或 `no_input`（24 个） |
| `init_env_files` / `init_env_bytes` | 输入文件数 / 总字节数 |
| `rubric` | `{prompt_version, completion_leaves, quality_leaves, top_entries, and_groups, or_groups}` |

## 结果目录

一次评测（一个模型、一批任务）对应 `results/` 下的一个模型目录：

```
results/
├── .name_mapping.json                 # 人工打分页盲评别名映射（运行时生成，不入库）
└── {tasks目录名PascalCase}[EN]_{model}_{YYYYmmdd_HHMMSS}_{uuid8}/
    ├── result.json                    # 模型级汇总
    ├── eval.log                       # 评测日志
    ├── analysis_report.xlsx           # analyze 后生成
    └── <task_id>/
        └── run_1/                     # 多轮时为 run_1 … run_k
            ├── score.json             # 指标 + 评分记录
            ├── sessions.json          # Agent 执行轨迹（会话事件）
            ├── workspace/             # Agent 交付物
            └── verifier/
                └── judge/             # 裁判 agent 产物（可选）
```

- 结果目录命名：`{tasks 目录名 PascalCase}[EN]_{model}_{timestamp}_{uuid8}`。中文评测为 `Tasks_<model>_...`，英文评测为 `TasksEN_<model>_...`；未指定 `--model-name` 时省略中间段。
- 多轮评测（`--runs k`）为每个任务生成 `run_1` … `run_k` 子目录。
- 旧布局：部分历史结果把 `score.json`、`sessions.json`、`workspace/` 直接放在 `<task_id>/` 下，读取时视为 `run_1`（`src/runs.py` 兼容）。
- `average` 不是磁盘目录，而是读取时对多个 run 求平均的**视图**（`run_id="average"`）。
- `results/` 整体不入库，只保留 `.gitkeep`。

## `score.json`

单个 run 的评分与指标记录，关键字段：

### 运行与指标（框架写入）

| 字段 | 说明 |
|---|---|
| `task_name` | 任务 id |
| `status` | `completed` / `failed` |
| `error` | 失败原因（成功时为 `null`） |
| `start_time` / `end_time` / `duration` | 起止时间与耗时（秒） |
| `retry_count` | 重试次数 |
| `input_tokens` / `output_tokens` | token 用量（无 usage 时按文本长度估算） |
| `input_cost` / `output_cost` | 成本（默认价格表为空，记 0；可在 `configs/model_prices.json` 配置） |
| `tool_calls` / `tool_success` / `tool_failed` | 工具调用数与成功/失败数 |
| `tool_success_rate` / `tool_names` | 工具成功率与工具名列表 |
| `error_recoveries` / `error_recovery_rate` | 失败后恢复次数与比例 |
| `api_calls` | 模型调用轮数 |
| `task_time` | 工具执行总时长（秒，取自工具结果） |

### tree 格式评分（人工或裁判 agent 写入）

| 字段 | 说明 |
|---|---|
| `rubric_results` | `{leaf_id: bool}`：逐叶子判定结果 |
| `rubric_format` | `"tree"` |
| `completion` | `{completed, total, passed, item_results}`；`total`/`passed` 按叶子统计 |
| `quality_score` | 质量分（0–1） |
| `score` | 总分，等于 `quality_score` |
| `completion_rate` | 通过叶子数 / 叶子总数 |
| `complete_flag` | `1` 全部完成量规顶层项通过；`0` 否则；未评分时通常缺失（人工也可显式写 `null`） |
| `scoring_mode` | `paper` / `legacy_mean`（评分时使用的口径） |
| `manual_score` | 人工（或采纳后的裁判）总分 |
| `manual_comment` / `manual_scored_at` / `manual_scored_by` | 评语 / 时间 / 评分者（`agent` 表示采纳裁判结果） |
| `adopted_agent_timestamp` | 采纳的裁判结果时间戳（采纳时写入） |
| `manual_feedback` | 人工反馈标记：`1` 好 / `-1` 差 / `0` 未标 |
| `doubtful` | 是否存疑（裁判 `needs_human_review=true` 时置 `true`，只增不减） |
| `trace_quality` | `{avg_score, dimensions}`，4 个过程维度的可选评分，仅用于分析 |
| `agent_review` | 裁判 agent 原始结构化输出，见 [评测流程](evaluation.zh-CN.md) |

### 兼容字段（旧数据）

| 字段 | 说明 |
|---|---|
| `dimension_scores` | 旧版过程维度分，读取时合成为 `trace_quality` |
| `rubric_scores` | 旧版 flat 评分项列表 `[{completion, quality_score, item_score}]` |
| `score` / `manual_score` | 旧版直接评分；无 tree 数据时按 `score >= 0.75` 回退判定通过 |

## `sessions.json`

Agent 执行轨迹：

```json
{
  "container": "openclaw_worker_1a2b3c4d",
  "sessions": [
    { "type": "message", "timestamp": "…", "message": { "role": "user", "content": ["…"] } }
  ]
}
```

- `sessions[]` 保存 OpenClaw 会话转录的原始记录：从容器内 `~/.openclaw/agents/main/sessions/` 的挂载目录读取**最新的** `*.jsonl` 文件（忽略 `*.trajectory.jsonl`），逐行解析后原样写入，不裁剪字段。
- 若 gateway 响应里直接带会话事件，优先使用响应；否则回退读取转录挂载。
- 消费方（指标统计、裁判 agent、报告页）读取时做形状归一：`toolCall` → `tool_use`、`toolResult` → `tool_result`、`usage` → token 等。

## `workspace/`

Agent 在容器 `/root/Desktop` 下产生的交付物拷贝（排除 `.openclaw_agents` 转录挂载点）。它是人工打分页与裁判 agent 检查的主要证据，也是报告页预览的对象。

## `verifier/`

预留给校验/评分产物，实际上存放裁判 agent 的输出：

| 路径 | 内容 |
|---|---|
| `verifier/judge/agent_judge.jsonl` | 裁判 agent 的 SDK 消息逐条转录（每条附加 `type` 与 `timestamp`） |
| `verifier/judge/exceptions.md` | 可选：评分过程遇到异常（缺轨迹、环境问题等）时的说明 |
| `verifier/judge/proof/` | 可选：裁判收集的证据（截图、抽取页面等） |

任务目录本身**不带** `verifier/`；它只在结果目录中出现。

## `result.json`

模型目录下的汇总文件，由 `src/runs.py::build_per_run_result_json` 生成：

```json
{
  "summary": {
    "total_tasks": 121,
    "completed_tasks": 121,
    "failed_tasks": 0,
    "total_duration": 0.0,
    "overall_score": 0.0
  },
  "tasks": [
    {
      "task_name": "5g_test_meetings_extraction",
      "runs": {
        "run_1": {"score": 0.0, "manual_score": null, "status": "completed", "duration": 0.0}
      },
      "score": 0.0,
      "manual_score": null,
      "status": "completed",
      "duration": 0.0
    }
  ]
}
```

- `summary.total_duration` 为各 run 时长之和；`overall_score` 为各任务 per-run 分数均值再对任务取均值。
- 每个任务顶层的 `score` / `manual_score` / `status` / `duration` 镜像 `run_1`，仅用于兼容旧读取方。
- 多轮平均视图还包含 `run_count`、`pass_rate_over_runs`、`pass_at_1`、`pass_k`、`mean_score`、`runs[]` 等字段（由读取方按需计算，不落盘到 `result.json`）。

## 多轮（`average`）视图

`--runs k` 会为每个任务生成 `run_1 … run_k`。报告页与分析器默认使用一个**虚拟的 `average` run**（不是磁盘目录，用 `--run-id average` 访问）：

- 数值指标（score、duration、tokens、成本、工具计数、API 调用、completion_rate）对可用 run 取均值；
- `quality_score` 仅当每个 run 都有数值时才平均；`manual_score` 对非 `None` 值取均值；
- `status` 仅当严格多数 run 完成时为 `completed`（k=2 平局判失败）；
- `pass_rate_over_runs` = 通过 run 数 / k；`pass_at_1` = 至少一个 run 通过；`pass_k` = 全部 run 通过；`complete_flag` = 1 当且仅当 `pass_k`；
- `runs[]` 保留每个 run 的 score、status、标记与 `rubric_results` 供钻取。

损坏或缺失的 run 会被跳过；没有 `run_*` 子目录的旧版单 run 结果（`score.json` 直接放在 case 目录）按 `run_1` 解析。

## 兼容性

- **量规格式**：tree（当前）与 flat（旧版）自动识别（`src/rubric/compat.py`）。裁判 agent 只支持 tree；旧 flat 数据可用 `src/rubric/migrate.py` 的 `flat_rubric_to_tree` 做有损迁移（不还原旧分数）。
- **评分格式**：tree（存在 `rubric_results`）、flat（存在 `rubric_scores` 列表）与 legacy（只有 `manual_score`/`score`）三类，读取时统一归一（`apply_legacy_compat`）。
- **通过判定**：`complete_flag == 1`；旧数据缺失该键或为 `null` 时回退 `score >= pass_threshold`（默认 0.75，`clawbench/configs/trace_config.json`）。

## 校验约束

仓库测试（`clawbench/tests/test_dataset.py`）对数据强制以下不变量：

- 任务数 = 121，目录名与 `id` 一致且唯一；
- `verifier_type == "manual"`、`language == "zh"`（中文版）、`prompt == rubric.query`、`rubric.query_id == id`；
- 任务目录没有 `verifier/` 子目录，且不含旧字段（`rule_verify`、`llm_verify`、`both_verify`、`prompt_old`、`scenario_category`、`ability_category_v2`）；
- 全量叶子 1,920（完成 666 / 质量 1,254）、组节点 533、每任务顶层项均值 8.43、权重取值 ⊆ `{1, 2, 3, 4, 6}`；
- 全部节点 id 全局唯一（1,920 个叶子 + 533 个组节点，共 2,453 个节点无重复），group 无 tags，leaf 无 children；
- 英文配置存在时与中文配置的结构签名、权重序列、顶层项数完全一致，且 `language == "en"`；
- `tasks.jsonl` 121 行，`init_env_state` 与实际输入文件一致；带技能任务共 13 个；
- 配置中不含敏感标识（PII、凭据等）。

## 不入库的内容

| 路径 | 原因 |
|---|---|
| `clawbench/results/*` | 评测产物（体积与数据敏感性） |
| `clawbench/workspace/` | 容器 worker 目录（运行时） |
| `clawbench/tasks/openclaw.json` | 含模型端点与 API key |
| `clawbench/configs/claude_settings.json` | 含裁判凭据 |
| `clawbench/configs/model_prices.json` | 本机价格配置（可选） |
| `clawbench/docker/openclaw/dist/*.tar` | 镜像体积过大 |
| 两个前端 `dist/`、`node_modules/` | 构建产物 |
| `raf/data/llm_config.json`、`raf/data/optimization_runs/` | 含密钥 / 运行时数据 |
| `raf/frontend/dist/` | RAF 前端构建产物 |

## 相关文档

- [ClawBench 评测集](benchmark.zh-CN.md)
- [评测流程](evaluation.zh-CN.md)

# Data format

This page is the field-level reference for the data shipped and produced by the repository. For the rubric methodology, see [Framework (RAF)](framework.md); for the benchmark composition, see [Benchmark (ClawBench)](benchmark.md).

## Repository data map

| Path | What it is |
|---|---|
| `clawbench/tasks/<task_id>/config.json` | Chinese task definition (canonical). |
| `clawbench/tasks/<task_id>/config.en.json` | English translation of the same task. |
| `clawbench/tasks/<task_id>/init_env/` | Initial environment (input files and optional special directories). |
| `clawbench/metadata/taxonomy.json` | Bilingual taxonomy: scenes, sub-scenes, competencies, capabilities, skills, difficulty, complexity. |
| `clawbench/metadata/tasks.jsonl` | One JSON record per task: taxonomy labels plus rubric statistics and initial-environment summary. |
| `clawbench/configs/trace_config.json` | Process-evaluation dimensions and the legacy pass threshold. |
| `raf/data/` | Prompt versions, capability lists, and the platform's file-based JSON storage (rubrics, queries, reviews). |

Runtime directories (`clawbench/results/`, `clawbench/workspace/`, `raf/data/llm_config.json`, `raf/data/optimization_runs/`, frontend `dist/` folders, `clawbench/tasks/openclaw.json`, `clawbench/configs/claude_settings.json`) are gitignored and never distributed.

## Task definition: `config.json` / `config.en.json`

Both files are JSON objects with the same schema. `runner.py`/`TaskConfig` loads `config.json` for `--lang zh` (default) and `config.en.json` for `--lang en`, falling back to Chinese when the English file is absent.

| Field | Type | Description |
|---|---|---|
| `id` | string | Task id. Must equal the task directory name. |
| `name` | string | Human-readable task name. |
| `version` | string | Task definition version (currently `"1.0"`). |
| `primary_scenario` | string | One of the 3 primary scenes, in Chinese (see `taxonomy.json` for the English label). |
| `secondary_scenario` | string | One of the 13 sub-scenes, in Chinese. |
| `ability_category` | string[] | Original human-readable competency labels (Chinese, may be compound, e.g. `"任务规划-任务分解"`). |
| `ability_category_canonical` | string[] | Canonical competency ids from `taxonomy.json` (e.g. `plan.decompose`, `tool.cli`). Multi-label. |
| `difficulty` | `"easy"` \| `"medium"` \| `"hard"` | Task difficulty. |
| `environment_complexity` | `"simple"` \| `"moderate"` \| `"complex"` | Complexity of the initial environment. |
| `timeout_seconds` | integer | Per-run execution time budget (120–600 s across the benchmark). |
| `verifier_type` | string | Always `"manual"`. The task model rejects other values: ClawBench tasks are scored by a human or a judge agent. |
| `env_init_needed` | boolean | Task-level flag indicating that the environment needs initialization; the runner always copies `init_env/` when it is present. |
| `skills` | string[] | External skills required by the task (e.g. `["baidu-search"]`); empty for most tasks. |
| `language` | `"zh"` \| `"en"` | Language of this definition file. |
| `prompt` | string | The user query sent to the agent. **Must be identical to `rubric.query`** (modulo surrounding whitespace). |
| `rubric` | object | The evaluation rubric — see below. |
| `note` | string (optional) | Short human note about the task (72/121 tasks). |
| `env_description` | string (optional) | Description of the initial environment (21/121 tasks). |
| `openclaw_config_path` | string (optional, top level) | Per-task sandbox model configuration file; overrides the shared `tasks/openclaw.json` for this task only. |

Trimmed example:

```json
{
  "id": "calendar_conflict_detection",
  "name": "calendar_conflict_detection",
  "version": "1.0",
  "primary_scenario": "个人生活助手",
  "secondary_scenario": "日程规划",
  "ability_category": ["任务规划-任务分解", "工具调用-CLI 调用"],
  "ability_category_canonical": ["plan.decompose", "tool.cli"],
  "difficulty": "hard",
  "environment_complexity": "complex",
  "timeout_seconds": 300,
  "verifier_type": "manual",
  "env_init_needed": true,
  "skills": [],
  "language": "zh",
  "prompt": "…the user query…",
  "rubric": { "id": "rubric-…", "query": "…the user query…", "query_id": "calendar_conflict_detection", "prompt_version": "v5.1", "language": "zh", "completion_rubric": ["…"], "quality_rubric": ["…"] },
  "note": "…"
}
```

Unknown extra keys are preserved by the loader, so future-compatible annotations do not break loading.

## Rubric schema

The `rubric` object is a `QueryRubric`:

| Field | Type | Description |
|---|---|---|
| `id` | string | Rubric id (e.g. `rubric-dac1f7c9da78`). |
| `query` | string | The query the rubric was generated for; must match the task `prompt`. |
| `query_id` | string | Query identifier; for benchmark tasks it equals the task id. |
| `prompt_version` | string | RAF prompt version used to generate the rubric (`v5.1` for all 121 benchmark rubrics). |
| `language` | `"zh"` \| `"en"` | Language of the rubric text. |
| `completion_rubric` | `RubricNode[]` | The completion tree (no weights). |
| `quality_rubric` | `WeightedItem[]` | The quality tree; each top-level item carries a weight. |

### `RubricNode`

| Field | Type | Description |
|---|---|---|
| `id` | string | Node id, globally unique within a task (e.g. `node-d1d0c0dfab0f`). |
| `type` | `"leaf"` \| `"group"` | Leaf = checkable criterion; group = container. |
| `name` | string | Leaf: one atomic binary criterion (positive statement). Group: the goal/dimension it aggregates. |
| `combinator` | `"and"` \| `"or"` | Meaningful only for groups; leaves keep `"and"` as a placeholder. |
| `children` | `RubricNode[]` | Group children (one or more); leaves must have `[]`. |
| `tags` | string[] | Leaf only: capability tags drawn from the 12-item capability list. Group nodes must carry `[]`. |

### `WeightedItem`

| Field | Type | Description |
|---|---|---|
| `weight` | number | Importance × difficulty weight; valid values `{1, 2, 3, 4, 6}` (model range 1.0–6.0). |
| `node` | `RubricNode` | Root of the quality item. |

Example:

```json
{
  "id": "rubric-dac1f7c9da78",
  "query": "…",
  "query_id": "calendar_conflict_detection",
  "prompt_version": "v5.1",
  "language": "zh",
  "completion_rubric": [
    { "id": "node-7c9ac4d249a4", "type": "group", "name": "冲突检测结果已正确生成", "combinator": "and", "children": [
      { "id": "node-eca2536abde5", "type": "leaf", "name": "正确识别了…", "combinator": "and", "children": [], "tags": ["条件判断", "逻辑推理"] }
    ], "tags": [] }
  ],
  "quality_rubric": [
    { "weight": 4.0, "node": { "id": "node-4e2df6d6b595", "type": "group", "name": "冲突判定质量", "combinator": "and", "children": ["…"], "tags": [] } }
  ]
}
```

### Invariants

A valid task rubric satisfies all of the following (checked by `clawbench/tests/test_dataset.py`):

- `config.id == config.rubric.query_id == directory name`.
- `config.prompt.strip() == config.rubric.query.strip()`.
- Every node id in both trees is unique within the task.
- Groups have at least one child; leaves have no children and carry capability tags; groups never carry tags.
- Quality weights belong to `{1, 2, 3, 4, 6}`; completion top-level items have no weight.
- The English config preserves the same ids, weights and tree structure (node signatures and weight list must match the Chinese config).

How the trees are scored (all-pass completion, AND/OR quality aggregation, weighting) is specified in [Framework (RAF)](framework.md#3-scoring).

## Language conventions

| Rule | Detail |
|---|---|
| Canonical language is Chinese | `config.json` is the source of truth; `config.en.json` is a translation. |
| Same identifiers | Both files share the task `id`, rubric `query_id`, all node ids, `prompt_version`, tree structure and weights. Text fields (`name`, `prompt`, rubric node names, `note`, `env_description`, ability labels) are translated. |
| Query must match its own language file | In `config.en.json`, `prompt` equals `rubric.query` in **English**; the same holds inside `config.json` in Chinese. |
| Chinese file names are preserved | English prompts keep Chinese file names and paths verbatim (e.g. `workspace/<中文文件名>.docx`), because the input files are not translated. |
| Fallback | If `config.en.json` is missing, `--lang en` falls back to `config.json`. |
| Leakage guard | De-identified text is checked for known sensitive identifiers; do not reintroduce real names, credentials or addresses in translations. |

The same convention applies to RAF's prompt assets (`<version>.json` / `<version>.en.json`, `capabilities.txt` / `capabilities.en.txt`), with English falling back to Chinese.

## Initial environment layout

```
clawbench/tasks/<task_id>/
├── config.json          # Chinese definition
├── config.en.json       # English translation
└── init_env/            # copied into the agent's desktop (except special dirs)
    ├── <input files>    # Markdown / Office / PDF / ics / eml / images / …
    ├── .skills/         # optional: external skills, mounted into the sandbox
    ├── .preset/         # optional: sandbox presets, mounted into the sandbox
    └── .scripts/        # optional: setup scripts, executed on the host
```

| Special directory | Handling during evaluation |
|---|---|
| `init_env/.skills/<name>/` | Mounted to `/root/.openclaw/workspace/skills` in the sandbox (not copied into the agent workspace). |
| `init_env/.preset/` | Mounted to `/root/.openclaw/workspace/presets`. |
| `init_env/.scripts/` | Not copied; each `.sh` runs with `bash` and each `.py` with `python3` on the host, inside the worker directory, before the request is sent. |

Tasks with no input files have an empty or absent `init_env/` (24 tasks; `init_env_state: "no_input"`). Empty directories are not tracked by git, so an empty `init_env/` after checkout simply means "no input files". External skills are not bundled with the repository — see [Benchmark](benchmark.md#skills).

## Metadata files

### `metadata/taxonomy.json`

Bilingual vocabulary shared by all tasks:

| Key | Content |
|---|---|
| `version` | Taxonomy version (`"1.0"`). |
| `scenes` | Primary scene → `{id, en}`. |
| `sub_scenes` | Sub-scene Chinese → English. |
| `competency_parents` | Parent id → `{zh, en}` (5 parents). |
| `competencies` | Leaf competency id → `{parent, zh, en}` (21 entries). |
| `capabilities` | The 12 rubric-leaf capability tags, Chinese → English. |
| `skills` | Required external skills, Chinese/English descriptions and placement hints. |
| `difficulty` / `complexity` | Chinese label → English label. |

### `metadata/tasks.jsonl`

One JSON record per task (121 lines), useful for filtering, statistics and dataset validation:

| Field | Description |
|---|---|
| `id`, `name` | Task id and display name. |
| `primary_scenario`, `secondary_scenario` | Chinese taxonomy labels (join with `taxonomy.json` for English). |
| `ability_category`, `ability_category_canonical` | Raw and canonical competency labels. |
| `difficulty`, `environment_complexity` | Labels as in the config. |
| `timeout_seconds` | Per-run timeout. |
| `required_skills` | Same as the config `skills` array. |
| `init_env_state` | `"has_input"` or `"no_input"`. |
| `init_env_files`, `init_env_bytes` | Number and total size of input files. |
| `rubric.prompt_version` | RAF prompt version used to generate the rubric. |
| `rubric.completion_leaves`, `rubric.quality_leaves` | Leaf counts per tree. |
| `rubric.top_entries` | `len(completion_rubric) + len(quality_rubric)`. |
| `rubric.and_groups`, `rubric.or_groups` | Group counts. |

## Run and result directories

`main.py eval` / `main.py run` create one result directory per evaluation:

```
clawbench/results/
└── <tasks_dir>[_EN]_<model>_<timestamp>_<uuid8>/   # e.g. Tasks_my-model_20261107_120000_1a2b3c4d
    ├── eval.log                     # full evaluation log
    ├── result.json                  # model-level summary (rebuilt from score.json files)
    └── <task_id>/
        └── run_<n>/                 # one subdirectory per repeat (--runs)
            ├── score.json           # run metrics + scoring record
            ├── sessions.json        # collected session trace
            ├── workspace/           # deliverables produced by the agent
            └── verifier/judge/      # judge-agent artifacts (when judge scoring is used)
```

The directory name is built as `{PascalCase(tasks dir name)}{EN if --lang en}_{model_name}_{YYYYmmdd_HHMMSS}_{uuid8}`; the model segment is omitted when `--model-name` is not given.

### `score.json`

Written by the runner for run metadata and metrics; augmented in place by scoring tools (manual scorer, judge agent). The file is a superset: unallocated scores are simply absent/`null`.

| Group | Fields |
|---|---|
| Run lifecycle | `task_name`, `status` (`completed`/`failed`), `error`, `start_time`, `end_time`, `duration` (seconds), `retry_count` |
| Token/cost metrics | `input_tokens`, `output_tokens`, `input_cost`, `output_cost`, `api_calls` |
| Tool metrics | `tool_calls`, `tool_success`, `tool_failed`, `tool_success_rate`, `tool_names`, `error_recoveries`, `error_recovery_rate`, `task_time` |
| Rubric scoring (tree) | `rubric_format: "tree"`, `rubric_results` (`{leaf_id: bool}`), `completion` (object: `completed`, `total`, `passed`, `item_results`), `quality_score`, `score` (= quality score), `completion_rate`, `complete_flag` (0/1), `scoring_mode` (`paper`/`legacy_mean`) |
| Manual scoring | `manual_score`, `manual_comment`, `manual_scored_at`, `manual_scored_by`, `adopted_agent_timestamp` (when a judge result was adopted) |
| Process quality | `trace_quality: {avg_score, dimensions: {task_understanding, task_planning, tool_usage, reflection_recovery}}` |
| Judge agent | `agent_review: {rubric_format, rubric_results: {leaf_id: {passed, reasoning}}, confidence, trace_quality?, time_analysis?, info_fidelity_analysis?, needs_human_review, review_notes?, timestamp}` |
| Markers | `doubtful` (set to true when a review flags the case for human attention), `manual_feedback` (`1` good / `-1` bad / `0` unset) |
| Legacy (read-only) | `dimension_scores`, `rubric_scores` — older formats that analysis tools can still read and normalise |

### `sessions.json`

```json
{
  "container": "openclaw_worker_1a2b3c4d",
  "sessions": [ { "type": "message", "timestamp": "…", "message": { "role": "user", "content": [ … ] } }, "…" ]
}
```

`sessions[]` stores the raw OpenClaw session transcript records (JSONL lines read unchanged from the sandbox's `~/.openclaw/agents/main/sessions/` mount, excluding `*.trajectory.jsonl`). Consumers normalise them at read time: tool calls (`toolCall` blocks become `tool_use`), tool results, token usage, and message timestamps. If the gateway response carries session events, those are used first; otherwise the transcript mount is read.

### `workspace/`

A copy of the agent's `/root/Desktop` directory after execution, i.e. the deliverables the agent produced. The session-transcript mount (`.openclaw_agents`) is excluded. This directory is the primary evidence used by the manual scorer and the judge agent.

### `verifier/`

Reserved for validation/scoring artifacts. In practice it holds the judge agent's output:

| Path | Content |
|---|---|
| `verifier/judge/agent_judge.jsonl` | One JSON line per judge-agent SDK message, with `type` and `timestamp` added. |
| `verifier/judge/exceptions.md` | Optional notes when the judge encountered anomalies (missing trace, environment problems, etc.). |
| `verifier/judge/proof/` | Optional evidence the judge collected (screenshots, extracted pages, …). |

Task directories do **not** ship a `verifier/` directory; it appears only inside results when relevant.

### `result.json`

Model-level summary rebuilt after each task finishes (and after every score update):

| Field | Content |
|---|---|
| `summary.total_tasks` / `completed_tasks` / `failed_tasks` | Counts of tasks in the result directory. |
| `summary.total_duration` | Sum of per-run durations. |
| `summary.overall_score` | Mean of per-case mean scores. |
| `tasks[]` | One entry per task: `task_name`, `runs` (`{run_id: {score, manual_score, status, duration}}`) and mirrored run-1 fields (`score`, `manual_score`, `status`, `duration`). |

### Multi-run ("average") view

`--runs k` creates `run_1 … run_k`. The report page and analyzer default to a virtual `average` run that is computed on the fly (it is **not** a directory on disk):

- Numeric metrics (score, duration, tokens, costs, tool counters, API calls, completion rate) are averaged over the available runs.
- `quality_score` is averaged only when every run has a numeric value; `manual_score` is the mean over non-`None` values.
- `status` is `completed` only when a strict majority of runs completed.
- `pass_rate_over_runs` = passed runs / k; `pass_at_1` = at least one run passed; `pass_k` = all runs passed; `complete_flag` = 1 iff `pass_k`.
- `runs[]` retains each run's score, status, flags and `rubric_results` for drill-down.

Legacy single-run result directories that store `score.json` directly in the case directory are still supported and are resolved as `run_1`.

## Compatibility and validator expectations

- **Rubric formats:** tree (current) and flat (legacy) axes are auto-detected (`src/rubric/compat.py`). The judge agent is tree-only; flat data can be converted with the opt-in migration helper `flat_rubric_to_tree`, which is lossy and does not reproduce the old scores.
- **Score formats:** tree (`rubric_results` present), flat (`rubric_scores` list) and legacy (only `manual_score`/`score`) are detected and normalised on read.
- **Dataset tests** (`cd clawbench && uv run pytest`) assert: 121 tasks; 1,920 leaves split 666/1,254; 533 groups; quality weights ⊆ `{1,2,3,4,6}`; mean 8.43 top-level entries; per-task initial-environment state matching `tasks.jsonl`; no legacy verifier fields; no known sensitive identifiers; structural parity of Chinese and English configs (the English test skips while translations are absent).
- **Scoring tests** assert the `paper`/`legacy_mean` semantics and that the selected mode is recorded in the result.
- **Git hygiene:** never commit `clawbench/results/*`, `clawbench/workspace/`, sandbox tarballs, `tasks/openclaw.json`, `configs/claude_settings.json`, `configs/model_prices.json`, `raf/data/llm_config.json`, `raf/data/optimization_runs/` or built frontend bundles.

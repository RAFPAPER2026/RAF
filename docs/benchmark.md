# ClawBench benchmark

**ClawBench** is a benchmark of **121 long-horizon personal-assistant tasks**, built from real OpenClaw usage rather than synthetic task descriptions. Every task ships with its initial environment and a verified AND–OR rubric, and every task is evaluated as a rubric-based manual judgement — by a human annotator or by a judge agent.

- **How to run it:** [evaluation](evaluation.md).
- **Exact field schemas:** [data format](data_format.md).
- **The rubric methodology behind the task rubrics:** [framework (RAF)](framework.md).

## What a task is

Each task is one directory under `clawbench/tasks/<task_id>/` containing:

| Part | Description |
|---|---|
| `config.json` | The Chinese task definition: user query, taxonomy labels, timeout, skills, initial-environment flags, and the rubric (two AND–OR trees). |
| `config.en.json` | The English translation of the same definition; identical rubric node ids, tree structure and weights. |
| `init_env/` | The initial environment given to the agent (input files, or empty for tasks that need no input). |
| `openclaw_config_path` (optional) | A top-level config key used only when a task needs its own sandbox model configuration instead of the shared `tasks/openclaw.json`. |

At evaluation time the harness starts an isolated sandbox container per task, copies `init_env/` (except the special `.skills/`, `.preset/` and `.scripts/` directories) into the agent's desktop workspace, sends the task prompt to the sandbox gateway, and collects the session trace plus the resulting workspace for scoring.

The on-disk layout is flat — one self-contained directory per task:

```
clawbench/
├── tasks/
│   ├── <task_id>/
│   │   ├── config.json          # Chinese definition + rubric
│   │   ├── config.en.json       # English translation
│   │   └── init_env/            # input files (copied to the agent's desktop)
│   │       ├── <documents, spreadsheets, calendars, images, …>
│   │       ├── .skills/         # optional; external skills (not distributed)
│   │       ├── .preset/         # optional; sandbox presets
│   │       └── .scripts/        # optional; host-executed setup scripts
│   └── … 121 task directories
└── metadata/
    ├── taxonomy.json            # bilingual labels
    └── tasks.jsonl              # one index record per task
```

## Composition

### Scenarios

| Primary scene | Tasks |
|---|---|
| Personal Life Assistant | 46 |
| Learning and Knowledge Management | 44 |
| Basic Office and Productivity | 31 |

The 121 tasks are split into 13 sub-scenes:

| Sub-scene | Tasks |
|---|---|
| Learning Assistance | 22 |
| Schedule Planning | 18 |
| Financial Advisory | 17 |
| Knowledge Capture | 10 |
| Process Automation | 10 |
| Resource Acquisition | 10 |
| Meeting Coordination | 8 |
| Document Processing | 8 |
| Creative Generation | 6 |
| Travel Planning | 5 |
| Email Management | 3 |
| Data Analysis | 2 |
| Information Retrieval | 2 |

### Capabilities

Each task carries multi-label competency annotations. There are **5 competency parents** and **21 leaf competencies** (e.g. `tool.cli`, `plan.decompose`, `context.long`, `instruction.follow`, `reflection.repair`):

| Competency parent | Tasks tagged (multi-label) |
|---|---|
| Tool Calling | 101 |
| Task Planning | 52 |
| Context Management | 42 |
| Instruction Following | 24 |
| Reflection & Repair | 21 |

In addition, every rubric leaf carries one or more **capability tags** from a fixed 12-item list (intent understanding, conditional judgement, logical reasoning, temporal reasoning, retrieval strategy, information filtering, tool usage, context retention, exception handling, factual accuracy, general knowledge, communication). The bilingual taxonomy — scenes, sub-scenes, competency parents, competencies, capabilities, skills, difficulty and complexity labels — is in [`clawbench/metadata/taxonomy.json`](../clawbench/metadata/taxonomy.json).

### Difficulty and environment complexity

| Difficulty | Tasks | Environment complexity | Tasks |
|---|---|---|---|
| Easy | 14 | Simple | 14 |
| Medium | 58 | Moderate | 63 |
| Hard | 49 | Complex | 44 |

Task timeouts: 300 s for 91 tasks, 600 s for 25, 500 s for 4 and 120 s for 1.

## Rubric statistics

All 121 task rubrics were generated with RAF prompt version **v5.1** and include both a completion tree and a quality tree.

| Statistic | Value |
|---|---|
| Binary leaf criteria (total) | 1,920 |
| — completion leaves | 666 |
| — quality leaves | 1,254 |
| Internal AND/OR group nodes | 533 (523 AND, 10 OR) |
| Top-level rubric entries per task | mean 8.43 (min 6, max 12) |
| — completion top-level items | 2–4 per task |
| — quality top-level items | 3–8 per task |
| Leaves per task | mean 15.87 (min 6, max 33) |
| Quality weights | drawn from `{1, 2, 3, 4, 6}` |

Weights encode importance × difficulty: `1 = 1×1`, `2 = 1×2 or 2×1`, `3 = 3×1`, `4 = 2×2`, `6 = 3×2`. Completion items are unweighted and aggregated by all-pass. A rubric leaf is a binary, self-contained, objectively judgeable criterion; quality top-level items combine leaves through AND/OR groups and a weight.

## Initial environments

Each task has one initial environment snapshot. It is an ordinary directory tree, not an opaque image:

- **475 input files**, about **117 MB** in total, across the 97 tasks that need input. The 24 remaining tasks need no input files (`init_env_state: "no_input"` in the task index); six tasks explicitly set `env_init_needed: false`.
- Formats include Markdown, text, Word, Excel, PowerPoint, PDF, calendar (`.ics`), email (`.eml`), CSV/JSON/JSONL, images, HTML, ZIP archives and a few audio/video files.
- Some files are fictional documents synthesized for the task; others are publicly available documents used as realistic inputs. Their copyright remains with the original authors — see [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

**The input files are in Chinese and are not translated.** `config.en.json` translates the task instructions and rubric criteria, while file names and file contents deliberately remain in their original language — English prompts mention the Chinese file names verbatim. A model evaluated with `--lang en` therefore still has to read Chinese inputs.

## Skills

Most tasks are solvable with the tools built into the sandbox. Thirteen tasks additionally require an external skill:

| Skill | Tasks | Examples |
|---|---|---|
| `baidu-search` (web search) | 12 | `paper_search_1`, `paper_search_2` |
| `rapid-ocr-reader` (image OCR) | 1 | `image_2_word_1` |

Skills are **not distributed** in this repository. To run those tasks, place the skill implementation under the task's initial environment:

```
clawbench/tasks/<task_id>/init_env/.skills/<skill-name>/
```

The harness mounts `init_env/.skills/` into the container (and does not copy it into the workspace), so the agent can discover and use the skill. The special directories `.skills/`, `.preset/` and `.scripts/` are excluded from the workspace copy; `.scripts/` scripts are executed on the host during environment initialization. `metadata/tasks.jsonl` records `required_skills` for every task, so you can filter out tasks whose skills you do not have.

## Bilingual task definitions

| File | Language | Role |
|---|---|---|
| `config.json` | Chinese | Canonical definition; `language: "zh"`. |
| `config.en.json` | English | Translation used with `--lang en`; `language: "en"`. |

The translation preserves the rubric node ids, weights, tree structure and the task id, so scores from Chinese and English runs remain comparable in structure. If an English file is missing, the harness falls back to the Chinese definition. See [data format](data_format.md) for the exact conventions.

## De-identification

The benchmark was built from real usage data, then filtered and de-identified before release:

- Personal identifiers, credentials, secrets, private addresses and sensitive content were removed from task definitions, rubrics, metadata and input files.
- Where a document was needed as a fixture, its content was rewritten or replaced with fictional data (names, accounts, companies, files).
- The dataset integrity tests assert that known sensitive identifiers do not appear in the released configs.
- Third-party material that remains in `init_env/` is included as a benchmark fixture only and keeps its original license.

## Task design references

Some ClawBench task scenarios are inspired by, or adapted from, publicly available agent-evaluation projects:

- **Claw-Eval** — <https://github.com/claw-eval/claw-eval>
- **PinchBench** — <https://github.com/pinchbench/skill>

These references acknowledge task-design inspiration; the projects' code and data are not redistributed in this repository.

## Evaluation protocol at a glance

- `verifier_type` is `manual` for every task: no rule-based or LLM-verifier auto-scoring is shipped. A task is scored through the manual scoring UI, or by the judge agent acting as an annotator.
- A run's `complete_flag` is the binary completion result from the rubric (all completion top-level items pass). With `--runs k`, the case-level flag becomes **pass^k** (1 only if all k runs pass); `pass_at_1` and `pass_rate_over_runs` are also recorded.
- Quality scores follow the `paper` or `legacy_mean` aggregation selected at scoring time and are stored per run.
- The default pass threshold for legacy data without `complete_flag` is `score ≥ 0.75` (`clawbench/configs/trace_config.json`).

[Evaluation](evaluation.md) explains the container lifecycle, scoring UIs, judge agent and reporting tools in detail.

## License and citation

- Benchmark data, annotations and prompt assets: **CC BY 4.0** ([`LICENSE-DATA`](../LICENSE-DATA)).
- Evaluation code: **Apache-2.0** ([`LICENSE`](../LICENSE)).
- Third-party fixtures: see [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).
- Repository: <https://github.com/RAFPAPER2026/RAF> · citation metadata: [`CITATION.cff`](../CITATION.cff).

If you use ClawBench, please cite the RAF paper:

> RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents. ICLR 2027 submission. <https://github.com/RAFPAPER2026/RAF>

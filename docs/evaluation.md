# Evaluation

ClawBench is evaluated with an isolated Docker sandbox per task: the harness starts an OpenClaw container, initialises the task environment, sends the task prompt to the container's gateway, and collects the session trace and workspace. **Scoring is deliberately not automated by the runner** — every task is scored by a human annotator (manual scoring UI) or by a judge agent (Claude Agent SDK), then analysed and reported.

This page describes that pipeline end to end. Field-level definitions of the artifacts are in [Data format](data_format.md); the setup commands are in the [ClawBench README](../clawbench/README.md).

## Pipeline overview

```
configs/trace_config.json
        │
        ▼
tasks/<id>/config.json + init_env/ ──▶ container manager ──▶ OpenClaw sandbox
        │                                    (10800)              │
        │                                                        ├─ /root/Desktop  ◀── worker dir
        │                                                        ├─ /root/.openclaw/openclaw.json
        │                                                        └─ gateway :18789
        ▼                                                         │
main.py run/eval ── start container, copy init_env,                 │
                    POST /v1/chat/completions ──────────────────────┘
        │
        ├─ collect sessions.json + workspace/ ──▶ score.json (metrics only)
        │
        ├─ human scoring UI (5002)  ─┐
        └─ judge agent (main.py judge)┴─▶ score.json (rubric_results, completion, complete_flag, …)
                                                   │
                                    result.json + analysis_report.xlsx + report page (4999)
```

## Sandbox containers

The container manager is a small FastAPI service (`src/container_manager.py`, default port 10800) that wraps the Docker CLI.

```bash
cd clawbench
uv run python src/container_manager.py            # --port, --workers-dir, --log-dir are optional
```

### Manager API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check used by the evaluator. |
| `POST /start` | Start one sandbox container; returns `{container_name, port, worker_path, config_path}`. |
| `GET /containers`, `GET /containers/{name}` | List / inspect managed containers and their Docker status. |
| `POST /stop`, `DELETE /containers/{name}` | Stop / stop-and-remove a container. |

Starting a container does the following:

- Generates a container name `openclaw_worker_<8 hex>`, creates a worker directory under `clawbench/workspace/openclaw_workers/<name>/`, and maps it to `/root/Desktop` in the container.
- Allocates a random free host port in `50000–65535` and maps it to the container's gateway port `18789`.
- Runs `docker run -d … <image> bash -l -c "openclaw gateway"` with the selected image (`OPENCLAW_IMAGE`, default `openclaw:base.4.2`).
- Injects `OPENCLAW_GATEWAY_TOKEN` as an environment variable, and optionally the `OPENCLAW_PROXY` HTTP/HTTPS proxy variables.

### Mounts

| Host path | Container path | Purpose |
|---|---|---|
| worker directory | `/root/Desktop` | Agent workspace; collected as the result `workspace/`. |
| `tasks/openclaw.json` or a per-task `openclaw_config_path` | `/root/.openclaw/openclaw.json` | Model provider/agent configuration. |
| task `init_env/.skills/` | `/root/.openclaw/workspace/skills` | Optional external skills. |
| task `init_env/.preset/` | `/root/.openclaw/workspace/presets` | Optional sandbox presets. |
| `<worker>/.openclaw_agents/` | `/root/.openclaw/agents` | Session transcript mount used to collect `sessions.json`. |

Model configuration resolution order: a task-level `openclaw_config_path` key, then the shared `tasks/openclaw.json`, then the placeholder provider baked into the image (gateway starts, model calls fail). See the [ClawBench README](../clawbench/README.md) for creating `tasks/openclaw.json` from `openclaw.example.json`.

### Gateway request

The evaluator waits for the container gateway to answer `GET /healthz` (up to 120 s), then sends the task prompt to the OpenAI-compatible endpoint:

```
POST http://127.0.0.1:<mapped-port>/v1/chat/completions
Authorization: Bearer <OPENCLAW_GATEWAY_TOKEN>

{"model": "openclaw", "messages": [{"role": "user", "content": "<task prompt>"}], "stream": false}
```

The request timeout is 1800 s by default. The container and worker directory are always cleaned up when the run finishes (the workspace is copied to the result directory first).

## Per-task lifecycle

`TaskRunner.run_task` (src/runner.py) implements one task/run:

| Step | What happens | Artifacts |
|---|---|---|
| 1 | Start a sandbox container via the manager (mounts above). | — |
| 2 | Initialise the environment: copy everything from `init_env/` **except** `.skills/`, `.preset/`, `.scripts/` into the worker directory. Run each `.scripts/*.sh` with `bash` and each `.scripts/*.py` with `python3` on the host, inside the worker directory. | worker `/root/Desktop` content |
| 3 | Wait for the gateway (`GET /healthz`, ≤120 s) and send the task prompt. | — |
| 4 | Extract session events from the gateway response, else read the mounted transcript (`~/.openclaw/agents/main/sessions/*.jsonl`, newest file, ignoring `*.trajectory.jsonl`). | `sessions.json` |
| 5 | Copy the worker directory (the agent's deliverables, minus the `.openclaw_agents` mount) into the result directory. | `workspace/` |
| 6 | Compute run metrics from the events: tokens, cost, API calls, tool calls/success/failure, error recoveries, tool durations. | `score.json` |
| 7 | Clean up the container and worker directory; record status/error/start/end/duration. | `score.json` |

Logging goes to the console and to `{result_dir}/eval.log`, including per-job progress and validation results.

## Running an evaluation

```bash
cd clawbench

# evaluate + analyze
uv run python main.py run --tasks-dir tasks --model-name my-model --workers 4

# evaluate only
uv run python main.py eval --tasks-dir tasks --result-base-dir results --workers 4

# k repeats per task for pass@k
uv run python main.py run --tasks-dir tasks --model-name my-model --runs 3 --workers 4
```

| Flag | Default | Meaning |
|---|---|---|
| `--tasks-dir` | required | Directory whose subdirectories each contain a `config.json`. |
| `--result-base-dir` | `results` | Base directory for the new result directory. |
| `--workers` | 4 | Number of parallel jobs (tasks × runs). |
| `--model-name` | none | Included in the result directory name; use the name of the model under test. |
| `--runs` | 1 | Repeats per task, for pass@k. |
| `--retries` | 0 | Extra attempts for a task/run whose status is not `completed`. |
| `--lang` | `zh` | `zh` reads `config.json`; `en` reads `config.en.json` (falling back to Chinese). |
| `--quality-aggregation` | `paper` | Quality scoring mode (`paper` or `legacy_mean`). |

Evaluation writes `clawbench/results/<tasks>[_EN]_<model>_<timestamp>_<uuid8>/`; tasks are executed with a thread pool (one container per job). Failed tasks can be re-run into a new run directory without redoing the completed ones:

```bash
cd clawbench
uv run python main.py rerun --result-dir results/<model_dir> --tasks-dir tasks
```

## Scoring a run

The runner never writes a rubric score, `manual_score` or `complete_flag`. Two scorers are provided.

### Manual scoring UI

```bash
cd clawbench
uv run python manual_scorer/main.py --result-dir results --tasks-dir tasks --port 5002
```

Open <http://127.0.0.1:5002>. The UI lets an annotator:

- Browse models and tasks, filter by run, inspect the task prompt and config.
- Read the session events and preview/download workspace files, including Office documents and images.
- Score tree rubrics leaf by leaf: tick/untick each criterion and see completion and weighted quality recompute live. The quality aggregation mode can be switched in the form (`paper` / `legacy_mean`).
- Save the derived score, edit the completion flag, mark manual feedback (good/bad), flag a case as doubtful, and record the four process-quality dimensions.
- Trigger single-task or batch judge-agent evaluation and adopt judge results.

| Flag | Default | Meaning |
|---|---|---|
| `--result-dir` | `results` | Directory containing model result directories. |
| `--tasks-dir` | none | Task definitions (needed to render rubrics and prompts). |
| `--port` | 5002 | HTTP port. |
| `--host` | `127.0.0.1` | Bind address; the default keeps the UI local-only. |
| `--agent-config` | `configs/agent_scorer_config.json` | Judge-agent configuration. |
| `--lang` | `zh` | Task-definition language. |
| `--quality-aggregation` | `paper` | Default quality scoring mode for the form and the server-side recompute. |

### Scoring API

The UI is a thin client over a REST API (`manual_scorer/api.py`); the same endpoints can be scripted:

| Endpoint | Purpose |
|---|---|
| `GET /api/models`, `GET /api/model/{model_id}/tasks`, `.../runs`, `.../task/{task_name}` | Enumerate results and task details. |
| `POST /api/model/{model_id}/task/{task_name}/score` | Save a score. Accepts tree input `{rubric_results: {leaf_id: bool}}` (derived server-side), flat input `{rubric_scores: [...]}`, or direct `{score}` / `{dimensions}`. |
| `PATCH .../complete-flag`, `.../manual-feedback`, `.../doubtful` | Update the corresponding markers. |
| `POST .../trace-quality` | Save the four process-quality dimensions. |
| `GET .../workspace`, `.../workspace/files`, `.../workspace/file` | Browse/download the collected workspace (path-traversal protected). |
| `POST .../agent-eval`, `POST /api/model/{model_id}/batch-agent-eval`, `.../adopt` | Run the judge agent for one task / a batch, and adopt its output. |

For tree scoring the server validates that every leaf id in the task rubric is present, recomputes completion and quality with the scoring module, and stores `rubric_results`, `completion`, `quality_score`, `score`, `completion_rate`, `complete_flag`, `scoring_mode`, `manual_score`, the comment, the timestamp and (optionally) the annotator name.

### Scoring modes

| Mode | Completion | Quality leaf | OR group | AND group | Top level |
|---|---|---|---|---|---|
| `paper` (default) | all top-level completion items pass | 1 / 0 | max | 1 only if all children score 1, else 0 | weighted mean |
| `legacy_mean` | same | 1 / 0 | max | mean of children | weighted mean |

The mode is selected by `--quality-aggregation` (CLI) or `CLAWBENCH_SCORING_MODE` (environment variable) and is recorded per scored run in `score.json` (`scoring_mode`).

Implementation locations:

| Implementation | File |
|---|---|
| ClawBench authoritative Python logic | `clawbench/src/rubric/scoring.py` |
| ClawBench report-page TypeScript mirror | `clawbench/web/src/rubric/scoring.ts` |
| ClawBench manual-scorer TypeScript mirror | `clawbench/manual_scorer/web/src/lib/scoring.ts` |
| RAF Python logic | `raf/rubric/scoring.py` |
| RAF frontend TypeScript mirror | `raf/frontend/src/lib/scoring.ts` |

The report page re-derives scores for a concrete run from the stored `rubric_results` on the server side (Python) so that what you see matches the stored scoring record; keep the mirrors in sync when changing the formula.

### Judge agent

The judge agent is an LLM annotator built on the **Claude Agent SDK**. It reads the task definition, the execution trace and the workspace, judges every rubric leaf, and writes a structured review. It only supports tree rubrics and only considers `verifier_type: "manual"` tasks.

#### Credentials and configuration

| File | Purpose |
|---|---|
| `clawbench/configs/agent_scorer_config.json` | Judge-agent parameters: `settings_path`, `model`, `max_turns` (120), `timeout_seconds` (1800), `permission_mode` (`acceptEdits`). |
| `clawbench/configs/claude_settings.example.json` | Template for the SDK settings file; copy it to `clawbench/configs/claude_settings.json` (gitignored) and fill in an Anthropic-compatible endpoint, token and model. |

```bash
cd clawbench
cp configs/claude_settings.example.json configs/claude_settings.json
# edit env.ANTHROPIC_BASE_URL, env.ANTHROPIC_AUTH_TOKEN, env.ANTHROPIC_MODEL
```

The settings file is passed to the SDK as the `settings` option; `model: null` means "use the SDK/model from the settings".

#### Workflow

1. **Eligibility** — the task must be `manual`, its rubric must be tree format, the run must exist, and (with `--skip-existing`) the case must not already carry an `agent_review`.
2. **Prompts** — the system prompt is assembled from six hot-loadable sections (`role`, `workflow`, `deliverables`, `exceptions`, `rules`, `output_format`, plus `trace_quality` when process evaluation is requested) and is language-selected (`--lang`). The user prompt contains the original task query, task/result directory layouts, a pre-extracted trace metadata summary (authoritative execution date, tool-call sequence), and the completion/quality rubric trees rendered as indented text.
3. **Evaluation** — the agent runs with the result directory as its working directory (task directory added as an extra readable root), reads `sessions.json` and `workspace/`, and returns structured output.
4. **Validation** — `rubric_results` must cover every leaf id exactly once with a boolean `passed` and a non-empty `reasoning` string; `confidence` must be in `[0, 1]`; the analysis fields must be non-empty; `needs_human_review` must be boolean. Invalid output fails the task (it is retried once).
5. **Persistence** — the SDK transcript is written to `verifier/judge/agent_judge.jsonl`; the review is stored in `score.json` as `agent_review`; `needs_human_review: true` sets the top-level `doubtful` marker (one-way: it is never cleared automatically).
6. **Adoption (optional)** — with `--adopt`, the leaf verdicts are scored with the authoritative scoring module and written as a normal manual score: `manual_score`, `rubric_results`, `completion`, `quality_score`, `completion_rate`, `complete_flag`, a per-leaf comment, `manual_scored_by: "agent"` and `adopted_agent_timestamp`. Process-quality dimensions are saved too when `--evaluate-trace` was used.

#### Output schema

| Field | Type | Required | Meaning |
|---|---|---|---|
| `rubric_results` | `{leaf_id: {passed: bool, reasoning: string}}` | yes | Verdict and evidence for every leaf in the completion and quality trees. |
| `confidence` | number `[0,1]` | yes | How confident the judge is in the overall assessment. |
| `time_analysis` | string | yes | Per-leaf time-window analysis (execution date is anchored to the first user message, UTC+8). |
| `info_fidelity_analysis` | string | yes | Per-leaf fidelity analysis for information obtained from search/browsing. |
| `needs_human_review` | boolean | yes | Whether the case should be reviewed by a human. |
| `review_notes` | string | yes | Why human review is needed (or "no need"). |
| `trace_quality` | `{task_understanding, task_planning, tool_usage, reflection_recovery}` | only with `--evaluate-trace` | Process-quality dimensions, each `0.0 / 0.25 / 0.5 / 0.75 / 1.0`. |

#### CLI

```bash
cd clawbench

# judge one model directory, then adopt results as manual scores
uv run python main.py judge --result-dir results/<model_dir> --tasks-dir tasks --adopt

# also evaluate process quality; skip cases that already have a review
uv run python main.py judge --result-dir results/<model_dir> --tasks-dir tasks \
  --evaluate-trace --skip-existing --workers 4 --run-id run_1
```

| Flag | Default | Meaning |
|---|---|---|
| `--result-dir` | required | A model result directory (or a parent directory containing several). |
| `--tasks-dir` | required | Task definitions. |
| `--run-id` | `run_1` | Which run to score. |
| `--workers` | 1 | Judge concurrency. |
| `--evaluate-trace` | off | Also produce the four process-quality dimensions. |
| `--skip-existing` | off | Skip cases that already have an `agent_review`. |
| `--adopt` | off | Write judge results as manual scores (`manual_score` + derived rubric fields). |
| `--agent-config` | `configs/agent_scorer_config.json` | Judge-agent configuration file. |

## Passing, `complete_flag` and pass@k

- **Per run:** `complete_flag = 1` iff every top-level completion item passes. This is the authoritative pass criterion throughout the harness (report page, analyzer, Excel export).
- **Legacy fallback:** data without `complete_flag` (or with an explicit `null`) falls back to `score >= pass_threshold`, default `0.75` from `configs/trace_config.json`.
- **Multi-run:** with `--runs k`, the per-case average view reports `pass_at_1` (at least one run passed), `pass_rate_over_runs` (fraction of passed runs) and `pass_k` (all runs passed). The average `complete_flag` is **pass^k**, so a task only counts as solved when all k runs pass. The averaged case `status` is `completed` only when a strict majority of runs completed.
- **New runs:** re-running failed tasks through `rerun` appends `run_<max+1>`, so pass@k views include it automatically.

## Analysis and reporting

### Excel report

```bash
cd clawbench
uv run python main.py analyze --result-dir results/<model_dir> --tasks-dir tasks
```

`analyze` writes `{result_dir}/analysis_report.xlsx` with three sheets (default `--run-id average`):

| Sheet | Content |
|---|---|
| `任务汇总` (Task summary) | One row per task: completion flag, score, duration, tokens/cost, tool/API statistics, taxonomy labels, plus config-derived columns when `--tasks-dir` is given. |
| `分类统计` (Category statistics) | Task count, average score and pass rate per category across primary/secondary scenario, ability, difficulty and complexity. |
| `总体统计` (Overall statistics) | Overall metrics: totals, average score, pass rate, duration, tokens, cost, tool success rate, error recovery rate and per-dimension process quality. |

With multiple runs (`--run-id average` and `max_run > 1`) the workbook additionally contains one `<run_id>` task-summary sheet per run. `main.py run` runs the same analysis automatically after evaluation.

### Report page

```bash
cd clawbench
uv run python main.py visualize --result-dir results --port 4999
```

Open <http://127.0.0.1:4999>. The page reads the `results/` directory and provides three views: a **dashboard** (aggregate metrics, distributions, per-model score bars), a **model comparison** view, and a **model detail** view with per-task drill-down (score, rubric tree results, session timeline, workspace preview, judge review, multi-run details). The backend exposes the corresponding JSON API under `/api/…` (`src/visualizer/api.py`).

The report page re-derives scores server-side from the stored `rubric_results` with the authoritative scoring module, and both the report page and the analyzer use the same pass/`complete_flag` logic and threshold, so their numbers are consistent with the stored `score.json` records.

## Security notes

- **Gateway token:** `OPENCLAW_GATEWAY_TOKEN` is shared by the container manager and the evaluator. It is injected into the container at start; never commit it, and do not log it.
- **No authentication by default:** both the manual scoring UI and the report page (and the container manager) have no login layer. All three services bind to `127.0.0.1` by default; expose them only deliberately (`--host`) and never make them public without an authenticating reverse proxy.
- **Secrets on disk:** `clawbench/tasks/openclaw.json` (model API key), `clawbench/configs/claude_settings.json` (judge endpoint token) and `raf/data/llm_config.json` are gitignored. Keep them out of archives and screenshots.
- **Sandbox scope:** containers are short-lived and removed after each run; workspace content is collected under the result directory and may contain sensitive task fixtures — review before sharing. The Docker socket/CLI is invoked by the trusted container manager process only.
- **Paths:** the manual scorer resolves workspace files inside the run directory and rejects path traversal.

## Troubleshooting

Common setup issues (frontend bundles, Docker, gateway tokens, model endpoints, proxies, package indexes) are summarised in the *Known limitations* section of the [ClawBench README](../clawbench/README.md).

# ClawBench: long-horizon personal-assistant agent benchmark

This directory (`clawbench/`) contains **ClawBench**, a benchmark of **121 long-horizon personal-assistant tasks** collected from real OpenClaw usage, together with the harness needed to run it: Docker-sandboxed execution, trace/workspace collection, human and judge-agent scoring, result analysis and a report page.

- **Every task is scored by a rubric-based manual judgement** — by a human annotator (manual scoring UI) or by a judge agent (Claude Agent SDK). No rule-based or LLM-verifier auto-scoring is shipped; `verifier_type` is `manual` for all 121 tasks.
- **Rubrics are built in**: each task definition carries a verified AND–OR rubric (1,920 binary leaves in total, generated with RAF prompt version v5.1 and reviewed by experts).
- **The benchmark is bilingual**: each task has a Chinese `config.json` and an English `config.en.json`; input files stay in Chinese.

Paper: *RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents* (ICLR 2027 submission) · Repository: <https://github.com/RAFPAPER2026/RAF>

## Repository layout

```
clawbench/
├── main.py                     # CLI: eval / run / analyze / visualize / rerun / judge
├── src/
│   ├── container_manager.py    # Docker container manager (FastAPI, port 10800)
│   ├── container_client.py     # manager client + OpenClaw gateway client
│   ├── orchestrator.py         # task loading, parallel execution, result dir naming
│   ├── runner.py               # per-task lifecycle (container → init → request → collect → clean)
│   ├── runs.py                 # run discovery, per-run result.json, multi-run averaging, pass@k
│   ├── models.py               # TaskConfig (config.json / config.en.json) and statuses
│   ├── i18n.py                 # language selection (CLAWBENCH_LANG / --lang)
│   ├── rubric/                 # scoring framework (single source of truth, tree + legacy compat)
│   ├── agent_scorer/           # judge agent (Claude Agent SDK): prompts, scorer, batch manager
│   ├── analyzer/               # statistics and Excel export
│   ├── visualizer/             # report-page backend (dashboard / comparison / model detail)
│   └── openclaw_events.py      # session-transcript reading and normalisation
├── manual_scorer/              # manual scoring UI + REST API (FastAPI + React, port 5002)
├── web/                        # report page frontend (React, served on port 4999)
├── tasks/<task_id>/            # config.json + config.en.json + init_env/
├── metadata/                   # taxonomy.json (bilingual) + tasks.jsonl (task index)
├── configs/                    # trace_config.json, agent_scorer_config.json, claude_settings.example.json
├── docker/openclaw/            # Dockerfile + configuration template for the sandbox image
├── tests/                      # harness tests, including dataset integrity checks
└── results/                    # runtime output (gitignored)
```

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | `.python-version` pins 3.12; `uv sync` installs it automatically. |
| Docker Engine | Required to run tasks (one sandbox container per job). On Windows/macOS use Docker Desktop. |
| The OpenClaw sandbox image | Not distributed. Build it from `docker/openclaw/`, or load an image archive you exported yourself. |
| Node.js 20+ + npm | To build the report page (`web/`) and the manual scoring UI (`manual_scorer/web/`). |
| An OpenAI-compatible model endpoint | For the agent under test. Configure it in `tasks/openclaw.json`. |
| An Anthropic-compatible endpoint + token | Only for judge-agent scoring (`configs/claude_settings.json`). |

## Quick start

All commands are run from the repository root.

### 1. Install dependencies and build the frontends

```bash
cd clawbench
uv sync
```

```bash
cd clawbench/web
npm install
npm run build
```

```bash
cd clawbench/manual_scorer/web
npm install
npm run build
```

Both `dist/` directories are gitignored; the FastAPI services return a "build the frontend first" message until they exist.

### 2. Provide the sandbox image

Build it from the included Dockerfile (needs the upstream base image, from `ghcr.io/openclaw/openclaw`):

```bash
docker build \
  --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.4.2 \
  -t openclaw:base.4.2 \
  clawbench/docker/openclaw
```

Or load an archive you already have:

```bash
docker load -i /path/to/openclaw-base.4.2.tar
```

### 3. Set the required environment variables

```bash
export OPENCLAW_GATEWAY_TOKEN=choose-a-shared-token   # required
export OPENCLAW_IMAGE=openclaw:base.4.2               # optional; this is the default
```

`OPENCLAW_GATEWAY_TOKEN` is shared by the container manager (which injects it into every sandbox) and the evaluator (which authenticates to the sandbox gateway with it). If your Docker host needs a proxy to reach the model endpoint, set `OPENCLAW_PROXY` as well.

### 4. Configure the model endpoint

```bash
cd clawbench
cp openclaw.example.json tasks/openclaw.json
# edit models.providers (baseUrl / apiKey / models[].id)
# and agents.defaults.model.primary
```

`tasks/openclaw.json` is mounted into every container as `/root/.openclaw/openclaw.json`. A single task can use its own configuration by adding a top-level `openclaw_config_path` key to its `config.json`. Both `tasks/openclaw.json` and per-task configs may contain API keys: they are gitignored, never commit them.

### 5. Start the container manager (port 10800)

Keep it running in its own terminal:

```bash
cd clawbench
uv run python src/container_manager.py
```

### 6. Run the evaluation

```bash
cd clawbench

# evaluate and analyze
uv run python main.py run --tasks-dir tasks --model-name my-model --workers 4

# evaluate only
uv run python main.py eval --tasks-dir tasks --result-base-dir results --workers 4

# k repeats per task (pass@k)
uv run python main.py run --tasks-dir tasks --model-name my-model --runs 3 --workers 4
```

Each task/run is executed in an isolated container; results go to `results/<tasks>[_EN]_<model>_<timestamp>_<uuid8>/`.

### 7. Analyze, report and score

```bash
cd clawbench

# Excel analysis (writes analysis_report.xlsx into the result directory)
uv run python main.py analyze --result-dir results/<model_dir> --tasks-dir tasks

# report page (dashboard / model comparison / per-task drill-down)
uv run python main.py visualize --result-dir results --port 4999

# manual scoring UI
uv run python manual_scorer/main.py --result-dir results --tasks-dir tasks --port 5002
```

Open <http://127.0.0.1:4999> for the report page and <http://127.0.0.1:5002> for manual scoring. The runner itself never writes scores — every task needs a human or judge-agent score.

### 8. Score results with the judge agent

Configure credentials first (see below), then:

```bash
cd clawbench

# score one model directory and adopt the judge results as manual scores
uv run python main.py judge --result-dir results/<model_dir> --tasks-dir tasks --adopt

# optionally also record process-quality dimensions and skip already-reviewed cases
uv run python main.py judge --result-dir results/<model_dir> --tasks-dir tasks \
  --evaluate-trace --skip-existing --workers 4
```

Judge artifacts are written to `results/<model_dir>/<task>/run_<n>/verifier/judge/` (`agent_judge.jsonl`, optional `exceptions.md` and `proof/`), and the review is stored in `score.json` as `agent_review`. With `--adopt`, the leaf verdicts are scored by the rubric engine and written as `manual_score` plus the derived rubric fields.

## CLI reference

| Command | Purpose |
|---|---|
| `main.py eval --tasks-dir tasks --result-base-dir results --workers 4` | Evaluate only. |
| `main.py run --tasks-dir tasks --model-name <model> --workers 4` | Evaluate plus analyze. |
| `main.py rerun --result-dir results/<model_dir> --tasks-dir tasks` | Re-run failed tasks into a new run directory. |
| `main.py analyze --result-dir results/<model_dir> --tasks-dir tasks` | Export `analysis_report.xlsx`. |
| `main.py visualize --result-dir results --port 4999` | Serve the report page. |
| `main.py judge --result-dir results/<model_dir> --tasks-dir tasks --adopt` | Batch judge-agent scoring. |
| `manual_scorer/main.py --result-dir results --tasks-dir tasks --port 5002` | Serve the manual scoring UI. |
| `src/container_manager.py` | Serve the Docker container manager (port 10800). |
| `uv run pytest` | Run the test suite (includes dataset integrity checks). |

Shared flags, available on the evaluation/analysis/report/scoring/judge commands: `--lang {zh,en}` (default `zh`) and `--quality-aggregation {paper,legacy_mean}` (default `paper`).

## Language and scoring modes

| Flag | Default | Meaning |
|---|---|---|
| `--lang zh` | yes | Read `config.json` (Chinese task definitions). |
| `--lang en` | | Read `config.en.json`; falls back to Chinese when the translation is missing. Prompt language follows the same setting. |
| `--quality-aggregation paper` | yes | Paper Eq. 1: leaf verdicts are binary; an AND group scores 1 only when every child passes; OR takes the maximum; top-level quality items are combined by weight. |
| `--quality-aggregation legacy_mean` | | Backward compatibility: AND groups take the mean of their children. |

The scoring mode is recorded in each scored `score.json` (`scoring_mode`) and must be consistent across scoring and analysis. It is implemented in `src/rubric/scoring.py` (authoritative Python) with TypeScript mirrors in `manual_scorer/web/src/lib/scoring.ts`, and the same formula is implemented on the RAF side; the report page re-derives scores server-side from the stored `rubric_results`.

## Skills and key configuration

Thirteen tasks require external skills that are **not distributed** with the repository:

| Skill | Tasks |
|---|---|
| `baidu-search` (web search) | 12 |
| `rapid-ocr-reader` (image OCR) | 1 |

Place a skill implementation under the task's initial environment so the harness mounts it into the sandbox:

```
clawbench/tasks/<task_id>/init_env/.skills/<skill-name>/
```

`metadata/tasks.jsonl` records `required_skills` per task, so you can filter out tasks whose skills you do not have. The `.skills/` directory is mounted into the container (not copied into the agent workspace); `.preset/` is mounted as well, and optional `.scripts/` are executed on the host during environment initialization.

Credentials and secrets are kept out of git by design:

| File | Purpose | Committed? |
|---|---|---|
| `tasks/openclaw.json` | Sandbox model endpoint/API key (copied from `openclaw.example.json`). | No (gitignored) |
| `configs/claude_settings.json` | Judge-agent SDK settings: `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL` (copied from `configs/claude_settings.example.json`). | No (gitignored) |
| `configs/agent_scorer_config.json` | Judge-agent parameters: `settings_path`, `model`, `max_turns` (120), `timeout_seconds` (1800), `permission_mode`. | Yes |
| `configs/model_prices.json` | Optional token price table for cost statistics (otherwise costs are 0). | No (gitignored) |
| `OPENCLAW_GATEWAY_TOKEN` | Sandbox gateway token, injected at container start. | Environment only |

To configure the judge agent:

```bash
cd clawbench
cp configs/claude_settings.example.json configs/claude_settings.json
# fill in env.ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_MODEL
```

## Results layout and pass@k

```
results/<tasks>[_EN]_<model>_<timestamp>_<uuid8>/
├── eval.log                       # full evaluation log
├── result.json                    # model-level summary (rebuilt from score.json files)
├── analysis_report.xlsx           # after `main.py analyze` / `main.py run`
└── <task_id>/
    └── run_<n>/
        ├── score.json             # run metrics + rubric scoring record
        ├── sessions.json          # collected execution trace
        ├── workspace/             # agent deliverables (evidence for scoring)
        └── verifier/judge/        # judge-agent artifacts (when used)
```

- **Pass criterion:** `complete_flag == 1`, i.e. every top-level completion item of the rubric passes. Legacy data without the flag falls back to `score >= 0.75` (`configs/trace_config.json`).
- **pass@k:** `--runs k` repeats every task k times. The case-level average view reports `pass_at_1`, `pass_rate_over_runs` and `pass_k`; the average `complete_flag` is **pass^k** (1 only if all k runs pass), and the averaged case `status` is `completed` only when a strict majority of runs completed.
- A virtual `average` run is used by default by the analyzer and report page; concrete run IDs can be selected with `--run-id`.
- Full field details (config, rubric, `score.json`, `result.json`, `sessions.json`) are in [Data format](../docs/data_format.md).

## Known limitations

- **Docker is mandatory** for evaluation; the sandbox image is not distributed, so you must build or load it first.
- **A model endpoint is mandatory** for the agent under test: the image ships only a placeholder provider, and `tasks/openclaw.json` must point at a reachable OpenAI-compatible endpoint.
- **Task instructions and input files are Chinese.** `--lang en` translates the task definition and rubric, but `init_env/` files are deliberately left in Chinese and are not translated.
- **External skills are not bundled**: 13 tasks need `baidu-search` / `rapid-ocr-reader` placed under `init_env/.skills/`; the other 108 tasks run without them.
- **Judge-agent scoring is optional and requires an Anthropic-compatible endpoint** plus a filled `configs/claude_settings.json`; without it, score results with the manual UI.
- **The harness is resource-heavy**: one container per job, long-horizon tasks with timeouts up to 600 s, and full-benchmark runs take hours even with parallel workers.
- **No authentication by default**: all three services (manual scoring UI, report page, container manager) bind to `127.0.0.1` by default; pass `--host` explicitly to expose them, and never make them public without an authenticating reverse proxy.
- **Token costs default to 0** unless you provide `configs/model_prices.json` (or point `CLAWBENCH_MODEL_PRICES` at a price table).
- **Legacy formats are read-only compatible**: old flat rubrics and score files can be read, but the judge agent only supports tree rubrics, and migration does not reproduce the original scores.

## Tests

```bash
cd clawbench
uv run pytest
```

The dataset tests enforce the released statistics (121 tasks; 1,920 leaves split 666/1,254; 533 groups; weights ⊆ `{1,2,3,4,6}`; mean 8.43 top-level entries), task/config invariants, metadata consistency, absence of known sensitive identifiers, and Chinese/English structural parity. Harness tests cover the runner configuration, run discovery and averaging, scoring modes, the judge agent, the analyzer and the manual scorer.

## Documentation

| Topic | Document |
|---|---|
| Benchmark composition and statistics | [docs/benchmark.md](../docs/benchmark.md) |
| Config/rubric/result schemas | [docs/data_format.md](../docs/data_format.md) |
| Container lifecycle, scoring, judge agent, report tools | [docs/evaluation.md](../docs/evaluation.md) |
| RAF platform (rubric generation) | [raf/README.md](../raf/README.md) |

## License and citation

Benchmark data, annotations and prompt assets are released under **CC BY 4.0** ([`LICENSE-DATA`](../LICENSE-DATA)); the evaluation code is **Apache-2.0** ([`LICENSE`](../LICENSE)). Third-party files inside `tasks/*/init_env/` remain under their original licenses — see [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

If you use ClawBench, please cite the paper:

> RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents. ICLR 2027 submission. <https://github.com/RAFPAPER2026/RAF>

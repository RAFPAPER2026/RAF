# RAF: Rubric Auto-generation Framework

This directory (`raf/`) is the implementation of the **RAF** platform: it turns a user query into an editable AND–OR evaluation rubric, records expert reviews and scores, and runs the PROMPT-R refinement loop until the rubric aligns with human preference. It is the platform used to generate the 121 ClawBench rubrics.

Paper: *RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents* (ICLR 2027 submission) · Repository: <https://github.com/RAFPAPER2026/RAF>

## What the platform implements

| Framework step | In the platform |
|---|---|
| **Generation** | An LLM produces a completion rubric (binary tree) and a quality rubric (weighted tree) from a seven-module prompt; single or batch generation from the UI, HTTP API or CLI. |
| **Expert review** | Per-rubric 1–5 star completion/quality reviews with notes, plus a batch-level approved/rejected quality gate per optimization round. |
| **Score recording** | A score sheet per optimization round: a human gold score plus each rater's score for every rubric. |
| **Termination** | Pearson / Spearman / QWK / composite metrics are computed and checked against target, convergence, budget and degradation rules. |
| **Suggestion → adoption → refinement** | RIFT diagnostics produce failure-mode findings and module-level suggestions; a human adopts suggestions; the LLM refines the affected prompt modules into a new prompt version, closing the loop. |

## Features

| Feature | Details |
|---|---|
| **Versioned, modular prompts** | Seven fixed-order modules (`role → structure → principles → examples → constraints → capabilities → output`), distributed versions **v5.1** (used to generate the ClawBench rubrics) and **v5.10** (latest, refined with PROMPT-R), each in Chinese and English. |
| **Tree rubric editor** | Build and edit AND/OR trees: leaves with capability tags, groups with `and`/`or` combinators, quality top-level weights in `{1, 2, 3, 4, 6}`, live validation and batch preview. |
| **Scoring** | Tick leaves to get binary completion (all-pass) and weighted quality; switch quality aggregation between `paper` (paper Eq. 1: AND groups are all-pass binary) and `legacy_mean`. |
| **Reviews** | 1–5 star completion and quality ratings plus up to three notes per rubric; aggregated statistics by prompt version. |
| **PROMPT-R optimization workbench** | Rounds with background generation, optional batch quality screening, score sheets, metric computation, RIFT analysis, suggestion adoption and prompt refinement into a new version. |
| **RIFT diagnostics** | Eight rubric failure modes in three families (reliability, content validity, consequence validity), diagnosed per rubric and aggregated to the prompt modules that need revision. |
| **Alignment metrics** | Pearson `r`, Spearman `ρ`, quadratic weighted kappa (5 levels), composite = `0.8·r + 0.2·QWK`, plus per-rubric deviations. |
| **Query management** | Central query store with tags, Excel/JSON import and export, and migration of queries from existing rubrics. |
| **Bilingual assets** | Chinese and English generation prompts and capability lists; `RAF_LANG` / `--lang` select the language, with English fallback to Chinese. |
| **File-based storage** | Plain JSON storage under `raf/data/` — no database required; the UI and API share the same data. |

## Quick start

```bash
cd raf

# Python dependencies
uv sync

# build the web UI (the dist/ directory is not committed)
cd frontend
npm install
npm run build
cd ..

# configure the LLM (environment variables override data/llm_config.json)
export RAF_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
export RAF_LLM_API_KEY=your-api-key
export RAF_LLM_MODEL=your-model

# start the platform
uv run python app.py
```

Open <http://localhost:8081>. On first start the platform seeds two demo queries, two demo rubrics and one review, so the list, builder, scorer and review pages have content to show.

Instead of environment variables you can copy the tracked template and edit it:

```bash
cd raf
cp configs/llm_config.example.json data/llm_config.json
```

The configuration is re-read on every LLM call, so edits take effect without restarting the server. Supported keys: `base_url`, `api_key`, `model`, `temperature`, `max_tokens`, `timeout`.

For frontend development, run Vite in a second terminal; `/api` is proxied to port 8081:

```bash
cd raf/frontend
npm run dev        # http://localhost:5173
```

## CLI

```bash
cd raf

# generate one rubric (saved to data/rubrics.json unless --no-save)
uv run python generate_rubric.py "Plan a three-day trip to Kyoto" --prompt-version v5.10

# generate without saving
uv run python generate_rubric.py "<query>" --prompt-version v5.10 --no-save

# generate with English prompt assets
uv run python generate_rubric.py "<query>" --prompt-version v5.10 --lang en

# batch generation from a file with one query per line
uv run python batch_generate.py --input queries.txt --prompt-version v5.10 --lang en --concurrency 8

# list managed queries (id, text; -v adds tags and rubric counts)
uv run python list_queries.py -v
```

`generate_rubric.py` calls the LLM with structured output first (JSON Schema), falls back to plain JSON mode on failure, retries up to three times, normalises the tree (single-child groups are collapsed, duplicate children removed) and warns about leaves with missing or unknown capability tags. `batch_generate.py` deletes previous rubrics for the same query/version/language before writing new ones.

## Prompt versions and language

| Concept | Details |
|---|---|
| Prompt versions | JSON files in `data/prompt_versions/` (`v5.1.json`, `v5.10.json`, plus their `.en.json` English translations). Each records `version`, `parent_version`, `created_at`, `change_description`, `metrics_summary` and the seven `modules`. |
| Active version | Stored in `data/active_prompt_version.txt` (currently `v5.10`); used whenever `--prompt-version` / `prompt_version` is omitted. |
| v5.1 | The prompt version used to generate all ClawBench rubrics; its recorded iteration metrics are Pearson 0.65 / QWK 0.57 / composite 0.634. |
| v5.10 | Latest version, refined from v5.9 through PROMPT-R (suggestions absorbed into the structure, principles, constraints and output modules). |
| Language selection | `RAF_LANG=zh` (default) or `RAF_LANG=en` for the server/API; `--lang zh\|en` for the CLIs (it also sets `RAF_LANG`). |
| Fallback | English assets fall back to Chinese when the `.en.json` file or `capabilities.en.txt` is missing. |
| Version management | The Prompt versions page can browse assembled prompts, diff two versions module by module, edit a module, clone a version with a change description, and activate a version. |

Prompt-version and capability-list API examples: `GET /api/prompt-versions`, `GET /api/prompt-versions/{version}`, `GET /api/prompt-versions/{version}/diff?compare_to=…`, `PUT /api/prompt-versions/{version}/modules/{module}`, `POST /api/prompt-versions/{version}/clone`, `PUT /api/prompt-versions/{version}/activate`, `GET|PUT /api/capabilities`.

## Scoring modes

Both the Python backend (`rubric/scoring.py`) and the frontend mirror (`frontend/src/lib/scoring.ts`) implement the same two modes:

| Mode | Completion | Quality leaf | OR group | AND group | Top level |
|---|---|---|---|---|---|
| `paper` (default) | all top-level completion items pass | 1 / 0 | max | 1 only if all children pass, else 0 | weighted mean |
| `legacy_mean` | same | 1 / 0 | max | mean of children | weighted mean |

The default mode is resolved from `CLAWBENCH_SCORING_MODE` (default `paper`). The scoring page and `POST /api/rubrics/{id}/score` accept a `scoring_mode` field; the response reports completion, weighted quality, the per-item breakdown and the mode used. Keep the two implementations in sync if the formula changes.

## Pages

The UI is in Chinese and has seven pages:

| Route | Page | What it does |
|---|---|---|
| `/list` | 量规列表 (Rubric list) | Search rubrics, inspect review statistics and tags, open the builder/scorer/review views. |
| `/builder` | 量规构建 (Builder) | Generate a rubric from a query or compose/edit the tree, then save. |
| `/scorer` | 评分 (Scoring) | Tick leaves, preview completion and weighted quality, switch scoring mode. |
| `/review/:id` | 审核 (Review) | Record a star review (completion 1–5, quality 1–5) with up to three notes. |
| `/prompts` | Prompt 版本 (Prompt versions) | Inspect assembled prompts and module sizes, diff, edit, clone, activate versions; edit the capability list. |
| `/optimize` | 优化实验 (Optimization) | PROMPT-R workbench: runs, rounds, quality screening, score sheets, metrics, RIFT diagnosis, suggestion adoption, refinement, stopping checks. |
| `/queries` | Query 管理 (Query management) | Create/import/export queries, manage tags, migrate queries from existing rubrics. |

The HTTP API is mounted under `/api` (rubrics CRUD/scoring, reviews, prompt versions, capabilities, queries, batch generation, optimization runs). The FastAPI app also serves the built SPA from `frontend/dist/` with a history fallback.

## Data files

| Path | Committed | Content |
|---|---|---|
| `data/prompt_versions/*.json`, `*.en.json` | yes | Seven-module prompt assets (zh/en). |
| `data/capabilities.txt`, `data/capabilities.en.txt` | yes | Capability list used for leaf tags and prompt injection. |
| `data/active_prompt_version.txt` | yes | Active prompt version (currently `v5.10`). |
| `data/rubrics.json` | yes (demo) | Rubrics; ships with two demo examples. |
| `data/queries.json` | yes (demo) | Managed queries; ships with two demo examples. |
| `data/reviews.json` | yes (demo) | Reviews; ships with one demo example. |
| `data/llm_config.json` | no (gitignored) | LLM endpoint/key configuration (auto-created empty on first start). |
| `data/optimization_runs/` | no (gitignored) | PROMPT-R run records (`run-*.json`). |
| `frontend/dist/` | no (gitignored) | Frontend build output served by `app.py`. |
| `data/usecase/*.txt` | no | Optional default input for `batch_generate.py` (one query per line). |

## Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `RAF_LLM_BASE_URL` | from `data/llm_config.json` | OpenAI-compatible base URL. |
| `RAF_LLM_API_KEY` | from `data/llm_config.json` | API key (required for any LLM call). |
| `RAF_LLM_MODEL` | from `data/llm_config.json` | Model id. |
| `RAF_LLM_TIMEOUT` | from `data/llm_config.json` / 300 s | Request timeout. |
| `RAF_LANG` | `zh` | Prompt language: `zh` or `en`. |
| `CLAWBENCH_SCORING_MODE` | `paper` | Default quality scoring mode: `paper` or `legacy_mean`. |

The LLM HTTP client does not use the system proxy (`trust_env=False`); point `base_url` at an endpoint that is directly reachable from the host running the platform.

## Limitations

- **LLM access is mandatory** for generation, RIFT diagnosis and prompt refinement; there is no offline template fallback.
- **No authentication.** The platform is a research tool: it binds to `127.0.0.1:8081` by default (`RAF_HOST` / `RAF_PORT` to change) and has no login layer — run it on a trusted network.
- **Single-node, file-based storage.** Concurrent multi-user deployments are outside the scope of this release; JSON files are written atomically but there is no database.
- **The UI is Chinese.** Prompt assets and generated rubrics can be produced in English (`--lang en` / `RAF_LANG=en`), but the interface labels are Chinese.
- **The frontend must be built.** `frontend/dist/` is deliberately not committed; `app.py` serves the UI only after `npm run build`.
- **Metrics need a score batch.** Correlations are undefined for fewer than two scored rubrics; a single case can still be diagnosed with RIFT.
- **Demo data is minimal.** `rubrics.json`, `queries.json` and `reviews.json` contain two/two/one seeded examples; real usage data is not distributed.
- **LLM generation is non-deterministic.** The same query and prompt version yield rubrics of the same style and constraints, not identical trees.

## Tests

```bash
cd raf
uv run pytest
```

The suite covers metrics, both scoring modes, prompt-module assembly, and LLM client configuration. See [Framework (RAF)](../docs/framework.md) for the methodology and [Data format](../docs/data_format.md) for the storage formats; the [repository README](../README.md) has the end-to-end quick start.

## License and citation

Code is released under **Apache-2.0** ([`LICENSE`](../LICENSE)); benchmark data and prompt assets referenced from this platform are released under **CC BY 4.0** ([`LICENSE-DATA`](../LICENSE-DATA)). If you use RAF, please cite the paper:

> RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents. ICLR 2027 submission. <https://github.com/RAFPAPER2026/RAF>

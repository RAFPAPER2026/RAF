# RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents

Official repository for the paper **“RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents”**.

The release has two components:

| Component | What it is |
|---|---|
| [`raf/`](raf/) | The **RAF** implementation: an LLM-driven platform that generates AND–OR rubric trees from user queries, records human/judge scores, measures alignment with human preference, and iteratively refines the rubric through expert-reviewed suggestions (PROMPT-R) with RIFT failure-mode diagnostics. |
| [`clawbench/`](clawbench/) | **ClawBench**, a benchmark of **121 long-horizon personal-assistant tasks** collected from real OpenClaw usage, together with a Docker-based evaluation harness, a judge agent, a manual scoring UI, and reporting/analysis tools. Every task is evaluated as a rubric-based manual judgement (human or judge agent). |

## What is included

- **121 tasks** under [`clawbench/tasks/`](clawbench/tasks/), each with its initial environment (`init_env/`) and a **Chinese** task definition (`config.json`) plus an **English** translation (`config.en.json`).
- **Verified AND–OR rubrics** embedded in the task configs: 1,920 binary leaf criteria in total (666 completion-side, 1,254 quality-side), 533 internal AND/OR group nodes.
- **Bilingual prompt assets**: rubric-generation prompts for versions `v5.1` (the version used to build ClawBench) and `v5.10` (latest), the judge-agent system prompts, and the capability lists — each in Chinese and English.
- **Evaluation code**: RAF platform (`raf/`), container orchestration, judge agent, manual scoring UI, report page and analyzers (`clawbench/`).
- **Documentation** in English and Chinese under [`docs/`](docs/).

## Repository layout

```
raf/                    # RAF platform: rubric generation, review, scoring, optimization
clawbench/              # ClawBench: 121 tasks + evaluation harness
  tasks/<task_id>/      #   init_env/ + config.json (zh) + config.en.json (en)
  src/                  #   orchestrator, container runner, judge agent, rubric scoring, analyzer, report API
  manual_scorer/        #   manual scoring UI (FastAPI + React)
  web/                  #   report page (React)
  docker/openclaw/      #   Dockerfile and configuration template for the OpenClaw sandbox
  metadata/             #   task index and bilingual taxonomy
  tests/                #   unit/integration tests, including dataset integrity checks
docs/                   # bilingual documentation
```

## Quick start (Chinese data, default)

### 1. Rubric auto-generation (RAF)

```bash
cd raf
uv sync
cd frontend && npm install && npm run build && cd ..

export RAF_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
export RAF_LLM_API_KEY=your-key
export RAF_LLM_MODEL=your-model

uv run python app.py          # http://localhost:8081
```

Generate a rubric from the CLI:

```bash
uv run python generate_rubric.py "帮我规划下周的行程" --prompt-version v5.10
uv run python generate_rubric.py "Plan my trip for next week" --prompt-version v5.10 --lang en
```

See [`raf/README.md`](raf/README.md) for prompt versions, scoring modes and the optimization workbench.

### 2. Benchmark evaluation (ClawBench)

Prerequisites: Docker (with an OpenClaw image), Python 3.12+ with `uv`, Node.js for the two frontends, and an OpenAI-compatible model endpoint for the agent under test.

```bash
cd clawbench
uv sync
# build the two frontends (report page and manual scoring UI)
(cd web && npm install && npm run build)
(cd manual_scorer/web && npm install && npm run build)
# build (or load) the sandbox image; see docker/openclaw/README.md
docker build --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.4.2 \
  -t openclaw:base.4.2 docker/openclaw

export OPENCLAW_GATEWAY_TOKEN=<shared-token>     # required
cp openclaw.example.json tasks/openclaw.json     # then edit models.providers
uv run python src/container_manager.py           # port 10800

uv run python main.py run --tasks-dir tasks --model-name <model> --workers 4
uv run python main.py visualize --result-dir results --port 4999
uv run python manual_scorer/main.py --result-dir results --tasks-dir tasks --port 5002
```

Judge-agent scoring of existing results (adopts into `manual_score`):

```bash
uv run python main.py judge --result-dir results/<model_dir> --tasks-dir tasks --adopt
```

See [`clawbench/README.md`](clawbench/README.md) and [`docs/evaluation.md`](docs/evaluation.md) for the full pipeline.

## Language and scoring modes

- **Language**: `--lang {zh,en}` (default `zh`). English configs are translations that keep the same rubric node ids, weights and tree structure; input files are not translated, so English prompts may reference Chinese file names.
- **Quality aggregation**: `--quality-aggregation {paper,legacy_mean}` (default `paper`).
  - `paper` follows the paper: leaf verdicts are binary, an AND group scores 1 only when every child passes, OR takes the maximum, and top-level quality entries are combined by weight.
  - `legacy_mean` keeps the earlier mean-based aggregation for compatibility.

## Documentation

| Document | English | 中文 |
|---|---|---|
| Framework (RAF) | [docs/framework.md](docs/framework.md) | [docs/framework.zh-CN.md](docs/framework.zh-CN.md) |
| Benchmark (ClawBench) | [docs/benchmark.md](docs/benchmark.md) | [docs/benchmark.zh-CN.md](docs/benchmark.zh-CN.md) |
| Data format | [docs/data_format.md](docs/data_format.md) | [docs/data_format.zh-CN.md](docs/data_format.zh-CN.md) |
| Evaluation | [docs/evaluation.md](docs/evaluation.md) | [docs/evaluation.zh-CN.md](docs/evaluation.zh-CN.md) |

## License

- Code: [Apache-2.0](LICENSE)
- Benchmark data, annotations and prompt assets: [CC BY 4.0](LICENSE-DATA)
- Third-party files contained in task fixtures remain under their original licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citation

If you use RAF or ClawBench, please cite the paper (see [CITATION.cff](CITATION.cff)):

```bibtex
@inproceedings{raf2027,
  title     = {RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents},
  booktitle = {International Conference on Learning Representations (ICLR)},
  year      = {2027},
  url       = {https://github.com/RAFPAPER2026/RAF}
}
```

## Acknowledgements

Some ClawBench task scenarios were inspired by, or adapted from, publicly available
agent-evaluation projects, including [Claw-Eval](https://github.com/claw-eval/claw-eval)
and [PinchBench](https://github.com/pinchbench/skill). We thank their authors.

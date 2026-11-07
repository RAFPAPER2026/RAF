# RAF：面向长程 LLM Agent 可审计评测的量规自动生成框架

本仓库是论文 **《RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents》** 的官方开源仓库。

仓库包含两个部分：

| 组件 | 说明 |
|---|---|
| [`raf/`](raf/) | **RAF** 框架实现：根据用户 query 自动生成 AND–OR 量规树，记录人工/裁判评分，计算与人类偏好的一致性，并通过“专家审核建议 + PROMPT-R 精炼 + RIFT 失败模式诊断”迭代优化量规。 |
| [`clawbench/`](clawbench/) | **ClawBench**：121 个来自真实 OpenClaw 使用场景的长程个人助理任务，配套基于 Docker 的评测框架、裁判 agent、人工打分页与报告/分析工具。所有任务均采用基于量规的人工/裁判评分。 |

## 仓库内容

- [`clawbench/tasks/`](clawbench/tasks/) 下的 **121 个任务**：每个任务包含初始环境 `init_env/`、中文任务定义 `config.json` 与英文翻译 `config.en.json`。
- 任务内嵌的**经校验 AND–OR 量规**：共 1,920 个二元叶子（完成侧 666、质量侧 1,254）、533 个 AND/OR 组节点。
- **中英双语 Prompt**：rubric 生成 prompt `v5.1`（构建 ClawBench 所用版本）与 `v5.10`（最新版本）、裁判 agent 系统 prompt、能力项列表，均提供中英两版。
- **评测代码**：RAF 平台（`raf/`）、容器编排、裁判 agent、人工打分页、报告页与分析器（`clawbench/`）。
- [`docs/`](docs/) 下的中英双语文档。

## 目录结构

```
raf/                    # RAF 平台：量规生成、审核、评分、优化
clawbench/              # ClawBench：121 个任务 + 评测框架
  tasks/<task_id>/      #   init_env/ + config.json（中文）+ config.en.json（英文）
  src/                  #   编排器、容器执行、裁判 agent、量规评分、分析器、报告 API
  manual_scorer/        #   人工打分页（FastAPI + React）
  web/                  #   报告页（React）
  docker/openclaw/      #   OpenClaw 沙箱镜像 Dockerfile 与配置模板
  metadata/             #   任务索引与中英标签词表
  tests/                #   单元/集成测试（含数据集完整性检查）
docs/                   # 中英双语文档
```

## 快速开始（默认中文数据）

### 1. 量规自动生成（RAF）

```bash
cd raf
uv sync
cd frontend && npm install && npm run build && cd ..

export RAF_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
export RAF_LLM_API_KEY=your-key
export RAF_LLM_MODEL=your-model

uv run python app.py          # http://localhost:8081
```

命令行生成量规：

```bash
uv run python generate_rubric.py "帮我规划下周的行程" --prompt-version v5.10
uv run python generate_rubric.py "Plan my trip for next week" --prompt-version v5.10 --lang en
```

Prompt 版本、评分口径与优化工作台详见 [`raf/README.zh-CN.md`](raf/README.zh-CN.md)。

### 2. 评测集评测（ClawBench）

前置条件：Docker 与 OpenClaw 镜像、Python 3.12+ 与 `uv`、用于构建两个前端的 Node.js，以及被测 agent 的 OpenAI 兼容模型端点。

```bash
cd clawbench
uv sync
# 构建报告页与人工打分页两个前端
(cd web && npm install && npm run build)
(cd manual_scorer/web && npm install && npm run build)
# 构建（或加载）沙箱镜像，详见 docker/openclaw/README.md
docker build --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.4.2 \
  -t openclaw:base.4.2 docker/openclaw

export OPENCLAW_GATEWAY_TOKEN=<shared-token>     # 必填
cp openclaw.example.json tasks/openclaw.json     # 修改 models.providers
uv run python src/container_manager.py           # 端口 10800

uv run python main.py run --tasks-dir tasks --model-name <model> --workers 4
uv run python main.py visualize --result-dir results --port 4999
uv run python manual_scorer/main.py --result-dir results --tasks-dir tasks --port 5002
```

对既有结果运行裁判 agent（自动采纳为 `manual_score`）：

```bash
uv run python main.py judge --result-dir results/<model_dir> --tasks-dir tasks --adopt
```

完整链路见 [`clawbench/README.zh-CN.md`](clawbench/README.zh-CN.md) 与 [`docs/evaluation.zh-CN.md`](docs/evaluation.zh-CN.md)。

## 语言与评分口径

- **语言**：`--lang {zh,en}`（默认 `zh`）。英文 config 为翻译版，保持相同的 rubric 节点 id、权重与树结构；输入文件不翻译，因此英文 prompt 中可能保留中文文件名。
- **质量分口径**：`--quality-aggregation {paper,legacy_mean}`（默认 `paper`）。
  - `paper` 与论文一致：叶子为二元判定，AND 组所有子节点通过才得 1，OR 组取最大值，质量顶层项按权重加权。
  - `legacy_mean` 保留早期的均值聚合口径，用于兼容。

## 文档

| 文档 | English | 中文 |
|---|---|---|
| 框架（RAF） | [docs/framework.md](docs/framework.md) | [docs/framework.zh-CN.md](docs/framework.zh-CN.md) |
| 评测集（ClawBench） | [docs/benchmark.md](docs/benchmark.md) | [docs/benchmark.zh-CN.md](docs/benchmark.zh-CN.md) |
| 数据格式 | [docs/data_format.md](docs/data_format.md) | [docs/data_format.zh-CN.md](docs/data_format.zh-CN.md) |
| 评测流程 | [docs/evaluation.md](docs/evaluation.md) | [docs/evaluation.zh-CN.md](docs/evaluation.zh-CN.md) |

## 许可

- 代码：[Apache-2.0](LICENSE)
- 评测数据、标注与 prompt 资产：[CC BY 4.0](LICENSE-DATA)
- 任务输入中的第三方文件版权归原作者，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 引用

如使用 RAF 或 ClawBench，请引用论文（见 [CITATION.cff](CITATION.cff)）：

```bibtex
@inproceedings{raf2027,
  title     = {RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents},
  booktitle = {International Conference on Learning Representations (ICLR)},
  year      = {2027},
  url       = {https://github.com/RAFPAPER2026/RAF}
}
```

## 致谢

ClawBench 的部分任务场景参考或改编自公开的 Agent 评测项目，包括
[Claw-Eval](https://github.com/claw-eval/claw-eval) 与
[PinchBench](https://github.com/pinchbench/skill)。感谢这些项目的作者。

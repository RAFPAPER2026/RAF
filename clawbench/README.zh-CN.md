# ClawBench：长程个人助理 Agent 评测集与评测框架

ClawBench 是论文 **《RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents》** 配套发布的评测集：**121 个长程个人助理任务**，全部来自真实 OpenClaw 使用场景，每个任务都配有经过 RAF 生成与校验的 AND–OR 量规。**所有任务均按量规人工评分或由裁判 agent 评分**（`verifier_type` 恒为 `manual`），框架不自动给出规则分。

本目录同时包含基于 Docker 的评测框架：

> 任务配置（`config.json`）→ 编排器并行评测（起容器 → 初始化环境 → 下发任务 → 收集会话与工作区）→ 产出结果（`score.json` / `sessions.json` / `workspace/`）→ 人工打分页或裁判 agent 评分 → 分析器 / 报告页

评测集构成、分类与统计见 [docs/benchmark.zh-CN.md](../docs/benchmark.zh-CN.md)，数据结构见 [docs/data_format.zh-CN.md](../docs/data_format.zh-CN.md)，完整评测链路见 [docs/evaluation.zh-CN.md](../docs/evaluation.zh-CN.md)。

## 目录结构

```
clawbench/
├── main.py                    # CLI 入口（eval / run / analyze / visualize / rerun / judge）
├── src/
│   ├── orchestrator.py        # 任务编排与并行执行（ThreadPoolExecutor）
│   ├── runner.py              # 单任务生命周期（容器→初始化→请求→收集→清理）
│   ├── runs.py                # 多轮 run 存储/发现/平均 + result.json
│   ├── container_manager.py   # Docker 容器管理服务（FastAPI，端口 10800）
│   ├── container_client.py    # 容器管理 API 客户端 + gateway 客户端
│   ├── rubric/                # 量规模型与评分（单一事实来源）
│   ├── agent_scorer/          # 裁判 agent（Claude Agent SDK）
│   ├── analyzer/              # 结果分析（统计 / Excel 导出）
│   └── visualizer/            # 报告页后端（FastAPI）
├── manual_scorer/             # 人工打分页（FastAPI + React，端口 5002）
├── web/                       # 报告页前端（React，端口 4999）
├── configs/                   # trace_config.json / agent_scorer_config.json 等
├── docker/openclaw/           # 评测容器镜像构建文件与配置模板
├── tasks/                     # 121 个任务：config.json + config.en.json + init_env/
├── metadata/                  # tasks.jsonl 任务索引 + taxonomy.json 中英词表
├── tests/                     # 单元/集成测试（含数据集完整性检查）
└── results/                   # 结果输出目录（不入库）
```

## 前置条件

| 依赖 | 要求 |
|---|---|
| Python | 3.12+（`pyproject.toml` 要求 ≥3.11，仓库 `.python-version` 固定 3.12） |
| uv | 用于创建虚拟环境与运行所有 Python 命令 |
| Docker | 评测容器运行时；需能构建或加载 OpenClaw 镜像 |
| Node.js | 20+，用于构建报告页与人工打分页两个前端 |
| 模型端点 | 被测 Agent 需要一个 OpenAI 兼容端点（在 `tasks/openclaw.json` 中配置） |
| 裁判端点 | 可选的 Anthropic 兼容端点（仅裁判 agent 评分时需要） |

## 快速开始

以下命令在仓库根目录执行。

### 1. 安装依赖

```bash
cd clawbench
uv sync
```

### 2. 构建两个前端

报告页与人工打分页的 `dist/` 都不入库，首次使用必须构建：

```bash
cd web && npm install && npm run build && cd ..
cd manual_scorer/web && npm install && npm run build && cd ..
```

### 3. 准备 OpenClaw 评测镜像

镜像基于官方 `ghcr.io/openclaw/openclaw`，内置可启动 gateway 的占位模型 provider；真实评测时通过 `tasks/openclaw.json` 注入模型配置。二选一：

```bash
# 方式 A：本地构建（需要能访问官方镜像仓库）
docker build --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.4.2 \
  -t openclaw:base.4.2 docker/openclaw

# 方式 B：已有导出的镜像 tar 时直接加载
docker load -i docker/openclaw/dist/openclaw-base.4.2.tar
```

镜像构建细节、可选版本与自定义配置见 [`docker/openclaw/README.md`](docker/openclaw/README.md)。

### 4. 设置环境变量

```bash
# 必填：容器与评测客户端共用的 gateway token
export OPENCLAW_GATEWAY_TOKEN=<shared-token>

# 可选：切换镜像（默认 openclaw:base.4.2）
export OPENCLAW_IMAGE=openclaw:base.4.2

# 可选：容器内出网代理（模型端点在公网时需要）
export OPENCLAW_PROXY=http://<your-proxy>:<port>
```

### 5. 配置被测模型

```bash
cp openclaw.example.json tasks/openclaw.json
```

编辑 `tasks/openclaw.json` 中的 `models.providers`（`baseUrl` / `apiKey` / `models[].id`）与 `agents.defaults.model.primary`。整批任务共用一个配置文件；某个任务需要单独配置时，可在其 `config.json` 顶层加 `openclaw_config_path` 指向另一份 `openclaw.json`。

### 6. 启动容器管理服务

```bash
uv run python src/container_manager.py     # 端口 10800
```

容器管理服务负责容器的启停删查：每次评测为每个任务创建一个 `openclaw_worker_<8位十六进制>` 容器，随机映射宿主机端口到容器内 18789，并把该任务的工作区目录挂载到容器 `/root/Desktop`（`init_env/` 在启动后拷贝进该目录）。

### 7. 运行评测

```bash
# 评测 + 分析（--lang 默认 zh；--model-name 仅用于命名结果目录）
uv run python main.py run --tasks-dir tasks --model-name <model> --lang zh --workers 4

# 每任务跑 3 轮，用于 pass^k
uv run python main.py run --tasks-dir tasks --model-name <model> --runs 3 --workers 4

# 只评测、不分析
uv run python main.py eval --tasks-dir tasks --result-base-dir results --workers 4
```

> `--model-name` 只是结果目录的标签，实际调用的模型由 `tasks/openclaw.json` 决定。

### 8. 分析结果

```bash
# 对既有结果重新分析（输出 {result_dir}/analysis_report.xlsx）
uv run python main.py analyze --result-dir results/<model_dir> --tasks-dir tasks
```

`run` 命令在评测结束后会自动执行同样的分析。

### 9. 打开报告页

```bash
uv run python main.py visualize --result-dir results --port 4999
# http://127.0.0.1:4999
```

报告页提供仪表盘、模型对比、逐任务钻取（量规树结果、会话时间线、工作区预览）与结果导出。`visualize` 默认绑定 `127.0.0.1`（`--host` 可改），且没有鉴权，请勿暴露到公网。

### 10. 人工打分

```bash
uv run python manual_scorer/main.py --result-dir results --tasks-dir tasks --port 5002
# http://127.0.0.1:5002
```

人工打分页默认只绑定 `127.0.0.1`（可用 `--host` 修改），默认无鉴权。页面支持逐叶子勾选量规、写入人工总分/完成标记、查看 `sessions.json` 与下载 `workspace/`、上传结果压缩包，以及触发单个/批量裁判评分。

### 11. 裁判 agent 评分（可选）

1. 复制裁判凭据模板并填写端点与密钥：

   ```bash
   cp configs/claude_settings.example.json configs/claude_settings.json
   # 编辑其中的 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_MODEL
   ```

2. 对既有结果批量评分，并把结果采纳为 `manual_score`：

   ```bash
   uv run python main.py judge \
     --result-dir results/<model_dir> --tasks-dir tasks --adopt

   # 同时评过程质量、跳过已有裁判结果的任务
   uv run python main.py judge \
     --result-dir results/<model_dir> --tasks-dir tasks \
     --evaluate-trace --skip-existing --workers 4
   ```

   可用参数：`--evaluate-trace`（同时评过程质量维度）、`--skip-existing`（已有 `agent_review` 的任务跳过）、`--workers`（并发数，默认 1）、`--run-id`（默认 `run_1`）、`--agent-config`（默认 `configs/agent_scorer_config.json`）。

裁判参数见 [`configs/agent_scorer_config.json`](configs/agent_scorer_config.json)：`max_turns` 120、`timeout_seconds` 1800、`permission_mode` acceptEdits；`model` 为 `null` 时由凭据模板中的 `ANTHROPIC_MODEL` 决定。

## CLI 速查

以下命令在 `clawbench/` 目录下用 `uv run` 执行（如 `uv run python main.py run ...`）。

| 命令 | 作用 |
|---|---|
| `main.py eval --tasks-dir tasks --result-base-dir results --workers 4` | 只评测 |
| `main.py run --tasks-dir tasks --model-name <model> --workers 4` | 评测 + 分析 |
| `main.py rerun --result-dir results/<model_dir> --tasks-dir tasks` | 重跑失败任务到新 run |
| `main.py analyze --result-dir results/<model_dir> --tasks-dir tasks` | 导出 `analysis_report.xlsx` |
| `main.py visualize --result-dir results --port 4999` | 启动报告页 |
| `main.py judge --result-dir results/<model_dir> --tasks-dir tasks --adopt` | 批量裁判评分 |
| `manual_scorer/main.py --result-dir results --tasks-dir tasks --port 5002` | 启动人工打分页 |
| `src/container_manager.py` | 启动容器管理服务（10800） |
| `uv run pytest` | 运行测试（含数据集完整性检查） |

评测/分析/报告/评分/裁判命令共享两个参数：`--lang {zh,en}`（默认 `zh`）与 `--quality-aggregation {paper,legacy_mean}`（默认 `paper`）。

## 语言与评分口径

| 选项 | 取值 | 默认 | 说明 |
|---|---|---|---|
| `--lang` | `zh` / `en` | `zh` | `zh` 读 `config.json`；`en` 读 `config.en.json`，英文配置缺失时回退中文 |
| `--quality-aggregation` | `paper` / `legacy_mean` | `paper` | 质量分口径；`paper` 与论文公式一致，`legacy_mean` 兼容旧实现 |

- 英文配置是任务定义与量规的翻译版：节点 id、权重、树结构与中文版完全一致；输入文件（`init_env/`）保持中文不翻译，因此英文 prompt 中可能出现中文文件名/路径。
- 评分口径同样作用于人工打分页的实时预览与服务端重算；报告页对具体 run 使用服务端的 `rubric_results` 权威重算，避免前端口径漂移。
- 评分逻辑实现位置：`src/rubric/scoring.py`（Python，权威实现）、`web/src/rubric/scoring.ts`、`manual_scorer/web/src/lib/scoring.ts`。

## 技能与密钥配置

- **技能不随仓库分发**：121 个任务中 12 个需要 `baidu-search`（联网检索），1 个需要 `rapid-ocr-reader`（图片文字识别），共 13 个任务；其余 108 个任务无需外部技能。使用前把对应技能放到任务目录的 `init_env/.skills/<name>/` 下（评测时该目录挂载到容器 `/root/.openclaw/workspace/skills`）；`metadata/tasks.jsonl` 的 `required_skills` 记录了每个任务的技能需求。
- **模型配置**：写在 `tasks/openclaw.json`（从 `openclaw.example.json` 复制）的 `models.providers.<provider>.baseUrl/apiKey` 与 `agents.defaults.model.primary`；该文件不入库。
- **gateway token**：`OPENCLAW_GATEWAY_TOKEN` 由容器与评测客户端共用，必须一致；容器管理服务会把它注入容器，评测客户端用它做 Bearer 鉴权。
- **裁判凭据**：`configs/claude_settings.json`（含 `ANTHROPIC_AUTH_TOKEN`），不入库；模板为 `configs/claude_settings.example.json`。
- **成本统计**：默认价格表为空，token 成本记 0；可提供 `configs/model_prices.json`（或 `CLAWBENCH_MODEL_PRICES` 指定路径）按模型配置输入/输出价格。

| 文件 | 作用 | 是否入库 |
|---|---|---|
| `tasks/openclaw.json` | 被测模型端点与 API key | 否（gitignored） |
| `configs/claude_settings.json` | 裁判 agent 凭据 | 否（gitignored） |
| `configs/agent_scorer_config.json` | 裁判参数（`max_turns` 120、`timeout_seconds` 1800 等） | 是 |
| `configs/model_prices.json` | 可选 token 价格表 | 否（gitignored） |
| `OPENCLAW_GATEWAY_TOKEN` | 沙箱 gateway token，容器启动时注入 | 仅环境变量 |

## 结果目录与 pass^k

```
results/
└── {tasks目录名PascalCase}[EN]_{model}_{YYYYmmdd_HHMMSS}_{uuid8}/
    ├── result.json                 # 汇总（summary + 每个任务的 runs）
    ├── eval.log                    # 评测日志
    ├── analysis_report.xlsx        # analyze 后生成
    └── <task_id>/
        ├── run_1/                  # --runs k 时为 run_1 … run_k
        │   ├── score.json          # 指标 + 评分记录
        │   ├── sessions.json       # 执行轨迹
        │   ├── workspace/          # agent 交付物
        │   └── verifier/judge/     # 裁判 agent 产物（转录、证据、异常说明）
        └── run_2/ …
```

- 单轮结果的旧布局（`score.json` 直接位于 `<task_id>/` 下）仍受支持，读取时按 `run_1` 处理。
- 通过判定全链路一致：`complete_flag == 1` 即通过；旧数据无该键时回退 `score >= 0.75`（`configs/trace_config.json` 的 `pass_threshold`）。
- 多轮评测（`--runs k`）：每个 run 独立评分；`complete_flag = pass^k`，即**全部 k 轮都通过才为 1**；分析视图同时给出 `pass_at_1`（至少一轮通过）与 `pass_rate_over_runs`。
- 默认视图是虚拟的 `average` run（不是磁盘目录），可用 `--run-id` 选择具体 run；字段细节见 [数据格式](../docs/data_format.zh-CN.md)。
- 评测执行器只采集轨迹与工作区，**不写分数**；`score.json` 中的评分字段由人工打分页或裁判 agent 写入。

## 报告页与分析器

- `main.py analyze`：命令行分析，打印总体/分类/任务统计并导出 `analysis_report.xlsx`（含任务汇总、分类统计、总体统计三个 sheet）；多轮结果导出多轮工作簿。
- `main.py visualize`：报告页服务（端口 4999），提供仪表盘、模型对比与模型详情（逐任务钻取：量规树结果、会话时间线、工作区预览、裁判结果），支持结果导出。
- 过程质量维度（可选）：`configs/trace_config.json` 定义 4 个维度（任务理解、任务规划、工具调用、反思修复），由人工打分页或 `--evaluate-trace` 的裁判 agent 写入 `trace_quality`，仅用于分析，不参与总分。

## 已知限制

- **Docker 是必需的**：评测需要 Docker 与可用的 OpenClaw 镜像；镜像不随仓库分发，必须先构建或加载。
- **模型端点是必需的**：镜像只内置占位 provider，`tasks/openclaw.json` 必须指向可达的 OpenAI 兼容端点，否则模型调用失败。
- 任务输入文件与 `init_env/` 为中文且不翻译；英文模式只翻译任务定义与量规，prompt 中仍会出现中文文件名。
- 外部技能不随仓库分发：13 个任务需要 `baidu-search` / `rapid-ocr-reader`，其余 108 个任务无需技能。
- 裁判 agent 需要 Anthropic 兼容端点；仅支持 tree 格式量规（ClawBench 121 个任务均为 tree 格式）。
- 容器管理服务、报告页与人工打分页默认均绑定 `127.0.0.1`，且不内置鉴权；如需远程访问，请显式传 `--host` 并放在带鉴权的反向代理/防火墙之后。
- 任务配置中的 `timeout_seconds`（120–600 秒）用于描述任务预期时长；实际下发 gateway 请求的超时固定为 1800 秒，裁判 agent 的超时由 `configs/agent_scorer_config.json` 指定（默认 1800 秒）。
- 评测资源开销大：每个 job 一个容器，长程任务单轮可能接近超时上限，完整跑完 121 个任务通常需要数小时。
- 默认不内置模型价格，token 成本记 0；如需成本统计请提供 `configs/model_prices.json`。
- 旧格式只读兼容：flat 量规与旧评分文件可读、可分析，但裁判 agent 只支持 tree，迁移工具不还原旧分数。

## 测试

```bash
cd clawbench
uv run pytest
```

测试包含数据集完整性检查（121 个任务、1,920 个叶子 666/1,254、533 个组节点、权重 ⊆ `{1,2,3,4,6}`、顶层项均值 8.43、双语结构一致性、无敏感标识）与执行器配置、run 发现与平均、评分口径、裁判 agent、分析器、人工打分等单元测试。

## 许可与引用

评测数据、标注与 prompt 资产以 **CC BY 4.0** 发布（[`LICENSE-DATA`](../LICENSE-DATA)）；评测代码以 **Apache-2.0** 发布（[`LICENSE`](../LICENSE)）；`tasks/*/init_env/` 中的第三方文件保留原许可，见 [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)。使用 ClawBench 时请引用论文：

> RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents. ICLR 2027 submission. <https://github.com/RAFPAPER2026/RAF>

## 相关文档

- [ClawBench 评测集](../docs/benchmark.zh-CN.md)
- [数据格式](../docs/data_format.zh-CN.md)
- [评测流程](../docs/evaluation.zh-CN.md)
- [RAF 框架](../docs/framework.zh-CN.md)
- [镜像构建说明](docker/openclaw/README.md)

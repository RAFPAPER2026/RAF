# 评测流程

本篇说明 ClawBench 如何把一道任务跑成可评分的结果：容器生命周期、gateway 请求、轨迹与交付物收集、人工打分页与裁判 agent、通过判定与报告。命令见 [clawbench/README.zh-CN.md](../clawbench/README.zh-CN.md)。

## 链路总览

```
main.py run
  └─ Orchestrator：加载 121 个任务，线程池并行（--workers），每任务每轮一个 job
       └─ TaskRunner：单任务单轮
            1. 起容器（容器管理服务 /start）
            2. 初始化环境（拷贝 init_env/，执行 .scripts/，挂载 .skills/、.preset/）
            3. 等待 gateway 就绪 → POST /v1/chat/completions 下发任务
            4. 收集 sessions.json 与 workspace/
            5. 统计 token/成本/工具指标 → 写 score.json（status=completed/failed）
            6. 清理容器与 worker 目录
  └─ 每完成一个 job 重建 result.json → 评测结束自动 analyze（analysis_report.xlsx）

评分（异步、可后置）
  ├─ 人工打分页（manual_scorer，5002）→ 写 score.json（manual_score / complete_flag）
  └─ 裁判 agent（src/agent_scorer）→ 写 score.json 的 agent_review，可采纳为 manual_score
```

## 组件与端口

| 组件 | 入口 | 默认端口 | 说明 |
|---|---|---|---|
| 评测 CLI | `main.py` | — | `eval` / `run` / `analyze` / `visualize` / `rerun` / `judge` |
| 容器管理服务 | `src/container_manager.py` | 10800 | 管理评测容器；`main.py` 通过 REST 调用 |
| 被测 Agent gateway | 容器内 `openclaw gateway` | 容器 18789 → 宿主随机端口 | OpenAI 兼容 HTTP 接口 |
| 报告页 | `main.py visualize` | 4999 | 结果可视化与导出 |
| 人工打分页 | `manual_scorer/main.py` | 5002 | 人工评分、轨迹与工作区查看 |

## 前置配置

```bash
cd clawbench
uv sync

# 镜像：构建或加载（二选一）；可用 OPENCLAW_IMAGE 切换版本
docker build --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.4.2 \
  -t openclaw:base.4.2 docker/openclaw
# docker load -i docker/openclaw/dist/openclaw-base.4.2.tar

export OPENCLAW_GATEWAY_TOKEN=<shared-token>   # 必填，容器与客户端共用
export OPENCLAW_IMAGE=openclaw:base.4.2        # 可选

cp openclaw.example.json tasks/openclaw.json   # 再编辑 models.providers 与 agents.defaults.model.primary
```

- `OPENCLAW_GATEWAY_TOKEN` 由容器管理服务注入容器，评测客户端用同一 token 做 Bearer 鉴权；未设置时容器创建会返回错误。
- `OPENCLAW_PROXY` 可选：给容器注入 `http_proxy`/`https_proxy`，模型端点在公网且 Docker 网络受限时需要。
- 模型配置优先级：任务 `config.json` 顶层 `openclaw_config_path` > tasks 目录顶层 `openclaw.json` > 镜像内置占位 provider（模型调用会失败）。

## 容器生命周期

### 1. 创建容器

容器管理服务是包装 Docker CLI 的小型 FastAPI 服务（`src/container_manager.py`，端口 10800），可选启动参数：`--port`、`--workers-dir`、`--log-dir`。

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/health` | 存活检查 |
| POST | `/start` | 启动一个沙箱容器，返回 `{container_name, port, worker_path, config_path}` |
| GET | `/containers`、`/containers/{name}` | 列出 / 查看受管容器及其 Docker 状态 |
| POST | `/stop`、DELETE `/containers/{name}` | 停止 / 停止并删除容器 |

收到 `/start` 后执行（等价命令）：

```bash
docker run -d --name openclaw_worker_<8hex> \
  -l app=openclaw_worker \
  -p <随机端口>:18789 \
  -v <worker_path>:/root/Desktop \
  [-v <openclaw.json>:/root/.openclaw/openclaw.json] \
  [-v <init_env/.skills>:/root/.openclaw/workspace/skills] \
  [-v <init_env/.preset>:/root/.openclaw/workspace/presets] \
  -v <worker_path>/.openclaw_agents:/root/.openclaw/agents \
  -e OPENCLAW_GATEWAY_TOKEN=<token> \
  <image> bash -l -c "openclaw gateway"
```

| 宿主 | 容器内 | 说明 |
|---|---|---|
| `workspace/openclaw_workers/<name>` | `/root/Desktop` | 工作区；agent 的交付物写在这里 |
| `tasks/openclaw.json` 或任务级配置 | `/root/.openclaw/openclaw.json` | 模型与 gateway 配置 |
| `init_env/.skills/` | `/root/.openclaw/workspace/skills` | 任务所需技能（可选） |
| `init_env/.preset/` | `/root/.openclaw/workspace/presets` | 预设（可选） |
| `<worker>/.openclaw_agents/` | `/root/.openclaw/agents` | 会话转录挂载点，评测后读取轨迹 |

- 容器名 `openclaw_worker_<8位十六进制>`；宿主端口从 50000–65535 随机分配（线程安全 + 冲突重试）。
- 每次 `docker run` 失败会换端口重试，最多 3 次；容器内固定执行 `bash -l -c "openclaw gateway"`。

### 2. 初始化环境

`init_env/` 的拷贝规则：

| 子目录 | 处理方式 |
|---|---|
| 普通文件/目录 | 整体拷贝到 worker 目录（即容器 `/root/Desktop`） |
| `.scripts/` | **不拷贝**，在宿主机执行：`.sh` 用 `bash`，`.py` 用 `python3`（无 `python3` 时用当前解释器），工作目录为 worker 目录，单脚本超时 300 秒 |
| `.skills/` | 不拷贝，挂载到容器 `/root/.openclaw/workspace/skills` |
| `.preset/` | 不拷贝，挂载到容器 `/root/.openclaw/workspace/presets` |

没有 `init_env/` 的任务跳过该步骤。

### 3. 等待 gateway 并下发任务

- 容器启动后，评测端轮询 `http://127.0.0.1:<宿主端口>/healthz`，最长等待 120 秒。
- 就绪后向 gateway 发送 OpenAI 兼容请求：

```
POST http://127.0.0.1:<port>/v1/chat/completions
Authorization: Bearer <OPENCLAW_GATEWAY_TOKEN>
Content-Type: application/json

{"model": "openclaw", "messages": [{"role": "user", "content": "<任务 prompt>"}], "stream": false}
```

- 请求超时默认 1800 秒；被测模型由容器内 `openclaw.json` 决定，`--model-name` 只用于结果目录命名。

### 4. 收集轨迹与工作区

| 产物 | 来源 | 说明 |
|---|---|---|
| `sessions.json` | gateway 响应中的 `session` / `sessions`；为空时读取 worker `.openclaw_agents/` 挂载的最新非 `*.trajectory.jsonl` 转录文件 | 结构为 `{container, sessions: [...]}` |
| `workspace/` | 容器 `/root/Desktop`（worker 目录） | 排除 `.openclaw_agents` 后整体拷贝 |
| `score.json` | 框架写入 | 任务状态、耗时、token/成本/工具指标 |

### 5. 清理

- 删除容器（`docker stop` + `rm`）；成功任务的 worker 目录也会删除（失败任务保留 worker 目录便于排查）。
- 容器不保留，评测证据只保留在结果目录的 `sessions.json` 与 `workspace/`。

## 运行评测

```bash
cd clawbench

# 评测 + 分析
uv run python main.py run --tasks-dir tasks --model-name <model> --lang zh --workers 4

# 只评测
uv run python main.py eval --tasks-dir tasks --result-base-dir results --workers 4

# 每任务跑 3 轮（pass@k）
uv run python main.py run --tasks-dir tasks --model-name <model> --runs 3 --workers 4
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--tasks-dir` | 必填 | 子目录各含 `config.json` 的任务目录 |
| `--result-base-dir` | `results` | 结果目录的基目录 |
| `--workers` | 4 | 并行 job 数（任务 × 轮次） |
| `--model-name` | 无 | 写入结果目录名；填被测模型名 |
| `--runs` | 1 | 每任务重复轮数（pass@k） |
| `--retries` | 0 | 状态非 `completed` 的任务/轮次的额外尝试次数 |
| `--lang` | `zh` | `zh` 读 `config.json`；`en` 读 `config.en.json`（缺失回退中文） |
| `--quality-aggregation` | `paper` | 质量分口径（`paper` / `legacy_mean`） |

评测结果写入 `results/<tasks>[_EN]_<model>_<timestamp>_<uuid8>/`；任务在线程池中并行执行（每个 job 一个容器）。失败任务可以重跑进新的 run 目录而不重做已完成的任务：

```bash
uv run python main.py rerun --result-dir results/<model_dir> --tasks-dir tasks
```

评测日志同时输出到控制台与 `{result_dir}/eval.log`（含任务/轮次进度与验证结果）。

## 人工打分页

```bash
uv run python manual_scorer/main.py --result-dir results --tasks-dir tasks --port 5002
# http://127.0.0.1:5002
```

| 项 | 说明 |
|---|---|
| 绑定地址 | 默认 `127.0.0.1`（`--host` 可改），**默认无鉴权** |
| 模型列表 | 盲评别名：按固定种子生成“模型 A / B / …”，映射持久化在 `results/.name_mapping.json` |
| run 选择 | 默认最新 run（`run_<max>`），可切到任意 run 或 `average` 视图 |
| 评分 | tree 格式量规逐叶子勾选，实时预览 `paper` / `legacy_mean` 两种口径的分数 |
| 人工记录 | 保存 `manual_score`、`complete_flag`、`manual_feedback`（好/差）、`doubtful`（存疑） |
| 过程维度 | 可填写 `trace_quality` 的 4 个维度（任务理解/任务规划/工具调用/反思修复），仅分析用 |
| 轨迹与交付物 | 查看 `sessions.json` 时间线、浏览/预览/下载 `workspace/` 文件（ZIP） |
| 上传结果 | 支持上传 `.zip` / `.rar` 结果包，检查冲突后导入指定 run（暂存会话有 TTL） |
| 裁判评分 | 单任务/批量触发裁判 agent、轮询状态、采纳结果 |

启动参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--result-dir` | `results` | 含模型结果目录的目录 |
| `--tasks-dir` | 无 | 任务定义（渲染量规与 prompt 需要） |
| `--port` | 5002 | HTTP 端口 |
| `--host` | `127.0.0.1` | 绑定地址；默认仅本机可访问 |
| `--agent-config` | `configs/agent_scorer_config.json` | 裁判 agent 配置 |
| `--lang` | `zh` | 任务定义语言 |
| `--quality-aggregation` | `paper` | 表单预览与服务端重算的默认质量分口径 |

主要 REST 接口（均在 `/api` 下）：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/models`、`/stats` | 模型列表与全局统计 |
| GET | `/model/{model_id}/runs` | run 列表与默认 run |
| GET | `/model/{model_id}/tasks?run_id=` | 任务列表与分数（`run_id=average` 为平均视图） |
| GET | `/model/{model_id}/task/{task_name}?run_id=` | 任务详情（`score` + `config` + `sessions`） |
| POST | `/model/{model_id}/task/{task_name}/score` | 保存评分（tree / flat / 直接分数三种模式） |
| PATCH | `.../complete-flag`、`.../manual-feedback`、`.../doubtful` | 更新完成标记 / 好差标记 / 存疑标记 |
| POST | `.../trace-quality` | 保存过程维度评分 |
| GET | `.../workspace/files`、`.../workspace/file`、`.../workspace` | 文件树 / 单文件 / ZIP 下载 |
| POST | `.../agent-eval`、`.../batch-agent-eval` | 单任务 / 批量裁判评分 |
| POST | `.../agent-eval/adopt` | 采纳裁判结果 |
| POST | `/model/{model_id}/upload/check`、`/upload/confirm` | 导入结果压缩包 |

## 裁判 agent

### 配置与凭据

```bash
cp configs/claude_settings.example.json configs/claude_settings.json
# 编辑 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_MODEL
```

- 裁判基于 `claude-agent-sdk`（`claude-agent-sdk==0.2.98`），需要 Anthropic 兼容端点。
- 运行参数在 `configs/agent_scorer_config.json`：

| 字段 | 当前值 | 说明 |
|---|---|---|
| `settings_path` | `configs/claude_settings.json` | 凭据设置文件；相对路径以 `clawbench/` 为基准，作为 SDK `settings` 选项传入 |
| `model` | `null` | 为 `null` 时使用凭据设置中的模型 |
| `max_turns` | 120 | 单次评测最大会话轮数 |
| `timeout_seconds` | 1800 | 单任务评测超时（超时由外部 `asyncio.wait_for` 强制） |
| `permission_mode` | `acceptEdits` | SDK 权限模式 |

### 工作流

1. 资格检查：任务必须是 `manual`、量规必须是 tree 格式、run 必须存在；（`--skip-existing` 时）任务不得已有 `agent_review`。
2. 组装 system prompt：`role` → `workflow` → `deliverables` → `exceptions` → `rules` → `output_format`，`--evaluate-trace` 时追加 `trace_quality` 模板；prompt 为该语言版本，缺失回退中文。
3. 组装 user prompt：原始任务 query、任务目录、结果目录、执行轨迹元信息（权威执行日期、工具调用序列）、以缩进文本渲染的完成/质量量规树（每个节点带 `[node-id]`）。
4. 裁判 agent 阅读 `sessions.json` 与 `workspace/` 中的实际交付物，逐叶子判定。
5. 输出结构化结果，写入 `score.json` 的 `agent_review`；`needs_human_review=true` 时同时把 `doubtful` 置为 `true`（只增不减）。

### 输出 schema

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `rubric_results` | object | 是 | `{leaf_id: {passed: bool, reasoning: string}}`，必须覆盖**全部**叶子 id |
| `confidence` | number | 是 | 整体置信度，`0.0–1.0` |
| `time_analysis` | string | 是 | 时间窗口的逐项分析记录（非空） |
| `info_fidelity_analysis` | string | 是 | 搜索信息忠实性的逐项分析记录（非空） |
| `needs_human_review` | boolean | 是 | 是否需要人工复核 |
| `review_notes` | string | 是 | 复核原因说明（非空；无需复核时写“无需人工复核”） |
| `trace_quality` | object | 条件 | 仅 `--evaluate-trace` 时必填；4 个维度取值 `0.0/0.25/0.5/0.75/1.0` |

校验规则：缺叶子、`passed` 非布尔、`reasoning` 为空、`confidence` 越界、必填分析字段为空、维度取值不合法都会判定本次评测失败；批量/CLI 路径会自动重试一次，仍失败则标记为失败（超时标记为 timeout）。

### 产物

```
<task_id>/run_<n>/verifier/judge/
├── agent_judge.jsonl     # SDK 消息逐条转录（type + timestamp）
├── exceptions.md         # 评分异常说明（裁判按 prompt 要求创建）
└── proof/                # 评估证据（如网页截图，裁判按需创建）
```

### 采纳与 CLI

```bash
# 对结果目录下所有模型目录批量裁判，并把结果采纳为 manual_score
uv run python main.py judge --result-dir results/<model_dir> --tasks-dir tasks --adopt

# 同时评过程质量、跳过已有裁判结果的任务，4 并发
uv run python main.py judge --result-dir results/<model_dir> --tasks-dir tasks \
  --evaluate-trace --skip-existing --workers 4 --run-id run_1
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--result-dir` | 必填 | 模型目录或其父目录 |
| `--tasks-dir` | 必填 | 任务目录 |
| `--run-id` | `run_1` | 评分的 run |
| `--workers` | 1 | 并发数 |
| `--evaluate-trace` | 关 | 同时评 4 个过程质量维度 |
| `--skip-existing` | 关 | 已有 `agent_review` 的任务跳过 |
| `--adopt` | 关 | 采纳为 `manual_score` |
| `--agent-config` | `configs/agent_scorer_config.json` | 裁判配置路径 |

采纳逻辑：由 `rubric_results` 重新计算完成度与质量分（`score = round(quality_score, 4)`），写入 `manual_score`、`complete_flag`、`rubric_results`、`manual_scored_by="agent"`、`adopted_agent_timestamp`，并写入 `manual_comment`（逐叶子的 ✓/✗ 与理由）；`needs_human_review=true` 时同时把 `doubtful` 置为 `true`（只增不减）。

## 评分口径

| 口径 | AND 组 | OR 组 | 顶层 | 默认 |
|---|---|---|---|---|
| `paper` | 全部子节点通过才得 1，否则 0 | 取最大值 | 按权重加权平均 | 是 |
| `legacy_mean` | 取子节点均值 | 取最大值 | 按权重加权平均 | 否 |

- CLI：`--quality-aggregation {paper,legacy_mean}`；人工打分页 `--quality-aggregation` 同时作用于实时预览与服务端重算。
- 完成度始终为二元，不受口径影响。
- 实现位置（修改需同步）：
  - Python（权威）：`clawbench/src/rubric/scoring.py`（`compute_rubric_score`）
  - TypeScript：`clawbench/web/src/rubric/scoring.ts`、`clawbench/manual_scorer/web/src/lib/scoring.ts`
  - RAF 侧同口径实现：`raf/rubric/scoring.py`、`raf/frontend/src/lib/scoring.ts`
- 报告页/人工打分页对具体 run 会用服务端 `rubric_results` 权威重算，避免前端口径与持久化值漂移。

## 通过判定与 pass^k

| 场景 | 规则 |
|---|---|
| 单轮 | `complete_flag == 1` 即通过；`0` 即未通过 |
| 旧数据（无 `complete_flag` 或为 `null`） | 回退 `score >= 0.75`（`configs/trace_config.json` 的 `pass_threshold`；兼容旧键 `legacy_threshold`，缺省 0.75） |
| 多轮（`--runs k`） | 每个 run 独立判定；`complete_flag = pass^k`（全部 k 轮通过才为 1），同时提供 `pass_at_1`（至少一轮通过）与 `pass_rate_over_runs`（通过轮数 / k） |
| 平均视图 | `run_id=average` 对多个 run 求均值（`status` 需按严格多数判定；损坏 run 跳过） |

结果目录与平均逻辑见 [数据格式](data_format.zh-CN.md)；`rerun` 会为重跑的任务追加 `run_<max+1>`，不覆盖既有 run。

## 报告页与分析器

```bash
# 命令行分析：打印总体/分类/任务统计，导出 {result_dir}/analysis_report.xlsx
uv run python main.py analyze --result-dir results/<model_dir> --tasks-dir tasks

# 报告页（默认绑定 127.0.0.1:4999，--host 可改）
uv run python main.py visualize --result-dir results --port 4999
```

- 分析器默认读取 `run_id="average"`；多轮结果（`max_run > 1`）导出多轮工作簿。
- `analysis_report.xlsx` 默认包含三个 sheet：**任务汇总**（逐任务的完成标记、分数、耗时、token/成本、工具/API 统计、分类标签，以及提供 `--tasks-dir` 时的配置派生列）、**分类统计**（按主场景/子场景/能力/难度/复杂度统计任务数、平均分与通过率）、**总体统计**（总体指标、平均分、通过率、耗时、token、成本、工具成功率、错误恢复率与过程质量维度）。
- 报告页有三个视图：**仪表盘**（聚合指标、分布、各模型分数条形图）、**模型对比**、**模型详情**（逐任务钻取：分数、量规树结果、会话时间线、工作区预览、裁判结果、多轮明细），并提供 Excel 导出。
- 报告页在服务端用权威评分模块从 `rubric_results` 重新推导分数；报告页与分析器使用同一套通过判定与阈值，因此数字与 `score.json` 一致。
- 过程质量维度定义在 `configs/trace_config.json`（任务理解、任务规划、工具调用、反思修复，各 5 级），仅用于分析，不进入总分。

## 安全注意事项

- **`OPENCLAW_GATEWAY_TOKEN` 是共享密钥**：容器与评测客户端必须一致；不要写入仓库、日志或截图。
- **默认无鉴权**：容器管理服务、报告页与人工打分页默认均绑定 `127.0.0.1`，不内置登录鉴权；如需远程访问，请显式传 `--host` 并放在带鉴权的反向代理/防火墙之后。
- **凭据文件不入库**：`configs/claude_settings.json`（裁判 token）、`tasks/openclaw.json`（模型 apiKey）已被 `.gitignore` 排除。
- **结果目录含任务数据与 Agent 输出**：`results/` 不入库，分发前请自行检查合规性。
- 评测容器以 root 运行并挂载任务输入，仅用于运行本仓库的受信任务集；不要用不可信的 `init_env/` 或配置运行。
- 优先使用 HTTPS 模型端点；若端点位于私有网络，请自行评估网络隔离策略。
- 人工打分页会拒绝工作区路径穿越，并对上传与文件访问做大小限制。

## 排错

前端未构建、Docker 不可用、gateway token、模型端点、代理与包源等常见问题，见 [clawbench/README.zh-CN.md](../clawbench/README.zh-CN.md) 的“已知限制”一节。

## 相关文档

- [数据格式](data_format.zh-CN.md)
- [ClawBench 评测集](benchmark.zh-CN.md)
- [clawbench/README.zh-CN.md](../clawbench/README.zh-CN.md)

# RAF：量规自动生成与迭代平台

本目录是论文 **《RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents》** 中 RAF 框架的官方实现。它是一个面向 AI Agent 评测的量规（rubric）生成与管理平台：输入用户 query，由 LLM 生成结构化的 AND–OR 量规（完成量规 + 质量量规），并支持量规编辑、人工审核、评分记录、与人类偏好的一致性计算，以及“专家审核建议 → 采纳 → PROMPT-R 精炼”的迭代优化闭环。

平台定位与论文中的 RAF 五步一致：**生成 → 专家审核 → 评分记录 → 终止判定 → 建议/采纳/精炼**。量规的最终“认证”依据是人类偏好一致性指标（Alignment = 0.8 × Pearson + 0.2 × QWK）；评测执行（Docker 容器、被测 agent、裁判 agent、报告页）由仓库中的 [`clawbench/`](../clawbench/) 负责。

| 论文步骤 | 平台中的实现 |
|---|---|
| 生成 | 七模块 prompt 驱动 LLM 生成完成量规（二元树）与质量量规（加权树）；支持单条/批量生成 |
| 专家审核 | 逐条量规 1–5 星评分与备注；优化轮次内整批 `approved` / `rejected` 质量初筛 |
| 评分记录 | 优化轮次的评分表：每条量规一个人工 gold 分 + 每位评分者的分数 |
| 终止判定 | 计算 Pearson / Spearman / QWK / Composite，并按达标、收敛、预算、退化规则判断 |
| 建议/采纳/精炼 | RIFT 诊断给出失败模式与模块级建议；人工采纳后 LLM 精炼出新的 prompt 版本，回到下一轮 |

框架原理、评分公式与指标定义见 [docs/framework.zh-CN.md](../docs/framework.zh-CN.md)。

## 主要功能

- **量规自动生成**：7 模块 prompt（`role → structure → principles → examples → constraints → capabilities → output`）驱动 LLM 生成 AND–OR 量规树，用结构化输出 JSON Schema 约束返回格式。
- **Prompt 版本管理**：内置 `v5.1`（生成 ClawBench 量规所用版本）与 `v5.10`（最新版本），提供中英文两版；支持版本对比、克隆、模块编辑与激活。
- **树形量规编辑**：前端可视化编辑 leaf / AND 组 / OR 组，质量量规顶层项带权重输入。
- **评分记录**：逐叶子勾选，实时计算完成度（二元）与质量分（加权，0–1），支持 `paper` / `legacy_mean` 两种口径。
- **人工审核**：对单条量规给出完成/质量 1–5 星评分与备注，按 prompt 版本聚合统计。
- **PROMPT-R 优化**：以轮次组织“生成 → 人工质量初筛 → 评分与指标 → RIFT 诊断 → 建议采纳 → 精炼新版本 → 中止判断”的迭代。
- **RIFT 质量诊断**：识别 8 种量规失败模式（主观、非原子、无依据、目标-过程混淆、意图遗漏、可 hack、低区分、冗余）。
- **一致性指标**：Pearson r、Spearman ρ、QWK、Composite，以及逐 query 偏差。
- **Query 管理**：集中管理 query、标签，支持 Excel / JSON 导入导出与从既有量规迁移。
- **双语资产**：中文与英文的生成 prompt、能力项列表；`RAF_LANG` / `--lang` 选择语言，英文缺失时回退中文。
- **文件型存储**：`data/` 下的 JSON 存储，无需数据库；UI 与 API 共用同一份数据。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ / FastAPI / Pydantic v2 / OpenAI SDK / numpy / scipy |
| 前端 | React 18 / TypeScript / Vite / Tailwind |
| 存储 | 文件型 JSON（`data/` 目录），无数据库 |
| 包管理 | uv（Python）+ npm（前端） |

## 快速开始

前置条件：Python 3.11+、[uv](https://docs.astral.sh/uv/)、Node.js 20+，以及一个 OpenAI 兼容的 LLM 端点。

```bash
cd raf
uv sync
# 前端构建产物不入库，必须构建（后端 app.py 托管 frontend/dist）
cd frontend && npm install && npm run build && cd ..

# 配置 LLM：环境变量优先（下例），也可以写 data/llm_config.json
export RAF_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
export RAF_LLM_API_KEY=your-key
export RAF_LLM_MODEL=your-model

uv run python app.py            # http://localhost:8081
```

打开 <http://localhost:8081>。首次启动会自动写入演示数据（2 条 query、2 条量规、1 条审核），让各页面都有内容可看。开发模式下也可以 `cd frontend && npm run dev`（Vite 端口 5173，`/api` 代理到 8081）。

### LLM 配置

两种方式任选其一，环境变量优先：

| 方式 | 说明 |
|---|---|
| 环境变量 | `RAF_LLM_BASE_URL` / `RAF_LLM_API_KEY` / `RAF_LLM_MODEL`；可选 `RAF_LLM_TIMEOUT`（秒） |
| `data/llm_config.json` | 模板见 [`configs/llm_config.example.json`](configs/llm_config.example.json)，复制为 `data/llm_config.json` 后填写；支持键：`base_url`、`api_key`、`model`、`temperature`、`max_tokens`、`timeout`；该文件不入库 |

配置在每次调用时重新读取，修改后无需重启服务。

## 量规结构速览

每条量规（`QueryRubric`）包含两棵相互独立的树：

| 维度 | 结构 | 判定方式 |
|---|---|---|
| 完成量规 `completion_rubric` | 顶层项列表（无权重） | 二元：顶层项全部通过才算任务完成 |
| 质量量规 `quality_rubric` | 顶层项列表，每项 `{weight, node}` | 连续：叶子 1/0，OR 取 max，AND 按口径聚合，顶层按权重加权平均 |

- 节点：`{id, type: leaf|group, name, combinator: and|or, children, tags}`；group 不能带 `tags`，叶子需填写能力项标签。
- 禁止单子节点 group；AND 组用于同一实体/维度下的多个条件，OR 组用于多条可接受路径。
- 质量顶层项权重为“重要性（1/2/3）× 难度（1/2）”，合法值仅 `{1, 2, 3, 4, 6}`。

## Prompt 版本与语言

Prompt 由 7 个模块按固定顺序拼接：`role → structure → principles → examples → constraints → capabilities → output`。每个版本是 `data/prompt_versions/<version>.json` 中的一个 JSON 记录，包含版本号、父版本、变更说明、可选的指标摘要与 7 个模块文本。

| 版本 | 父版本 | 说明 |
|---|---|---|
| `v5.1` | `v5` | 微调 AND 组使用规则；**构建 ClawBench 全部 121 个任务量规所用的版本**。版本记录中的迭代指标为 Pearson 0.65 / QWK 0.57 / Composite 0.634（50 条 query、3 位评分者） |
| `v5.10` | `v5.9` | 最新版本，默认活跃版本；由 PROMPT-R 精炼 `structure`、`principles`、`constraints`、`output` 四个模块得到 |

- 英文资产：`data/prompt_versions/<version>.en.json` 与 `data/capabilities.en.txt`；缺失时回退中文。
- 能力项列表：`data/capabilities.txt`（12 项），运行时注入 prompt 的 `{capabilities}` 占位符。
- 活跃版本记录在 `data/active_prompt_version.txt`（默认 `v5.10`），也可在页面或 API 中切换。
- 语言选择：环境变量 `RAF_LANG`（默认 `zh`）；生成 CLI 另支持 `--lang {zh,en}`。

## CLI

单条生成：

```bash
cd raf
uv run python generate_rubric.py "查看我本周的日程安排，有会议冲突帮我调整一下" \
  --prompt-version v5.10
# 英文量规
uv run python generate_rubric.py "Plan my week and resolve meeting conflicts" \
  --prompt-version v5.10 --lang en
# 只生成、不保存
uv run python generate_rubric.py "帮我总结这份文档" --no-save
```

批量生成（默认从 `data/usecase/*.txt` 读取 query，每行一条；会先删除同 `(query, prompt_version, language)` 的旧记录）：

```bash
uv run python batch_generate.py --input queries.txt --prompt-version v5.10 --concurrency 8
```

列出 query：

```bash
uv run python list_queries.py -v
```

| 命令 | 作用 |
|---|---|
| `uv run python app.py` | 启动平台服务（`http://localhost:8081`） |
| `uv run python generate_rubric.py "<query>"` | 对单条 query 生成量规 |
| `uv run python batch_generate.py --input <file>` | 批量生成量规 |
| `uv run python list_queries.py -v` | 列出集中管理的 query |

## 评分口径

质量分支持两种口径，默认 `paper`（与论文公式一致）：

| 口径 | 规则 |
|---|---|
| `paper`（默认） | 叶子勾选得 1、未勾选得 0；OR 组取子节点最大值；AND 组**所有子节点都通过才得 1，否则 0**；顶层按权重加权平均 |
| `legacy_mean` | 兼容早期实现：AND 组取子节点均值（部分得分），OR 仍取最大值 |

- 完成度始终为二元：所有完成量规顶层项通过才记完成（`complete_flag = 1`），总分 `score` 取质量分。
- 评分页可在下拉框中切换口径；服务端默认值可用环境变量 `CLAWBENCH_SCORING_MODE` 覆盖（该口径名与 ClawBench 共用，保证两套组件一致）。
- 评分逻辑有 Python 与 TypeScript 双份实现（`rubric/scoring.py` 与 `frontend/src/lib/scoring.ts`），修改需同步。

```bash
# 例：服务端默认使用兼容口径启动平台
CLAWBENCH_SCORING_MODE=legacy_mean uv run python app.py
```

## 一致性指标

| 指标 | 含义 |
|---|---|
| Pearson r | 与人类偏好（gold）的排序/线性一致性 |
| Spearman ρ | 秩相关 |
| QWK | 二次加权 Kappa：分数离散到 5 级后计算等级一致性 |
| Composite | `0.8 × Pearson + 0.2 × QWK`，即论文中的 Alignment Score |
| 逐 query 偏差 | 评分者均值 − gold，用于定位异常 query |

## 页面

| 路由 | 页面 | 功能 |
|---|---|---|
| `/list` | 量规列表 | 搜索/去重/版本数/审核统计；进入评分、审核、编辑、版本对比 |
| `/builder` | 量规构建 | 新建/编辑量规，树形编辑（质量顶层项带权重） |
| `/scorer` | 评分 | 逐叶子勾选，实时展示完成度与质量分 |
| `/review/:id` | 审核 | 只读量规树 + 完成/质量 1–5 星 + 备注 |
| `/prompts` | Prompt 版本 | 版本列表、模块 diff、克隆、激活、模块编辑 |
| `/optimize` | 优化实验 | PROMPT-R 轮次工作台：初筛、评分、指标、RIFT 诊断、建议采纳、中止判断 |
| `/queries` | Query 管理 | Query 增删改查、标签、Excel 导入导出 |

UI 为中文。

## 数据文件

| 路径 | 说明 |
|---|---|
| `data/rubrics.json` | 量规记录（仓库内为 2 条演示数据） |
| `data/queries.json` | 集中管理的 Query（2 条演示数据） |
| `data/reviews.json` | 人工审核记录（1 条演示数据） |
| `data/prompt_versions/*.json` | Prompt 版本（`v5.1`、`v5.10` 及英文版） |
| `data/capabilities.txt` / `data/capabilities.en.txt` | 能力项列表（中英各 12 项） |
| `data/active_prompt_version.txt` | 当前活跃 prompt 版本 |
| `data/llm_config.json` | LLM 配置，**不入库**（含 API key） |
| `data/optimization_runs/` | PROMPT-R 优化运行记录，**不入库** |
| `data/usecase/*.txt` | `batch_generate.py` 的默认输入（每行一条 query，可选、可不入库） |
| `frontend/dist/` | 前端构建产物，**不入库**，需执行 `npm run build` |

## 限制

- 需要可用的 OpenAI 兼容 LLM 端点；未配置时生成、诊断与精炼都会失败，没有离线模板兜底。
- **无鉴权**：平台默认监听 `127.0.0.1:8081`（可用 `RAF_HOST` / `RAF_PORT` 修改），没有登录层，请只在受信网络使用。
- 文件型 JSON 存储、无数据库，定位为单节点研究平台，不适合多用户并发部署。
- 前端必须构建后才能使用页面；只调用 API 时可省略构建。
- 页面 UI 文案为中文；prompt 资产与生成的量规可通过 `--lang en` / `RAF_LANG=en` 产出英文，但界面语言不变。
- 仓库只带 2 条演示量规；完整的 121 条 ClawBench 量规在 [`clawbench/tasks/`](../clawbench/tasks/)。
- 英文 prompt 资产缺失时自动回退中文；生成/诊断使用 LLM，输出具有随机性，同一 query 与版本得到的是同风格量规而非逐字相同结果。
- 一致性指标至少需要 2 条已评分的量规；单条量规仍可用 RIFT 诊断。
- 平台不执行 Agent 评测；容器编排、被测模型与裁判评分见 [clawbench/README.zh-CN.md](../clawbench/README.zh-CN.md)。

## 测试

```bash
cd raf
uv run pytest
```

测试覆盖指标计算、两种评分口径、prompt 模块拼接与 LLM 客户端配置。

## 许可与引用

代码以 **Apache-2.0** 发布（见 [`LICENSE`](../LICENSE)）；benchmark 数据、标注与 prompt 资产以 **CC BY 4.0** 发布（见 [`LICENSE-DATA`](../LICENSE-DATA)）。使用 RAF 时请引用论文：

> RAF: Rubric Auto-generation Framework for Auditable Evaluation of Long-Horizon LLM Agents. ICLR 2027 submission. <https://github.com/RAFPAPER2026/RAF>

## 相关文档

- [RAF 框架原理](../docs/framework.zh-CN.md)
- [ClawBench 评测集](../docs/benchmark.zh-CN.md)
- [数据格式](../docs/data_format.zh-CN.md)
- [评测流程](../docs/evaluation.zh-CN.md)

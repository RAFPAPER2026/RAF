"""prompt + JSON schema 组装。

- system prompt = role + workflow + deliverables + exceptions + rules + output_format
  六段按顺序拼接（`_load_section` 每次读盘、热加载无缓存）；`evaluate_trace=True` 时再追加
  trace_quality.md 模板。system prompt **完全 case-agnostic**（无路径、无 rubric 树、无叶子 id）
- user prompt 为纯 f-string 拼接（六段）；rubric 树以缩进文本注入
- 输出 schema：按叶子 id 的密封对象（additionalProperties:false 对多余 key 触发模型重试）

`rubric.md` 是废弃模板（无代码加载，rubric 树已移入 user prompt）。
"""

from __future__ import annotations

from string import Template
from pathlib import Path
from typing import Any, Optional

from src.agent_scorer.trace_meta import TraceMeta, extract_trace_meta
from src.i18n import current_language
from src.rubric.models import QueryRubric, RubricNode
from src.rubric.scoring import collect_leaf_ids

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# 与 configs/trace_config.json 一致的 4 个过程评价维度
DEFAULT_TRACE_DIMENSIONS = [
    {"key": "task_understanding", "name": "任务理解", "name_en": "Task Understanding", "levels": 5},
    {"key": "task_planning", "name": "任务规划", "name_en": "Task Planning", "levels": 5},
    {"key": "tool_usage", "name": "工具调用", "name_en": "Tool Usage", "levels": 5},
    {"key": "reflection_recovery", "name": "反思修复", "name_en": "Reflection & Recovery", "levels": 5},
]

SYSTEM_SECTIONS = ("role", "workflow", "deliverables", "exceptions", "rules", "output_format")

_TRACE_DIMENSION_KEYS = tuple(d["key"] for d in DEFAULT_TRACE_DIMENSIONS)
_TRACE_DIMENSION_VALUES = [0.0, 0.25, 0.5, 0.75, 1.0]


def _load_section(name: str, lang: str | None = None) -> str:
    """从 `prompts/{lang}/{name}.md` 读盘；英文缺失时回退中文模板。"""
    language = current_language(lang)
    candidate = PROMPTS_DIR / language / f"{name}.md"
    if not candidate.is_file():
        candidate = PROMPTS_DIR / f"{name}.md"
    return candidate.read_text(encoding="utf-8").strip()


def build_system_prompt(
    query_rubric: QueryRubric, evaluate_trace: bool = False, lang: str | None = None
) -> str:
    """六段按顺序拼接；`evaluate_trace=True` 时追加 trace_quality 模板
    （`$trace_dimensions_desc` 替换为 4 个过程评价维度的列表行）。
    """
    language = current_language(lang)
    parts = [_load_section(name, language) for name in SYSTEM_SECTIONS]
    if evaluate_trace:
        name_key = "name_en" if language == "en" else "name"
        dims_desc = "\n".join(
            f"{dim[name_key]} ({dim['key']}): 0.0/0.25/0.5/0.75/1.0"
            for dim in DEFAULT_TRACE_DIMENSIONS
        )
        parts.append(
            Template(_load_section("trace_quality", language)).substitute(
                trace_dimensions_desc=dims_desc
            )
        )
    return "\n\n".join(parts)


def _render_tree(node: RubricNode, indent: int = 0, weight: Optional[float] = None,
                 prefix: str = "✦ ", lang: str | None = None) -> list[str]:
    """把 rubric 树递归渲染为缩进文本：
    - 顶层节点前缀 `✦ `，子节点按层级缩进，用 `├─ ` 连接，每层最后子节点改用 `└─ `
    - 叶子行形如「节点名 [id] — 叶子节点」；顶层叶子带权重时追加「, 权重 N」
    - 组行形如「节点名 [id] — AND 组」或「节点名 [id] — OR 组」（combinator 大写）
    """
    language = current_language(lang)
    if node.type == "leaf":
        kind = "leaf" if language == "en" else "叶子节点"
    else:
        kind = f"{node.combinator.upper()} group" if language == "en" else f"{node.combinator.upper()} 组"
    suffix = ""
    if weight is not None and indent == 0 and node.type == "leaf":
        suffix = f", weight {weight:g}" if language == "en" else f", 权重 {weight:g}"
    lines = [f"{'  ' * indent}{prefix}{node.name} [{node.id}] — {kind}{suffix}"]
    for i, child in enumerate(node.children):
        connector = "└─ " if i == len(node.children) - 1 else "├─ "
        lines.extend(_render_tree(child, indent + 1, prefix=connector))
    return lines


def _render_tree_text(node: RubricNode, weight: Optional[float] = None, lang: str | None = None) -> str:
    """`_render_tree` 输出的缩进文本（多行）。"""
    return "\n".join(_render_tree(node, weight=weight, lang=lang))


def render_completion_tree(rubric: QueryRubric, lang: str | None = None) -> str:
    return "\n".join(_render_tree_text(node, lang=lang) for node in rubric.completion_rubric)


def render_quality_tree(rubric: QueryRubric, lang: str | None = None) -> str:
    return "\n".join(
        _render_tree_text(item.node, item.weight, lang=lang) for item in rubric.quality_rubric
    )


def _wrap_payload(label: str, payload: str) -> str:
    """`query`/`detail` 单行时内联「label: 值」；多行时以 4 空格缩进包裹
    （避免内容串进下一条调用行），格式为「label:」后接 4 空格缩进的对齐内容。
    """
    if "\n" not in payload:
        return f" {label}: {payload}"
    indented = "\n".join(f"    {line}" for line in payload.splitlines())
    return f" {label}:\n{indented}"


def _render_trace_meta(trace_meta: Optional[TraceMeta], lang: str | None = None) -> str:
    """渲染「执行轨迹元信息」段：None → 整段省略（空串）；
    available 为假 → 降级提示 judge 自行读 sessions.json。
    """
    language = current_language(lang)
    if trace_meta is None:
        return ""
    if not trace_meta.available:
        if language == "en":
            return (
                "## Execution Trace Metadata\n\n"
                "Unable to extract trace metadata from sessions.json. Read the execution time "
                "from sessions.json in the result directory yourself: time-window validation "
                "still applies, anchored on the first user message timestamp."
            )
        return (
            "## 执行轨迹元信息\n\n"
            "无法从 sessions.json 提取执行轨迹元信息。请自行从结果目录的 sessions.json "
            "读取执行时间：时间校验仍按规则执行，时间点以首条用户消息时间戳为准。"
        )
    if language == "en":
        lines = [
            "## Execution Trace Metadata",
            "",
            f"- Authoritative execution date: {trace_meta.execution_date_cn}. This is the **only "
            "authoritative anchor** for time windows such as \"latest\", \"previous N days\", "
            "\"next N days\" or \"the past week\"; never use the agent's self-reported \"today\", "
            "the current evaluation time, or any other time.",
        ]
        duration = (
            f"{trace_meta.duration_seconds:.0f} s"
            if trace_meta.duration_seconds is not None
            else "unknown"
        )
        lines.append(
            f"- Start → end: {trace_meta.start_time_cn} → {trace_meta.end_time_cn}"
            f" (duration {duration}, {trace_meta.api_calls} model calls)"
        )
        if not trace_meta.tool_calls:
            lines.append("- (no tool calls)")
        else:
            for call in trace_meta.tool_calls:
                status = {True: "true", False: "false", None: "unknown"}[call.success]
                line = f"- `{call.name}` | success: {status}"
                if call.is_search and call.query:
                    line += _wrap_payload("query", call.query)
                elif call.detail:
                    line += _wrap_payload("detail", call.detail)
                lines.append(line)
        return "\n".join(lines)
    lines = [
        "## 执行轨迹元信息",
        "",
        f"- 权威执行日期：{trace_meta.execution_date_cn}。这是判断「最新/前N天/未来N天/最近一周」"
        "等时间窗口的**唯一权威基准**，不得使用 Agent 自述的「今天」、当前评测时间或任何其他时间。",
    ]
    duration = (
        f"{trace_meta.duration_seconds:.0f} 秒" if trace_meta.duration_seconds is not None else "未知"
    )
    lines.append(
        f"- 执行起止：{trace_meta.start_time_cn} → {trace_meta.end_time_cn}"
        f"（耗时 {duration}，模型调用 {trace_meta.api_calls} 轮）"
    )
    if not trace_meta.tool_calls:
        lines.append("- （无工具调用）")
    else:
        for call in trace_meta.tool_calls:
            status = {True: "true", False: "false", None: "unknown"}[call.success]
            line = f"- `{call.name}` | success: {status}"
            if call.is_search and call.query:
                line += _wrap_payload("query", call.query)
            elif call.detail:
                line += _wrap_payload("detail", call.detail)
            lines.append(line)
    return "\n".join(lines)


def build_user_prompt(
    task_prompt: str,
    task_dir: str,
    result_dir: str,
    completion_tree: str,
    quality_tree: str,
    trace_meta: Optional[TraceMeta],
    lang: str | None = None,
) -> str:
    """纯 f-string 拼接（无 Template），共六段：原始任务提问 / 任务目录 / 结果目录 /
    执行轨迹元信息（无则省略）/ Rubric 评分标准 / 收尾指令。
    """
    language = current_language(lang)
    parts: list[str] = []
    trace_section = _render_trace_meta(trace_meta, language)
    if language == "en":
        parts.append(f"## Original Task Query\n\n---\n{task_prompt}\n---")
        parts.append(
            f"## Task Directory\n\n{task_dir}\n\nLayout:\n"
            "- config.json: task definition, must read\n"
            "- init_env/: input deliverables (if any)\n"
            "- verifier/: validation scripts, generally not needed"
        )
        parts.append(
            f"## Result Directory\n\n{result_dir}\n\nNote: your working directory (cwd) is this "
            "directory. Layout:\n"
            "- sessions.json: execution trace, must read\n"
            "- workspace/: final deliverables, the core evidence\n"
            "- score.json: existing scoring record, reference only; do not decide passes from it\n"
            "- verifier/: not needed"
        )
        if trace_section:
            parts.append(trace_section)
        parts.append(
            "## Rubric Evaluation Criteria\n\nJudge leaf nodes only; AND/OR aggregation is derived "
            f"automatically.\n\n### Completion Criteria Tree\n\n{completion_tree}\n\n"
            f"### Quality Scoring Tree\n\n{quality_tree}"
        )
        parts.append(
            "Score according to the workflow and the deliverable inspection protocol in the system "
            "instructions, using the rubric above:\n"
            "1. Read the task configuration and execution trace first, then inspect the workspace\n"
            "2. While scoring leaves, fill time_analysis for time-sensitive leaves and "
            "info_fidelity_analysis for search-dependent leaves\n"
            "3. Finish with confidence, and decide needs_human_review / review_notes as in step 6"
        )
        return "\n\n".join(parts)
    parts.append(f"## 原始任务提问\n\n---\n{task_prompt}\n---")
    parts.append(
        f"## 任务目录\n\n{task_dir}\n\n目录结构：\n"
        "- config.json：任务定义，必读\n"
        "- init_env/：输入型交付物（如有）\n"
        "- verifier/：校验脚本，一般无需关注"
    )
    parts.append(
        f"## 结果目录\n\n{result_dir}\n\n注意：你的工作目录（cwd）即此目录。目录结构：\n"
        "- sessions.json：执行轨迹，必读\n"
        "- workspace/：最终交付物，评测核心\n"
        "- score.json：已有评分记录，仅供参考，不据此判断通过与否\n"
        "- verifier/：无需关注"
    )
    if trace_section:
        parts.append(trace_section)
    parts.append(
        "## Rubric 评分标准\n\n你只需判断叶子节点，AND/OR 组合结果会自动派生。\n\n"
        f"### 完成判定树\n\n{completion_tree}\n\n### 质量评分树\n\n{quality_tree}"
    )
    parts.append(
        "请按系统指令中的评估工作流、交付物检查规程与上述 Rubric 标准评分：\n"
        "1. 先读任务配置与执行轨迹，再检查工作区输出\n"
        "2. 逐叶评分时对涉时叶子完成时间窗口分析并写入 time_analysis；"
        "对涉搜叶子完成搜索信息提取分析并写入 info_fidelity_analysis\n"
        "3. 最后给出置信度，并按工作流第 6 步判定是否需人工复核，"
        "写入 needs_human_review 与 review_notes"
    )
    return "\n\n".join(parts)


def build_output_schema(rubric: QueryRubric, evaluate_trace: bool) -> dict:
    """输出 schema（`{"type":"json_schema", "schema":{...}}`）：
    - `rubric_results`：按叶子 id 的密封对象（`additionalProperties:false` —— 密封是
      结构化输出层对多余 key 触发模型重试的机制，如误发 group id）
    - 始终必填：confidence / time_analysis / info_fidelity_analysis / needs_human_review /
      review_notes
    - `trace_quality`：仅 evaluate_trace=True 时存在，4 维度 number，enum 档位，
      追加在 required 末位
    """
    leaf_ids = collect_leaf_ids(rubric)
    properties: dict[str, Any] = {
        "rubric_results": {
            "type": "object",
            "properties": {
                leaf: {
                    "type": "object",
                    "properties": {
                        "passed": {"type": "boolean"},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["passed", "reasoning"],
                    "additionalProperties": False,
                }
                for leaf in leaf_ids
            },
            "required": leaf_ids,
            "additionalProperties": False,
        },
        "confidence": {"type": "number"},
        "time_analysis": {"type": "string"},
        "info_fidelity_analysis": {"type": "string"},
        "needs_human_review": {"type": "boolean"},
        "review_notes": {"type": "string"},
    }
    required = [
        "rubric_results",
        "confidence",
        "time_analysis",
        "info_fidelity_analysis",
        "needs_human_review",
        "review_notes",
    ]
    if evaluate_trace:
        properties["trace_quality"] = {
            "type": "object",
            "properties": {
                key: {"type": "number", "enum": _TRACE_DIMENSION_VALUES}
                for key in _TRACE_DIMENSION_KEYS
            },
            "required": list(_TRACE_DIMENSION_KEYS),
            "additionalProperties": False,
        }
        required.append("trace_quality")
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def build_prompts(
    config: Any,
    evaluate_trace: bool,
    task_dir: str | Path,
    result_dir: str | Path,
    lang: str | None = None,
) -> tuple[str, str, dict]:
    """组装 `(system_prompt, user_prompt, output_schema)`。"""
    language = current_language(lang)
    rubric = QueryRubric.model_validate(config.rubric)
    system_prompt = build_system_prompt(rubric, evaluate_trace, language)
    completion_tree = render_completion_tree(rubric, language)
    quality_tree = render_quality_tree(rubric, language)
    trace_meta = extract_trace_meta(result_dir)
    user_prompt = build_user_prompt(
        config.prompt,
        str(task_dir),
        str(result_dir),
        completion_tree,
        quality_tree,
        trace_meta,
        language,
    )
    output_schema = build_output_schema(rubric, evaluate_trace)
    return system_prompt, user_prompt, output_schema

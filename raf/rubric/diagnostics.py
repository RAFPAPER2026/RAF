"""RIFT 失败模式诊断：逐 rubric 诊断（每条一次 LLM 调用）+ 聚合诊断（再调一次 LLM）。"""
from __future__ import annotations

import json
from collections import Counter

from .client import chat_json
from .i18n import current_language
from .models_optim import FailureFinding

# RIFT 8 种失败模式
FAILURE_MODES = {
    "subjective": {
        "category": "可靠性",
        "name": "Subjective（主观）",
        "definition": "叶子使用主观评价词（清晰/适当/合理/友好/简洁/充分），缺乏可观察的行为锚点，不同评分者难以做出相同判定",
    },
    "non_atomic": {
        "category": "可靠性",
        "name": "Non-Atomic（非原子）",
        "definition": "单个叶子用「并且」「同时」捆绑多个可独立判定的条件",
    },
    "ungrounded": {
        "category": "可靠性",
        "name": "Ungrounded（无依据）",
        "definition": "检查项依赖无法从轨迹中直接获取的外部信息，且未在叶子名称中指明参考标准",
    },
    "misaligned": {
        "category": "内容效度",
        "name": "Misaligned（目标-过程混淆）",
        "definition": "completion 与 quality 边界交叉：completion 检查过程质量，或 quality 重复检查目标达成",
    },
    "missing_criteria": {
        "category": "内容效度",
        "name": "Missing Criteria（意图遗漏）",
        "definition": "用户的独立意图（含隐含意图、条件意图）没有对应的 completion 检查项",
    },
    "hackable": {
        "category": "后果效度",
        "name": "Hackable（可 hack）",
        "definition": "检查项评价的是语言表述而非实际行为结果，Agent 可以通过口头承诺得分",
    },
    "low_signal": {
        "category": "后果效度",
        "name": "Low Signal（低区分）",
        "definition": "检查项在不同质量的轨迹上得分相同（全满分或全零分），没有区分力",
    },
    "redundant": {
        "category": "后果效度",
        "name": "Redundant（冗余）",
        "definition": "completion 与 quality 之间存在语义重复的检查项",
    },
}

# RIFT 8 failure modes (English)
FAILURE_MODES_EN = {
    "subjective": {
        "category": "Reliability",
        "name": "Subjective",
        "definition": "A leaf uses subjective evaluative words (clear, appropriate, reasonable, "
        "friendly, concise, sufficient) without observable behavioral anchors, so different "
        "raters cannot reach the same verdict",
    },
    "non_atomic": {
        "category": "Reliability",
        "name": "Non-Atomic",
        "definition": "A single leaf bundles multiple independently judgeable conditions with "
        "'and' / 'as well as'",
    },
    "ungrounded": {
        "category": "Reliability",
        "name": "Ungrounded",
        "definition": "A criterion depends on external information that cannot be obtained from "
        "the trajectory, and the reference standard is not specified in the leaf name",
    },
    "misaligned": {
        "category": "Content validity",
        "name": "Misaligned",
        "definition": "The boundary between completion and quality is crossed: completion checks "
        "process quality, or quality re-checks goal achievement",
    },
    "missing_criteria": {
        "category": "Content validity",
        "name": "Missing Criteria",
        "definition": "An independent user intent (including implicit and conditional intents) "
        "has no corresponding completion criterion",
    },
    "hackable": {
        "category": "Consequential validity",
        "name": "Hackable",
        "definition": "A criterion evaluates wording rather than actual behavior/outcome, so the "
        "agent can score by verbal commitment",
    },
    "low_signal": {
        "category": "Consequential validity",
        "name": "Low Signal",
        "definition": "A criterion yields the same verdict across trajectories of different "
        "quality (all pass or all fail) and has no discriminative power",
    },
    "redundant": {
        "category": "Consequential validity",
        "name": "Redundant",
        "definition": "A semantic duplicate exists between completion and quality criteria",
    },
}


DIAGNOSE_SYSTEM = """你是 Rubric 质量诊断专家，遵循 RIFT 框架诊断 AI Agent 评估量规中的失败模式。

8 种失败模式定义：
{failures}

你的任务：检查给定的 rubric（completion_rubric + quality_rubric），找出其中存在的失败模式。

输出 JSON：{{"findings": [{{"pattern": "模式 key", "node_name": "问题节点名称（叶子或组）", "category": "completion|quality", "evidence": "证据：引用具体叶子名称并说明违反了哪条定义", "severity": "high|medium|low", "suggestion": "具体修改建议"}}]}}

要求：
- 只报告确实存在的问题，没有则返回空数组
- 一个节点可以对应多条 finding
- pattern 取值仅限上述 8 个 key"""


DIAGNOSE_SYSTEM_EN = """You are a rubric quality diagnostician following the RIFT framework. You diagnose failure modes in AI-agent evaluation rubrics.

Eight failure-mode definitions:
{failures}

Task: inspect the given rubric (completion_rubric + quality_rubric) and identify the failure modes it contains.

Output JSON: {{"findings": [{{"pattern": "pattern key", "node_name": "offending node name (leaf or group)", "category": "completion|quality", "evidence": "evidence: quote the specific leaf name and explain which definition it violates", "severity": "high|medium|low", "suggestion": "concrete revision suggestion"}}]}}

Requirements:
- Report only real problems; return an empty array when there are none.
- One node may correspond to multiple findings.
- pattern must be one of the eight keys above."""


def diagnose_rubric(rubric: dict, lang: str | None = None) -> list[FailureFinding]:
    """对单条 rubric 做 RIFT 诊断（一次 LLM 调用）。"""
    language = current_language(lang)
    payload = {
        "query": rubric.get("query", ""),
        "completion_rubric": rubric.get("completion_rubric", []),
        "quality_rubric": rubric.get("quality_rubric", []),
    }
    modes = FAILURE_MODES_EN if language == "en" else FAILURE_MODES
    failures_text = "\n".join(
        f"- {key}（{v['category']}）：{v['definition']}" if language != "en"
        else f"- {key} ({v['category']}): {v['definition']}"
        for key, v in modes.items()
    )
    system = DIAGNOSE_SYSTEM_EN if language == "en" else DIAGNOSE_SYSTEM
    user = (
        f"Please diagnose the following rubric:\n{json.dumps(payload, ensure_ascii=False)}"
        if language == "en"
        else f"请诊断以下 rubric：\n{json.dumps(payload, ensure_ascii=False)}"
    )
    messages = [
        {"role": "system", "content": system.format(failures=failures_text)},
        {"role": "user", "content": user},
    ]
    # 不指定 temperature，走模型默认值（reasoning 模型在低温下会对深度分析任务产生超长思考、吃光预算）
    data = chat_json(messages)
    findings: list[FailureFinding] = []
    for f in data.get("findings", []):
        pattern = f.get("pattern")
        if pattern not in FAILURE_MODES:
            continue
        findings.append(FailureFinding(
            pattern=pattern,
            node_name=f.get("node_name", ""),
            category=f.get("category", "quality"),
            evidence=f.get("evidence", ""),
            severity=f.get("severity", "medium"),
            suggestion=f.get("suggestion", ""),
        ))
    return findings


AGGREGATE_SYSTEM = """你是 Rubric 质量诊断专家（RIFT 框架）与 prompt 工程专家。

输入：对一批 rubric 逐条诊断出的失败模式 finding 列表（可能包含大量条目）。
任务：
1. 识别系统性的失败模式（在多条 rubric 中反复出现的问题）
2. 将问题归因到生成 prompt 的模块：role / structure / principles / examples / constraints / capabilities / output
3. 对每个需要修改的模块给出可执行的优化建议

输出 JSON：{{"summary": "系统性问题的简要总结", "suggestions": [{{"module": "模块名", "problem": "该模块存在的问题（联系具体 finding）", "suggestion": "针对该模块的具体修改建议（可直接执行）"}}]}}

要求：建议必须具体到 prompt 模块内的修改动作，而不是泛泛而谈。最多 5 条建议。"""


AGGREGATE_SYSTEM_EN = """You are a rubric quality diagnostician (RIFT) and prompt-engineering expert.

Input: a list of failure-mode findings produced by diagnosing a batch of rubrics individually (it may contain many entries).
Tasks:
1. Identify systematic failure modes (problems that recur across multiple rubrics).
2. Attribute the problems to prompt modules: role / structure / principles / examples / constraints / capabilities / output.
3. Give actionable optimization suggestions for each module that needs changes.

Output JSON: {{"summary": "brief summary of systematic problems", "suggestions": [{{"module": "module key", "problem": "the problem in that module (link to concrete findings)", "suggestion": "concrete, directly executable revision to that module"}}]}}

Requirements: suggestions must name concrete edits inside the prompt module, not generic advice. At most 5 suggestions."""


def aggregate_diagnosis(
    findings: list[FailureFinding], rubrics: list[dict], lang: str | None = None
) -> dict:
    """聚合诊断（一次 LLM 调用）：汇总系统性问题并归因到 prompt 模块、给出优化建议。"""
    language = current_language(lang)
    modes = FAILURE_MODES_EN if language == "en" else FAILURE_MODES
    counter = Counter(f.pattern for f in findings)
    if language == "en":
        summary_lines = [f"{modes[p]['name']}: {count}" for p, count in counter.items()]
    else:
        summary_lines = [f"{modes[p]['name']}：{count} 次" for p, count in counter.items()]
    samples = [f.model_dump() for f in findings[:60]]
    if language == "en":
        user = (
            f"{len(findings)} findings across {len(rubrics)} rubrics.\n\n"
            "Pattern counts:\n" + "\n".join(summary_lines) + "\n\n"
            "Sample findings (max 60):\n" + json.dumps(samples, ensure_ascii=False)
        )
        system = AGGREGATE_SYSTEM_EN
    else:
        user = (
            f"共 {len(findings)} 条 finding，覆盖 {len(rubrics)} 条 rubric。\n\n"
            f"模式统计：\n" + "\n".join(summary_lines) + "\n\n"
            f"finding 样例（最多 60 条）：\n{json.dumps(samples, ensure_ascii=False)}"
        )
        system = AGGREGATE_SYSTEM
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    data = chat_json(messages)  # 模型默认 temperature，同 diagnose_rubric
    valid_modules = {"role", "structure", "principles", "examples", "constraints", "capabilities", "output"}
    data["suggestions"] = [
        s for s in data.get("suggestions", []) if s.get("module") in valid_modules
    ]
    return data

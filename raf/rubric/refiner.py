"""Prompt 精炼器：将采纳的优化建议精炼为新版本 prompt 模块，并支持回测。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import prompt_modules
from .client import chat
from .i18n import current_language
from .models import now_iso

REFINE_SYSTEM = """你是 prompt 工程专家。你的任务是精炼一个用于生成 AI Agent 评估量规的 prompt 模块。

精炼规则：
1. 只针对给定建议做局部修改，保持模块原有结构、风格与约定，不重写无关内容
2. 保留模块中的占位符（如 {capabilities}）与特殊标记
3. 保留模块原有的标题层级（如 ## 1.、### 1.1）
4. 如果建议相互矛盾或与模块已有规则冲突，以模块已有规则为准并忽略矛盾建议
5. 修改后模块的规则必须自洽，不得引入新的内部矛盾

输出：仅返回精炼后的完整模块文本，不要添加任何解释文字或代码块标记。"""


REFINE_SYSTEM_EN = """You are a prompt-engineering expert. Your task is to refine one prompt module used to generate AI-agent evaluation rubrics.

Refinement rules:
1. Make only the local changes requested by the suggestions; preserve the module's structure, style and conventions; do not rewrite unrelated content.
2. Preserve placeholders (e.g. {capabilities}) and special markers.
3. Preserve the module's heading hierarchy (e.g. ## 1., ### 1.1).
4. If suggestions conflict with the module's existing rules, keep the existing rules and ignore the conflicting suggestions.
5. The refined module's rules must be self-consistent and must not introduce new internal contradictions.

Output: return only the refined full module text, with no explanations or code fences."""


def refine_prompt(
    current_version: str,
    new_version: str,
    accepted_suggestions: list[dict],
    lang: str | None = None,
) -> dict:
    """将采纳的建议按模块分组，逐模块调用 LLM 精炼，保存为新版本 prompt。"""
    language = current_language(lang)
    current = prompt_modules.load_version(current_version, language)
    if current is None:
        raise ValueError(f"版本不存在: {current_version}")

    by_module: dict[str, list[dict]] = {}
    for s in accepted_suggestions:
        module_key = s.get("module", "")
        if module_key not in prompt_modules.MODULE_ORDER:
            raise ValueError(f"未知模块: {module_key}")
        by_module.setdefault(module_key, []).append(s)

    new_modules = dict(current.get("modules", {}))
    refined_modules: list[str] = []
    for module_key, suggestions in by_module.items():
        old_text = new_modules.get(module_key, "")
        if language == "en":
            suggestion_text = "\n".join(
                f"- Problem: {s['problem']}\n  Suggestion: {s['suggestion']}" for s in suggestions
            )
            messages = [
                {"role": "system", "content": REFINE_SYSTEM_EN},
                {"role": "user", "content": (
                    f"Current module ({module_key}) content:\n\n{old_text}\n\n"
                    f"Suggestions to apply:\n{suggestion_text}"
                )},
            ]
        else:
            suggestion_text = "\n".join(
                f"- 问题：{s['problem']}\n  建议：{s['suggestion']}" for s in suggestions
            )
            messages = [
                {"role": "system", "content": REFINE_SYSTEM},
                {"role": "user", "content": (
                    f"当前模块（{module_key}）内容：\n\n{old_text}\n\n"
                    f"需要落实的优化建议：\n{suggestion_text}"
                )},
            ]
        # 不指定 temperature，走模型默认值（reasoning 模型在低温下长思考会吃光 max_tokens）
        new_text = _strip_code_fence(chat(messages).strip())
        if not new_text:
            raise ValueError(f"模块 {module_key} 精炼结果为空")
        new_modules[module_key] = new_text
        refined_modules.append(module_key)

    record = {
        "version": new_version,
        "parent_version": current_version,
        "created_at": now_iso(),
        "change_description": (
            "PROMPT-R refinement: " + "; ".join(
                f"{m} module absorbed {len(by_module[m])} suggestion(s)" for m in refined_modules
            )
            if language == "en"
            else "PROMPT-R 精炼：" + "；".join(
                f"{prompt_modules.MODULE_NAMES.get(m, m)}模块吸收 {len(by_module[m])} 条建议"
                for m in refined_modules
            )
        ),
        "language": language,
        "metrics_summary": {},
        "modules": new_modules,
    }
    prompt_modules.save_version(record)
    return record


def backtest(version: str, queries: list[str], concurrency: int = 4) -> dict:
    """回测：用指定版本为查询重新生成 rubric，返回基本统计（不保存）。"""
    from generate_rubric import generate_rubric

    stats = {"version": version, "total": len(queries), "succeeded": 0, "failed": 0, "errors": []}

    def _one(q: str):
        try:
            rubric = generate_rubric(q, prompt_version=version)
            return q, rubric, None
        except Exception as exc:  # noqa: BLE001
            return q, None, str(exc)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        for q, rubric, err in ex.map(_one, queries):
            if err:
                stats["failed"] += 1
                stats["errors"].append({"query": q, "error": err})
            else:
                stats["succeeded"] += 1
    return stats


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text

"""双格式检测：flat（旧）与 tree（当前）并存，自动识别。"""

from __future__ import annotations

from typing import Any


def detect_rubric_format(rubric: Any) -> str:
    """识别 rubric 配置格式，返回 "tree" 或 "flat"。

    rubric 显式 `rubric_format` 字段只是可选提示，非必需。嗅探规则：
    - dict 且 `completion_rubric` 非空、`[0]` 的 `type ∈ {"leaf","group"}` → "tree"
    - 否则 dict 且 `quality_rubric` 非空、`[0]` 含 dict `node` → "tree"
    - 否则（含 list 形式、None/缺失）→ "flat"（防御性默认，保证历史数据可用）
    """
    if isinstance(rubric, dict):
        fmt = rubric.get("rubric_format")
        if fmt in ("tree", "flat"):
            return fmt
        completion = rubric.get("completion_rubric")
        if isinstance(completion, list) and completion:
            first = completion[0]
            if isinstance(first, dict) and first.get("type") in ("leaf", "group"):
                return "tree"
        quality = rubric.get("quality_rubric")
        if isinstance(quality, list) and quality:
            first = quality[0]
            if isinstance(first, dict) and isinstance(first.get("node"), dict):
                return "tree"
    return "flat"


def detect_score_format(score_data: Any) -> str:
    """识别 score.json 结果格式，返回 "tree" / "flat" / "legacy"。

    - 显式 `rubric_format=="tree"` 或 `rubric_results` 是 dict → "tree"
    - `rubric_scores` 是 list → "flat"
    - 都没有 → "legacy"（仅 manual_score 等）
    """
    if not isinstance(score_data, dict):
        return "legacy"
    if score_data.get("rubric_format") == "tree" or isinstance(
        score_data.get("rubric_results"), dict
    ):
        return "tree"
    if isinstance(score_data.get("rubric_scores"), list):
        return "flat"
    return "legacy"

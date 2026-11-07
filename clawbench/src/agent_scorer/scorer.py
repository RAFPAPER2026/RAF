"""AgentScorer — 核心 evaluate() 流程。

超时不在 scorer 内：由 AgentTaskManager._run_with_timeout 用 asyncio.wait_for 外部强制。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.agent_scorer.exceptions import AgentParseError, AgentValidationError
from src.agent_scorer.models import AgentReview
from src.agent_scorer.prompt_builder import DEFAULT_TRACE_DIMENSIONS, build_prompts
from src.i18n import current_language
from src.models import TaskConfig
from src.rubric.compat import detect_rubric_format
from src.rubric.models import QueryRubric
from src.rubric.scoring import collect_leaf_ids
from src.runs import write_json_atomic

# 硬编码默认 ← JSON 文件覆盖 ← 构造器 overrides
DEFAULT_AGENT_CONFIG: dict[str, Any] = {
    "settings_path": None,
    "model": None,
    "max_turns": 30,
    "timeout_seconds": 300,
    "permission_mode": "acceptEdits",
}

JUDGE_DIR_NAME = "verifier/judge"
AGENT_JUDGE_FILE = "agent_judge.jsonl"
EXCEPTIONS_FILE = "exceptions.md"
PROOF_DIR = "proof"

_TRACE_DIMENSION_KEYS = tuple(d["key"] for d in DEFAULT_TRACE_DIMENSIONS)
_TRACE_DIMENSION_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
_TRACE_TOLERANCE = 1e-3


def _sdk():
    """惰性导入 SDK（测试可 monkeypatch 该函数）。"""
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query  # noqa: PLC0415

    return query, ClaudeAgentOptions, ResultMessage


def _message_type(message: Any) -> str:
    """类名去 `Message` 后缀转小写：UserMessage→user、AssistantMessage→assistant、
    SystemMessage→system、ToolResultMessage→toolresult、ResultMessage→result。
    """
    name = type(message).__name__
    if name.endswith("Message"):
        name = name[: -len("Message")]
    return name.lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentScorer:
    """Agent 自动评测（仅支持 tree 格式 rubric）。"""

    def __init__(self, agent_config_path: str | Path | None = None, **overrides: Any):
        self.agent_config_path = Path(agent_config_path) if agent_config_path else None
        self.overrides = overrides

    def _load_agent_config(self) -> dict:
        cfg = dict(DEFAULT_AGENT_CONFIG)
        if self.agent_config_path and self.agent_config_path.is_file():
            try:
                file_cfg = json.loads(self.agent_config_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                file_cfg = {}
            if isinstance(file_cfg, dict):
                for key in cfg:
                    if key in file_cfg:
                        cfg[key] = file_cfg[key]
        cfg.update(self.overrides)
        return cfg

    # ------------------------------------------------------------ 清旧产物

    @staticmethod
    def clear_previous_result(result_dir: str | Path) -> None:
        """清旧产物：删 `verifier/judge/agent_judge.jsonl`、`exceptions.md`、`proof/` 目录；
        原子剥离 score.json 中的 `agent_review` 键；**不碰** `workspace/`、`sessions.json`、
        `manual_score`；失败仅 warning。
        """
        result_dir = Path(result_dir)
        judge_dir = result_dir / JUDGE_DIR_NAME
        for target in (judge_dir / AGENT_JUDGE_FILE, judge_dir / EXCEPTIONS_FILE):
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                print(f"[warn] 清理 {target} 失败：{exc}")
        try:
            import shutil

            shutil.rmtree(judge_dir / PROOF_DIR, ignore_errors=True)
        except OSError as exc:
            print(f"[warn] 清理 proof/ 失败：{exc}")
        score_path = result_dir / "score.json"
        try:
            data = json.loads(score_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "agent_review" in data:
                del data["agent_review"]
                write_json_atomic(score_path, data)
        except (OSError, ValueError):
            print(f"[warn] 剥离 agent_review 失败：{score_path}")

    # ------------------------------------------------------------ evaluate

    async def evaluate(
        self,
        config: Any,
        evaluate_trace: bool,
        task_dir: str | Path,
        result_dir: str | Path,
    ) -> AgentReview:
        """完整评测流程：

        1. 清旧产物 2. 读任务配置 + tree-only 守卫 3. 构建 prompts 4. 加载 agent 配置
        5. 组装 SDK options 6. 调用 SDK 7. 存转录 8. 解析结构化输出 9. 校验 10. 持久化
        """
        task_dir = Path(task_dir)
        result_dir = Path(result_dir)
        # 1. 清旧产物
        self.clear_previous_result(result_dir)

        # 2. 读任务配置 + tree-only 守卫（flat 不支持——整个 pipeline 从 schema 到采纳都是 tree-only）
        config_path = TaskConfig.config_path(task_dir, current_language())
        if not config_path.is_file():
            raise FileNotFoundError(f"任务配置缺失：{config_path}")
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw_config, dict) or detect_rubric_format(raw_config.get("rubric")) != "tree":
            raise ValueError("Agent 评分仅支持 tree 格式 rubric（flat 不支持）")
        rubric = QueryRubric.model_validate(raw_config.get("rubric"))

        # 3. 构建 prompts
        system_prompt, user_prompt, output_schema = build_prompts(
            config, evaluate_trace, task_dir, result_dir
        )

        # 4. 加载 agent 配置（硬编码默认 ← JSON 文件覆盖 ← 构造器 overrides）
        agent_config = self._load_agent_config()

        # 5. 组装 SDK options（cwd = 结果目录，使 sessions.json/workspace 可读；
        #    add_dirs = 任务目录；model 为 null 时用 SDK 默认/环境指定）
        query, ClaudeAgentOptions, ResultMessage = _sdk()
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            permission_mode=agent_config["permission_mode"],
            cwd=str(result_dir),
            add_dirs=[str(task_dir)],
            output_format=output_schema,
            max_turns=agent_config["max_turns"],
            model=agent_config["model"],
            setting_sources=["user"],
        )
        if agent_config.get("settings_path"):
            settings_path = Path(str(agent_config["settings_path"])).expanduser()
            if not settings_path.is_absolute():
                # 相对路径以 clawbench/ 项目根为基准（src/agent_scorer/scorer.py → 上三级）
                settings_path = Path(__file__).resolve().parent.parent.parent / settings_path
            if settings_path.is_file():
                options.settings = str(settings_path)

        # 6. 调用 SDK：逐条收集；遇首个 ResultMessage 即 break（一次性单向流）
        messages: list[Any] = []
        result_message: Any = None
        async for message in query(prompt=user_prompt, options=options):
            messages.append(message)
            if isinstance(message, ResultMessage):
                result_message = message
                break

        # 7. 存转录
        self._save_transcript(result_dir, messages)

        # 8. 解析结构化输出
        if result_message is None:
            raise AgentParseError("未收到 ResultMessage")
        if getattr(result_message, "is_error", False):
            raise AgentParseError(
                f"评测出错：{getattr(result_message, 'message', getattr(result_message, 'result', 'unknown'))}"
            )
        output = getattr(result_message, "structured_output", None)
        if output is None or not isinstance(output, dict):
            raise AgentParseError("ResultMessage 缺少结构化输出")

        # 9. 校验 → AgentReview
        review = self._validate_output(output, rubric, evaluate_trace)

        # 10. 持久化
        self.save_agent_review(result_dir, review)
        return review

    # ------------------------------------------------------------ 转录

    @staticmethod
    def _save_transcript(result_dir: Path, messages: list[Any]) -> None:
        """写 `verifier/judge/agent_judge.jsonl`：SDK 消息逐条 `asdict` + 两个附加字段
        `type`（类名去 Message 后缀转小写）与 `timestamp`。序列化 `ensure_ascii=False,
        default=str`；每次运行截断重建（clear_previous_result 先删旧的）。
        """
        judge_dir = result_dir / JUDGE_DIR_NAME
        judge_dir.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for message in messages:
            try:
                record = asdict(message)
            except TypeError:
                record = {"raw": str(message)}
            if not isinstance(record, dict):
                record = {"raw": str(record)}
            record["type"] = _message_type(message)
            record["timestamp"] = _now_iso()
            lines.append(json.dumps(record, ensure_ascii=False, default=str))
        (judge_dir / AGENT_JUDGE_FILE).write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )

    # ------------------------------------------------------------ 校验

    @staticmethod
    def _validate_output(output: dict, rubric: QueryRubric, evaluate_trace: bool) -> AgentReview:
        leaf_ids = collect_leaf_ids(rubric)

        rubric_results_raw = output.get("rubric_results")
        if not isinstance(rubric_results_raw, dict):
            raise AgentValidationError("rubric_results 必须为对象")
        missing = [leaf for leaf in leaf_ids if leaf not in rubric_results_raw]
        if missing:
            raise AgentValidationError(f"missing leaf ids: {missing}")
        results: dict[str, dict[str, Any]] = {}
        for leaf in leaf_ids:
            value = rubric_results_raw[leaf]
            if not isinstance(value, dict):
                raise AgentValidationError(f"叶子 {leaf} 的结果必须为对象")
            if not isinstance(value.get("passed"), bool):
                raise AgentValidationError(f"叶子 {leaf} 缺少布尔 passed")
            if not isinstance(value.get("reasoning"), str):
                raise AgentValidationError(f"叶子 {leaf} 缺少字符串 reasoning")
            results[leaf] = {"passed": value["passed"], "reasoning": value["reasoning"]}
        # 多余非叶子 key 静默丢弃（含已知 group id —— 组结果由下游 src/rubric/scoring.py 推导）

        confidence = output.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise AgentValidationError("confidence 必填且为数字")
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise AgentValidationError("confidence 必须在 [0.0, 1.0]")

        for field in ("time_analysis", "info_fidelity_analysis", "review_notes"):
            value = output.get(field)
            if not isinstance(value, str) or not value.strip():
                raise AgentValidationError(f"{field} 必填非空字符串（纯空白失败）")
        needs_human_review = output.get("needs_human_review")
        if not isinstance(needs_human_review, bool):
            raise AgentValidationError("needs_human_review 必填布尔值")

        trace_quality: Optional[dict[str, Any]] = None
        if evaluate_trace:
            raw_tq = output.get("trace_quality")
            if not isinstance(raw_tq, dict):
                raise AgentValidationError("trace_quality 必填（evaluate_trace=True）")
            wrapped = raw_tq.get("dimensions")
            dims = wrapped if isinstance(wrapped, dict) else raw_tq  # 接受裸 dict 或带 dimensions 包装
            normalized: dict[str, float] = {}
            for key in _TRACE_DIMENSION_KEYS:
                value = dims.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise AgentValidationError(f"trace_quality 维度 {key} 必填")
                matched = next(
                    (v for v in _TRACE_DIMENSION_VALUES if abs(float(value) - v) <= _TRACE_TOLERANCE),
                    None,
                )
                if matched is None:
                    raise AgentValidationError(
                        f"trace_quality 维度 {key} 必须为 0.0/0.25/0.5/0.75/1.0"
                    )
                normalized[key] = matched
            trace_quality = {"dimensions": normalized}

        return AgentReview(
            rubric_format="tree",
            rubric_results=results,
            confidence=confidence,
            trace_quality=trace_quality,
            time_analysis=output["time_analysis"],
            info_fidelity_analysis=output["info_fidelity_analysis"],
            needs_human_review=needs_human_review,
            review_notes=output["review_notes"],
            timestamp=_now_iso(),
        )

    # ------------------------------------------------------------ 持久化

    @staticmethod
    def save_agent_review(result_dir: str | Path, agent_review: AgentReview) -> None:
        """要求 `{result_dir}/score.json` 存在（否则 FileNotFoundError）；
        写 `score_data["agent_review"]`；`needs_human_review=True` 时置顶层
        `score_data["doubtful"] = True`（单向，只写 True 从不清除——人工或前轮设置的
        存疑在重跑后保留）；原子写。
        """
        result_dir = Path(result_dir)
        score_path = result_dir / "score.json"
        if not score_path.is_file():
            raise FileNotFoundError(f"score.json 不存在：{score_path}")
        data = json.loads(score_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"score.json 内容异常：{score_path}")
        data["agent_review"] = agent_review.to_dict()
        if agent_review.needs_human_review:
            data["doubtful"] = True
        write_json_atomic(score_path, data)

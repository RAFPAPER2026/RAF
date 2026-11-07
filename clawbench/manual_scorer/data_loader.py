"""人工打分页数据读写（ManualScorerDataLoader）。

- 盲评别名：固定种子 shuffle 生成「模型 A」…「模型 Z」→「模型 AA」…（共 702 个别名），
  持久化 `{真实名: 别名}` 到 `result_dir/.name_mapping.json`；真实名取目录名前两个 `_` 分隔段
- result.json 一致性：`rebuild_result_json` 委托 `build_per_run_result_json`（src/runs.py），
  线程锁 `_result_json_lock` 串行化 + tempfile+`os.replace` 原子写
- 模型缓存：`_models_cache` 2 秒 TTL，去重 `/api/models` 扫描
"""

from __future__ import annotations

import json
import random
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.models import TaskConfig
from src.rubric.compat import detect_rubric_format, detect_score_format
from src.rubric.models import QueryRubric
from src.rubric.scoring import collect_leaf_ids, compute_rubric_score
from src.runs import (
    AVERAGE_RUN_ID,
    apply_legacy_compat,
    average_case_scores,
    derive_complete_flag,
    discover_runs,
    is_legacy_single_run,
    is_passed,
    iter_case_dirs,
    list_model_runs,
    load_pass_threshold,
    migrate_legacy_to_run_1,
    resolve_run_dir,
    write_json_atomic,
    write_result_json,
)

MODELS_CACHE_TTL = 2.0
ALIAS_SEED = 20260327  # 固定种子 shuffle

_SCORE_ERRORS = (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError, AttributeError)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _all_aliases() -> list[str]:
    """「模型 A」…「模型 Z」→「模型 AA」…「模型 ZZ」（共 702 个别名）。"""
    aliases = [f"模型 {chr(64 + i)}" for i in range(1, 27)]
    for i in range(1, 27):
        for j in range(1, 27):
            aliases.append(f"模型 {chr(64 + i)}{chr(64 + j)}")
    return aliases


class ManualScorerDataLoader:
    def __init__(self, result_dir: str | Path, tasks_dir: str | Path | None = None):
        self.result_dir = Path(result_dir)
        self.tasks_dir = Path(tasks_dir) if tasks_dir else None
        self._models_cache: tuple[float, Optional[list[dict]]] = (0.0, None)
        self._result_json_lock = threading.Lock()
        self._name_mapping: Optional[dict[str, str]] = None

    # ------------------------------------------------------------ 模型发现

    def _list_model_ids(self) -> list[str]:
        if not self.result_dir.is_dir():
            return []
        return sorted(
            child.name
            for child in self.result_dir.iterdir()
            if child.is_dir() and (child / "result.json").is_file()
        )

    def _real_model_names(self) -> list[str]:
        return sorted({"_".join(m.split("_")[:2]) for m in self._list_model_ids()})

    def get_name_mapping(self) -> dict[str, str]:
        """盲评别名映射 `{真实名: 别名}`（惰性构建）。"""
        if self._name_mapping is None:
            self._name_mapping = self._build_name_mapping()
        return self._name_mapping

    def _build_name_mapping(self) -> dict[str, str]:
        mapping_path = self.result_dir / ".name_mapping.json"
        mapping: dict[str, str] = {}
        if mapping_path.is_file():
            try:
                data = json.loads(mapping_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    mapping = {str(k): str(v) for k, v in data.items()}
            except (OSError, ValueError):
                mapping = {}
        real_names = self._real_model_names()
        # 已映射的名字保持稳定；新增名从未用别名中 shuffle 分配
        new_names = [n for n in real_names if n not in mapping]
        available = [a for a in _all_aliases() if a not in set(mapping.values())]
        rng = random.Random(ALIAS_SEED)
        for name in new_names:
            if not available:
                break
            mapping[name] = available.pop(rng.randrange(len(available)))
        for name in list(mapping):
            if name not in real_names:
                mapping.pop(name, None)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(mapping_path, mapping)
        return mapping

    def invalidate_models_cache(self) -> None:
        self._models_cache = (0.0, None)

    def get_models(self) -> list[dict]:
        """`ModelSummary[]`（仅统计 manual 任务；含 run 平均分数与 per-run 统计），2 秒 TTL。"""
        now = time.monotonic()
        cached = self._models_cache
        if cached[1] is not None and now - cached[0] < MODELS_CACHE_TTL:
            return cached[1]
        models = self._load_models()
        self._models_cache = (now, models)
        return models

    def _load_models(self) -> list[dict]:
        mapping = self.get_name_mapping()
        return [
            self._load_model_summary(self.result_dir / model_id, model_id, mapping)
            for model_id in self._list_model_ids()
        ]

    def _load_model_summary(
        self, model_dir: Path, model_id: str, mapping: dict[str, str]
    ) -> dict:
        """只数 manual 任务；用 run 平均分数；per_run_stats 每 run
        `{total, scored, passed, avg_score, pass_rate}`。
        """
        real_name = "_".join(model_id.split("_")[:2])
        threshold = load_pass_threshold()
        runs_info = list_model_runs(model_dir)
        runs = runs_info["runs"] or ["run_1"]
        case_dirs = iter_case_dirs(model_dir)

        per_case_avg: dict[str, dict] = {}
        for case_dir in case_dirs:
            config = self._load_task_config(case_dir.name)
            if config is None or config.verifier_type != "manual":
                continue
            avg = average_case_scores(case_dir)
            if avg is not None:
                per_case_avg[case_dir.name] = avg

        scored = sum(
            1 for s in per_case_avg.values() if _is_number(s.get("manual_score"))
        )
        scores = [float(s["score"]) for s in per_case_avg.values() if _is_number(s.get("score"))]
        passed = sum(1 for s in per_case_avg.values() if is_passed(s, threshold))
        total = len(per_case_avg)

        per_run_stats: dict[str, dict] = {}
        for run_id in runs:
            stats: dict[str, Any] = {
                "total": 0, "scored": 0, "passed": 0, "avg_score": None, "pass_rate": None,
            }
            run_scores: list[float] = []
            for case_dir in case_dirs:
                config = self._load_task_config(case_dir.name)
                if config is None or config.verifier_type != "manual":
                    continue
                try:
                    run_dir = resolve_run_dir(case_dir, run_id)
                    data = apply_legacy_compat(
                        dict(json.loads((run_dir / "score.json").read_text(encoding="utf-8")))
                    )
                except _SCORE_ERRORS:
                    continue
                stats["total"] += 1
                if _is_number(data.get("manual_score")):
                    stats["scored"] += 1
                if _is_number(data.get("score")):
                    run_scores.append(float(data["score"]))
                if is_passed(data, threshold):
                    stats["passed"] += 1
            stats["avg_score"] = round(sum(run_scores) / len(run_scores), 4) if run_scores else None
            stats["pass_rate"] = (
                round(stats["passed"] / stats["total"] * 100, 2) if stats["total"] else None
            )
            per_run_stats[run_id] = stats

        return {
            "id": model_id,
            "name": real_name,
            "alias": mapping.get(real_name, real_name),
            "total": total,
            "scored": scored,
            "unscored": total - scored,
            "passed": passed,
            "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
            "pass_rate": round(passed / total * 100, 2) if total else None,
            "runs": runs,
            "max_run": runs_info["max_run"],
            "default_run": f"run_{runs_info['max_run']}" if runs_info["max_run"] else "run_1",
            "per_run_stats": per_run_stats,
        }

    def get_global_stats(self) -> dict:
        """`/api/stats`：{total_models, total_tasks, total_scored, total_unscored, models[]}。"""
        models = self.get_models()
        total = sum(m["total"] for m in models)
        scored = sum(m["scored"] for m in models)
        return {
            "total_models": len(models),
            "total_tasks": total,
            "total_scored": scored,
            "total_unscored": total - scored,
            "models": [
                {"id": m["id"], "name": m["name"], "total": m["total"], "scored": m["scored"]}
                for m in models
            ],
        }

    # ------------------------------------------------------------ 路径解析

    def _resolve_model_dir(self, model_id: str) -> Path:
        model_dir = self.result_dir / model_id
        if not model_dir.is_dir():
            raise FileNotFoundError(f"模型不存在：{model_id}")
        return model_dir

    def _resolve_case_dir(self, model_id: str, task_name: str) -> Path:
        case_dir = self.result_dir / model_id / task_name
        if not case_dir.is_dir():
            raise FileNotFoundError(f"任务目录不存在：{model_id}/{task_name}")
        return case_dir

    def _resolve_writable_run_dir(self, model_id: str, task_name: str, run_id: str) -> Path:
        """写路由统一入口：**拒绝写磁盘上不存在的 run**。"""
        case_dir = self._resolve_case_dir(model_id, task_name)
        try:
            return resolve_run_dir(case_dir, run_id)
        except (ValueError, FileNotFoundError) as exc:
            raise FileNotFoundError(
                f"run '{run_id}' 不存在于磁盘：{model_id}/{task_name}"
            ) from exc

    def get_runs(self, model_id: str) -> dict:
        """`{runs[], max_run, per_case_runs, default_run, runs_detail:[{run_id, scored_tasks}]}`。"""
        model_dir = self._resolve_model_dir(model_id)
        info = list_model_runs(model_dir)
        runs = info["runs"] or ["run_1"]
        runs_detail = []
        for run_id in runs:
            scored = 0
            for case_dir in iter_case_dirs(model_dir):
                try:
                    run_dir = resolve_run_dir(case_dir, run_id)
                    data = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
                    if isinstance(data, dict) and _is_number(data.get("manual_score")):
                        scored += 1
                except _SCORE_ERRORS:
                    continue
            runs_detail.append({"run_id": run_id, "scored_tasks": scored})
        return {
            "runs": runs,
            "max_run": info["max_run"],
            "per_case_runs": info["per_case_runs"],
            "default_run": f"run_{info['max_run']}" if info["max_run"] else "run_1",
            "runs_detail": runs_detail,
        }

    # ------------------------------------------------------------ 任务配置

    def get_task_config(self, task_name: str) -> Optional[TaskConfig]:
        return self._load_task_config(task_name)

    def _load_task_config(self, task_name: str) -> Optional[TaskConfig]:
        if self.tasks_dir is None:
            return None
        config_path = TaskConfig.config_path(self.tasks_dir / task_name)
        if not config_path.is_file():
            return None
        try:
            return TaskConfig.load(config_path.parent)
        except (OSError, ValueError, TypeError):
            return None

    # ------------------------------------------------------------ 任务列表/详情

    def get_task_summaries(self, model_id: str, run_id: str = AVERAGE_RUN_ID) -> list[dict]:
        """`TaskSummary[]`，**只含 `verifier_type=="manual"` 任务**。"""
        model_dir = self._resolve_model_dir(model_id)
        summaries: list[dict] = []
        for case_dir in iter_case_dirs(model_dir):
            config = self._load_task_config(case_dir.name)
            if config is None or config.verifier_type != "manual":
                continue
            if run_id == AVERAGE_RUN_ID:
                data = average_case_scores(case_dir)
                if data is None:
                    continue
            else:
                try:
                    run_dir = resolve_run_dir(case_dir, run_id)
                    data = apply_legacy_compat(
                        dict(json.loads((run_dir / "score.json").read_text(encoding="utf-8")))
                    )
                except _SCORE_ERRORS:
                    continue
            fmt = detect_score_format(data)
            summaries.append(
                {
                    "task_name": case_dir.name,
                    "status": data.get("status"),
                    "score": data.get("score"),
                    "manual_score": data.get("manual_score"),
                    "complete_flag": data.get("complete_flag"),
                    "manual_feedback": data.get("manual_feedback", 0),
                    "doubtful": bool(data.get("doubtful", False)),
                    "completion_rate": data.get("completion_rate"),
                    "rubric_format": fmt if fmt != "legacy" else None,
                    "duration": data.get("duration"),
                }
            )
        summaries.sort(key=lambda s: s["task_name"])
        return summaries

    def get_task_detail(self, model_id: str, task_name: str, run_id: str = "run_1") -> dict:
        """`{task_name, score(兼容处理+tree 重算), config(+rubric_format), sessions[]}`。
        仅具体 run（average 拒绝）。
        """
        if run_id == AVERAGE_RUN_ID:
            raise ValueError("任务详情仅支持具体 run_id（average 不是磁盘目录）")
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        try:
            score = apply_legacy_compat(
                dict(json.loads((run_dir / "score.json").read_text(encoding="utf-8")))
            )
        except _SCORE_ERRORS as exc:
            raise FileNotFoundError(f"score.json 不可读：{model_id}/{task_name}/{run_id}") from exc
        config = self._load_task_config(task_name)
        if config is None:
            raise FileNotFoundError(f"任务配置缺失：{task_name}")
        # tree 重算（compute_rubric_score 权威派生）
        if detect_rubric_format(config.rubric) == "tree" and isinstance(
            score.get("rubric_results"), dict
        ):
            rubric = QueryRubric.model_validate(config.rubric)
            try:
                derived = compute_rubric_score(rubric, score["rubric_results"])
            except (ValueError, TypeError):
                pass
            else:
                score["completion"] = derived["completion"]
                score["quality_score"] = derived["quality_score"]
                score["score"] = derived["score"]
                score["completion_rate"] = derived["completion_rate"]
                score["complete_flag"] = derived["complete_flag"]
                score["rubric_format"] = "tree"
        config_data = config.model_dump()
        config_data["rubric_format"] = detect_rubric_format(config.rubric)
        sessions: list[Any] = []
        sessions_path = run_dir / "sessions.json"
        if sessions_path.is_file():
            try:
                sessions_data = json.loads(sessions_path.read_text(encoding="utf-8"))
                if isinstance(sessions_data, dict) and isinstance(sessions_data.get("sessions"), list):
                    sessions = sessions_data["sessions"]
            except (OSError, ValueError):
                sessions = []
        return {"task_name": task_name, "score": score, "config": config_data, "sessions": sessions}

    def get_sessions(self, model_id: str, task_name: str, run_id: str = "run_1") -> dict:
        """原始 sessions.json。"""
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        sessions_path = run_dir / "sessions.json"
        if not sessions_path.is_file():
            return {}
        try:
            data = json.loads(sessions_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------ 评分写入

    def _load_score_data(self, run_dir: Path) -> dict:
        score_path = run_dir / "score.json"
        if not score_path.is_file():
            raise FileNotFoundError(f"score.json 不存在：{score_path}")
        data = json.loads(score_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"score.json 内容异常：{score_path}")
        return data

    def _write_score_data(self, run_dir: Path, data: dict) -> None:
        write_json_atomic(run_dir / "score.json", data)
        self.invalidate_models_cache()

    def rebuild_result_json(self, model_id: str) -> dict:
        """`_update_result_json` / `_reconcile_result_json` 均委托 `build_per_run_result_json`
        （src/runs.py）；线程锁串行化 + 原子写。
        """
        with self._result_json_lock:
            return write_result_json(self.result_dir / model_id)

    _update_result_json = rebuild_result_json
    _reconcile_result_json = rebuild_result_json

    def save_task_score(
        self,
        model_id: str,
        task_name: str,
        run_id: str,
        rubric_results: Optional[dict[str, bool]] = None,
        rubric_scores: Optional[list[dict]] = None,
        score: Optional[float] = None,
        dimensions: Optional[dict[str, float]] = None,
        comment: Optional[str] = None,
        scored_by: Optional[str] = None,
    ) -> dict:
        """评分写入统一入口：tree 存原始 `rubric_results` + 派生字段（**保留旧
        `rubric_scores` 作审计轨迹**）；flat 存 `rubric_scores`；直接模式写 `score`/`dimensions`。
        按请求体内容分发到三种模式。
        """
        if rubric_results is not None:
            return self.save_tree_score(
                model_id, task_name, run_id, rubric_results, comment, scored_by
            )
        if rubric_scores is not None:
            return self.save_flat_score(
                model_id, task_name, run_id, rubric_scores, comment, scored_by
            )
        if score is not None or dimensions is not None:
            return self.save_direct_score(
                model_id, task_name, run_id, score, dimensions, comment, scored_by
            )
        raise ValueError("评分请求体为空（需 rubric_results/rubric_scores/score/dimensions 之一）")

    def save_tree_score(
        self,
        model_id: str,
        task_name: str,
        run_id: str,
        rubric_results: dict[str, bool],
        comment: Optional[str] = None,
        scored_by: Optional[str] = None,
        scoring_mode: Optional[str] = None,
    ) -> dict:
        """tree 模式：按 config 树校验 `rubric_results` 覆盖全部叶子 →
        `compute_rubric_score` 权威派生 → `score = quality_score`（round 4 位）。
        """
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        config = self._load_task_config(task_name)
        if config is None or detect_rubric_format(config.rubric) != "tree":
            raise ValueError("任务不是 tree 格式 rubric")
        rubric = QueryRubric.model_validate(config.rubric)
        leaf_ids = collect_leaf_ids(rubric)
        missing = [leaf for leaf in leaf_ids if leaf not in rubric_results]
        if missing:
            raise ValueError(f"rubric_results 未覆盖叶子：{missing}")
        leaf_bools = {str(k): bool(v) for k, v in rubric_results.items() if str(k) in leaf_ids}
        derived = compute_rubric_score(rubric, leaf_bools, scoring_mode=scoring_mode)
        data = self._load_score_data(run_dir)
        data["rubric_results"] = leaf_bools
        data["rubric_format"] = "tree"
        data["completion"] = derived["completion"]
        data["quality_score"] = derived["quality_score"]
        data["score"] = round(derived["quality_score"], 4)
        data["completion_rate"] = derived["completion_rate"]
        data["complete_flag"] = derived["complete_flag"]
        data["scoring_mode"] = derived["scoring_mode"]
        data["manual_score"] = data["score"]  # 保留旧 rubric_scores 作审计轨迹
        data["manual_comment"] = comment
        data["manual_scored_at"] = _now_iso()
        if scored_by:
            data["manual_scored_by"] = scored_by
        self._write_score_data(run_dir, data)
        self.rebuild_result_json(model_id)
        return {"success": True, "message": "已保存 tree 评分", "score": data["score"]}

    def save_flat_score(
        self,
        model_id: str,
        task_name: str,
        run_id: str,
        rubric_scores: list[dict],
        comment: Optional[str] = None,
        scored_by: Optional[str] = None,
    ) -> dict:
        """flat 模式：`item_score = completion * quality_score`，`score = mean(item_scores)`，
        `completion_rate = mean(completions)`。
        """
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        items: list[dict] = []
        for item in rubric_scores:
            completion = 1 if item.get("completion") else 0
            quality = float(item.get("quality_score") or 0)
            items.append(
                {"completion": completion, "quality_score": quality, "item_score": completion * quality}
            )
        score = sum(i["item_score"] for i in items) / len(items) if items else 0.0
        completion_rate = sum(i["completion"] for i in items) / len(items) if items else 0.0
        complete_flag = 1 if items and all(i["completion"] for i in items) else 0
        data = self._load_score_data(run_dir)
        data["rubric_scores"] = items
        data["completion_rate"] = round(completion_rate, 4)
        data["score"] = round(score, 4)
        data["complete_flag"] = complete_flag
        data["manual_score"] = data["score"]
        data["manual_comment"] = comment
        data["manual_scored_at"] = _now_iso()
        if scored_by:
            data["manual_scored_by"] = scored_by
        self._write_score_data(run_dir, data)
        self.rebuild_result_json(model_id)
        return {"success": True, "message": "已保存评分", "score": data["score"]}

    def save_direct_score(
        self,
        model_id: str,
        task_name: str,
        run_id: str,
        score: Optional[float] = None,
        dimensions: Optional[dict[str, float]] = None,
        comment: Optional[str] = None,
        scored_by: Optional[str] = None,
    ) -> dict:
        """直接模式：写 `score` 或 `dimensions`。"""
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        data = self._load_score_data(run_dir)
        if score is not None:
            data["score"] = round(float(score), 4)
            data["manual_score"] = data["score"]
            data["complete_flag"] = derive_complete_flag(data["score"])
        if dimensions is not None:
            data["dimension_scores"] = {str(k): float(v) for k, v in dimensions.items()}
        data["manual_comment"] = comment
        data["manual_scored_at"] = _now_iso()
        if scored_by:
            data["manual_scored_by"] = scored_by
        self._write_score_data(run_dir, data)
        self.rebuild_result_json(model_id)
        return {"success": True, "message": "已保存评分", "score": data.get("score")}

    def save_manual_score(
        self,
        model_id: str,
        task_name: str,
        run_id: str,
        score: float,
        rubric_results: Optional[dict[str, bool]] = None,
        completion: Optional[dict] = None,
        quality_score: Optional[float] = None,
        completion_rate: Optional[float] = None,
        complete_flag: Optional[int] = None,
        comment: Optional[str] = None,
        scored_by: Optional[str] = None,
        adopted_agent_timestamp: Optional[str] = None,
    ) -> dict:
        """写 `manual_score/manual_comment/manual_scored_at/manual_scored_by/
        adopted_agent_timestamp`，顶层 `score` 同步；tree 路径存 `rubric_results/
        rubric_format:"tree"/completion/quality_score/completion_rate/complete_flag`
        （旧 flat `rubric_scores` 留作审计）；重建 result.json + 失效模型缓存。
        """
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        data = self._load_score_data(run_dir)
        data["manual_score"] = round(float(score), 4)
        data["score"] = data["manual_score"]
        data["manual_comment"] = comment
        data["manual_scored_at"] = _now_iso()
        if scored_by:
            data["manual_scored_by"] = scored_by
        if adopted_agent_timestamp:
            data["adopted_agent_timestamp"] = adopted_agent_timestamp
        if rubric_results is not None:
            data["rubric_results"] = {str(k): bool(v) for k, v in rubric_results.items()}
            data["rubric_format"] = "tree"
        if completion is not None:
            data["completion"] = completion
        if quality_score is not None:
            data["quality_score"] = round(float(quality_score), 4)
        if completion_rate is not None:
            data["completion_rate"] = round(float(completion_rate), 4)
        if complete_flag is not None:
            data["complete_flag"] = complete_flag
        self._write_score_data(run_dir, data)
        self.rebuild_result_json(model_id)
        return {"success": True, "message": "已保存人工评分", "score": data["score"]}

    def save_complete_flag(self, model_id: str, task_name: str, run_id: str, complete_flag: Any) -> None:
        """只写 complete_flag；不碰 result.json；null 存显式 null。"""
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        data = self._load_score_data(run_dir)
        data["complete_flag"] = complete_flag
        self._write_score_data(run_dir, data)

    def save_manual_feedback(self, model_id: str, task_name: str, run_id: str, manual_feedback: int) -> None:
        """只写该标记（1=好/-1=差/0=未标）。"""
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        data = self._load_score_data(run_dir)
        data["manual_feedback"] = int(manual_feedback)
        self._write_score_data(run_dir, data)

    def save_doubtful(self, model_id: str, task_name: str, run_id: str, doubtful: bool) -> None:
        """只写存疑标记。"""
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        data = self._load_score_data(run_dir)
        data["doubtful"] = bool(doubtful)
        self._write_score_data(run_dir, data)

    def save_trace_quality(
        self, model_id: str, task_name: str, run_id: str, trace_quality: dict
    ) -> None:
        """写 `trace_quality: {avg_score, dimensions}`（独立于总分，仅分析用）。"""
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        dimensions = trace_quality.get("dimensions") if isinstance(trace_quality, dict) else None
        if not isinstance(dimensions, dict) or not dimensions:
            raise ValueError("trace_quality.dimensions 缺失")
        values = [float(v) for v in dimensions.values()]
        data = self._load_score_data(run_dir)
        data["trace_quality"] = {
            "avg_score": round(sum(values) / len(values), 4),
            "dimensions": {str(k): float(v) for k, v in dimensions.items()},
        }
        self._write_score_data(run_dir, data)

    # ------------------------------------------------------------ 工作区

    WORKSPACE_ROOTS = ("workspace", "judge")

    def workspace_root_dir(
        self, model_id: str, task_name: str, run_id: str, root: str = "workspace"
    ) -> Path:
        if root not in self.WORKSPACE_ROOTS:
            raise ValueError(f"非法 root：{root}（合法：workspace/judge）")
        run_dir = self._resolve_writable_run_dir(model_id, task_name, run_id)
        if root == "judge":
            return run_dir / "verifier" / "judge"
        return run_dir / "workspace"

    def list_workspace_files(
        self, model_id: str, task_name: str, run_id: str, root: str = "workspace"
    ) -> dict:
        """递归文件树 `{files[], total_size, total_files}`。"""
        base = self.workspace_root_dir(model_id, task_name, run_id, root)
        files = self._walk(base)
        total_size = sum(f["size"] for f in files if f["type"] == "file")

        def count(tree: list[dict]) -> int:
            return sum(
                1 if f["type"] == "file" else count(f.get("children") or []) for f in tree
            )

        return {"files": files, "total_size": total_size, "total_files": count(files)}

    def _walk(self, base: Path) -> list[dict]:
        if not base.is_dir():
            return []
        result: list[dict] = []
        for child in sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            rel = child.relative_to(base)
            if child.is_dir():
                result.append(
                    {
                        "name": child.name,
                        "path": str(rel).replace("\\", "/"),
                        "size": 0,
                        "type": "dir",
                        "children": self._walk(child),
                    }
                )
            else:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = 0
                result.append(
                    {
                        "name": child.name,
                        "path": str(rel).replace("\\", "/"),
                        "size": size,
                        "type": "file",
                    }
                )
        return result

    def resolve_workspace_file(
        self, model_id: str, task_name: str, run_id: str, path: str, root: str = "workspace"
    ) -> Path:
        """单文件（**防路径穿越**）。"""
        base = self.workspace_root_dir(model_id, task_name, run_id, root).resolve()
        target = (base / path).resolve()
        if not target.is_relative_to(base):
            raise ValueError("非法路径（路径穿越）")
        if not target.is_file():
            raise FileNotFoundError(f"文件不存在：{path}")
        return target

    def build_workspace_zip(
        self, model_id: str, task_name: str, run_id: str, root: str = "workspace"
    ) -> tuple[Path, Path]:
        """流式下载任务子目录 ZIP（临时文件，响应后由 API 层删除）。"""
        import tempfile

        base = self.workspace_root_dir(model_id, task_name, run_id, root)
        if not base.is_dir():
            raise FileNotFoundError(f"{root} 目录不存在：{model_id}/{task_name}/{run_id}")
        tmp_dir = Path(tempfile.mkdtemp(prefix="openclaw_ms_ws_"))
        archive_base = tmp_dir / f"{task_name}_{run_id}_{root}"
        shutil.make_archive(str(archive_base), "zip", root_dir=str(base))
        return Path(str(archive_base) + ".zip"), tmp_dir

    # ------------------------------------------------------------ 模型管理

    def create_model(self, model_name: str, prefix: Optional[str] = None) -> str:
        """消毒名（拒 `/ \\ ..`），建目录 `{prefix_}{name}_{YYYYmmdd_HHMMSS}`，写空 result.json。"""
        sanitized = model_name.replace("/", "").replace("\\", "").replace("..", "").strip()
        if not sanitized or sanitized in (".", ".."):
            raise ValueError(f"非法模型名：{model_name!r}")
        prefix_san = (prefix or "").replace("/", "").replace("\\", "").replace("..", "").strip()
        name = f"{prefix_san + '_' if prefix_san else ''}{sanitized}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        model_dir = self.result_dir / name
        self.result_dir.mkdir(parents=True, exist_ok=True)
        model_dir.mkdir(exist_ok=False)
        write_json_atomic(
            model_dir / "result.json",
            {
                "summary": {
                    "total_tasks": 0,
                    "completed_tasks": 0,
                    "failed_tasks": 0,
                    "total_duration": 0.0,
                    "overall_score": 0.0,
                },
                "tasks": [],
            },
        )
        self.invalidate_models_cache()
        return name

    def delete_model(self, model_id: str, confirm_name: Optional[str] = None) -> None:
        """`{confirm_name}` 必须等于 model_id 才删（shutil.rmtree）。"""
        if confirm_name is not None and confirm_name != model_id:
            raise ValueError("confirm_name 必须等于 model_id")
        model_dir = self.result_dir / model_id
        if not model_dir.is_dir():
            raise FileNotFoundError(f"模型不存在：{model_id}")
        shutil.rmtree(model_dir)
        self.invalidate_models_cache()

    def delete_task(self, model_id: str, task_name: str) -> None:
        """删 case 目录 + 重建 result.json。"""
        case_dir = self._resolve_case_dir(model_id, task_name)
        shutil.rmtree(case_dir)
        self.rebuild_result_json(model_id)

    # ------------------------------------------------------------ 上传导入

    def list_case_names(self, model_id: str) -> list[str]:
        model_dir = self.result_dir / model_id
        if not model_dir.is_dir():
            return []
        return sorted(p.name for p in model_dir.iterdir() if p.is_dir() and discover_runs(p))

    def import_result_case(
        self, model_id: str, case_name: str, source_case_dir: Path, run_id: str,
        overwrite: bool = True,
    ) -> str:
        """拷贝结果 case 进 `{model}/<case>/{run}`（legacy run_1 原样写入；
        其他 run 先迁移 legacy→run_1/）。返回 "imported"/"skipped"。
        """
        model_dir = self.result_dir / model_id
        model_dir.mkdir(parents=True, exist_ok=True)
        dest_case = model_dir / case_name
        if run_id == "run_1" and is_legacy_single_run(source_case_dir):
            # legacy run_1 原样写入（case 根布局）
            if dest_case.exists():
                if not overwrite:
                    return "skipped"
                shutil.rmtree(dest_case)
            shutil.copytree(source_case_dir, dest_case)
            return "imported"
        if is_legacy_single_run(source_case_dir):
            migrate_legacy_to_run_1(source_case_dir)
        try:
            source_run_dir = resolve_run_dir(source_case_dir, run_id)
        except (ValueError, FileNotFoundError) as exc:
            raise ValueError(f"源 case 缺少 {run_id}：{case_name}") from exc
        dest_case.mkdir(parents=True, exist_ok=True)
        dest_run = dest_case / run_id
        if dest_run.exists():
            if not overwrite:
                return "skipped"
            shutil.rmtree(dest_run)
        shutil.copytree(source_run_dir, dest_run)
        return "imported"

    def import_usecase(
        self, case_name: str, source_case_dir: Path, overwrite: bool = True
    ) -> str:
        """拷贝用例进 `tasks_dir/<case>`。"""
        if self.tasks_dir is None:
            return "skipped"
        dest = self.tasks_dir / case_name
        if dest.exists():
            if not overwrite:
                return "skipped"
            shutil.rmtree(dest)
        shutil.copytree(source_case_dir, dest)
        return "imported"

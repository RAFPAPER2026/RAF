"""报告页数据加载（results/ 磁盘目录读取，`_MODELS_CACHE_TTL=2.0` 秒缓存）。"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from src.analyzer.core import (
    calculate_statistics,
    load_all_results_multi,
    load_task_configs,
    merge_task_data,
)
from src.analyzer.export import export_multi_run_to_excel, export_results_to_excel
from src.models import TaskConfig
from src.rubric.compat import detect_rubric_format, detect_score_format
from src.rubric.models import QueryRubric
from src.rubric.scoring import compute_rubric_score
from src.runs import (
    AVERAGE_RUN_ID,
    apply_legacy_compat,
    average_case_scores,
    list_model_runs,
    resolve_run_dir,
)

_MODELS_CACHE_TTL = 2.0


def parse_model_timestamp(model_id: str) -> str:
    """从 `{name}_{YYYYMMDD}_{HHMMSS}_{hash}` 解析时间戳（排序用），失败返回空串。"""
    parts = model_id.split("_")
    for i in range(len(parts) - 2, 0, -1):
        if (
            len(parts[i]) == 8
            and parts[i].isdigit()
            and i + 1 < len(parts)
            and len(parts[i + 1]) == 6
            and parts[i + 1].isdigit()
        ):
            return f"{parts[i]}_{parts[i + 1]}"
    return ""


class DataLoader:
    def __init__(self, result_base_dir: str | Path, tasks_dir: str | Path | None = None):
        self.result_base_dir = Path(result_base_dir)
        self.tasks_dir = Path(tasks_dir) if tasks_dir else None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._configs: Optional[dict[str, TaskConfig]] = None

    def _cached(self, key: str, producer: Any) -> Any:
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit is not None and now - hit[0] < _MODELS_CACHE_TTL:
            return hit[1]
        value = producer()
        self._cache[key] = (now, value)
        return value

    def _model_dir(self, model_id: str) -> Path:
        model_dir = self.result_base_dir / model_id
        if not model_dir.is_dir():
            raise FileNotFoundError(f"模型目录不存在：{model_id}")
        return model_dir

    def _load_configs(self) -> dict[str, TaskConfig]:
        if self._configs is None:
            self._configs = load_task_configs(self.tasks_dir)
        return self._configs

    # ------------------------------------------------------------ 模型列表

    def get_all_models(self) -> list[dict]:
        """`ModelInfo[]`（模型目录列表，名字前端解析；时间戳从目录名解析，按时间戳倒序）。"""
        return self._cached("models", self._load_models)

    def _load_models(self) -> list[dict]:
        if not self.result_base_dir.is_dir():
            return []
        models: list[dict] = []
        for child in sorted(self.result_base_dir.iterdir()):
            if not child.is_dir() or not (child / "result.json").is_file():
                continue
            scores = load_all_results_multi(child, AVERAGE_RUN_ID)
            stats = calculate_statistics(scores)
            info = list_model_runs(child)
            models.append(
                {
                    "id": child.name,
                    "runs": info["runs"],
                    "max_run": info["max_run"],
                    "stats": {
                        "average_score": stats["average_score"],
                        "pass_rate": stats["pass_rate"],
                        "total_tasks": stats["total_tasks"],
                        "total_duration": stats["total_duration"],
                        "total_input_tokens": stats["total_input_tokens"],
                        "total_output_tokens": stats["total_output_tokens"],
                    },
                }
            )
        models.sort(key=lambda m: parse_model_timestamp(m["id"]), reverse=True)
        return models

    # ------------------------------------------------------------ 任务列表

    def get_task_scores(self, model_id: str, run_id: str = AVERAGE_RUN_ID) -> list[dict]:
        """`TaskScore[]`（按 task_id 排序）。每任务合并 score.json 与 config.json。"""
        model_dir = self._model_dir(model_id)
        scores = load_all_results_multi(model_dir, run_id)
        configs = self._load_configs()
        result = [
            self._merge_task_score(name, score, configs.get(name), run_id)
            for name, score in scores.items()
        ]
        result.sort(key=lambda t: str(t.get("task_id") or t.get("task_name") or ""))
        return result

    def _merge_task_score(
        self, task_name: str, score: dict, config: Optional[TaskConfig], run_id: str
    ) -> dict:
        entry = dict(score)
        entry["task_name"] = task_name
        if config is not None:
            entry["task_id"] = config.id or task_name
            entry["prompt"] = config.prompt
            entry["verifier_type"] = (
                config.verifier_type or entry.get("verifier_type") or "manual"
            )
            entry["primary_scenario"] = config.primary_scenario or config.scenario_category
            entry["secondary_scenario"] = config.secondary_scenario
            entry["ability_category"] = list(config.ability_category)
            entry["difficulty"] = config.difficulty
            entry["complexity"] = config.complexity
            entry["rubric"] = config.rubric
        else:
            entry["task_id"] = task_name
            entry.setdefault("prompt", "")
            entry.setdefault("verifier_type", "manual")
        # status "success"→"completed"
        if entry.get("status") == "success":
            entry["status"] = "completed"
        # rubric 检测：仅 tree 格式带 rubric_results/completion/quality_score
        score_format = detect_score_format(entry)
        if score_format == "tree":
            entry["rubric_format"] = "tree"
        else:
            entry["rubric_format"] = "flat" if score_format == "flat" else None
            entry.pop("rubric_results", None)
            entry.pop("completion", None)
            entry.pop("quality_score", None)
        # 仅平均查询附加多轮字段（pass_at_k 来自 pass_at_1）
        if run_id == AVERAGE_RUN_ID:
            entry.setdefault("pass_at_k", entry.get("pass_at_1"))
        return entry

    # ------------------------------------------------------------ case 详情

    def get_case_detail(self, model_id: str, task_name: str, run_id: str = AVERAGE_RUN_ID) -> dict:
        """average → 直接用 `average_case_scores`（跳过 tree 重算——平均视图无叶子 map）；
        具体 run → `resolve_run_dir` + 读 score.json + `apply_legacy_compat`；tree rubric
        具体 run 有 rubric_results 时用 `compute_rubric_score` 权威重算（失败回退持久化值）。
        """
        case_dir = self._model_dir(model_id) / task_name
        config = self._load_configs().get(task_name)
        if run_id == AVERAGE_RUN_ID:
            score = average_case_scores(case_dir)
            if score is None:
                raise FileNotFoundError(f"任务无可用 run：{task_name}")
        else:
            run_dir = resolve_run_dir(case_dir, run_id)
            score = apply_legacy_compat(
                dict(json.loads((run_dir / "score.json").read_text(encoding="utf-8")))
            )
            if config is not None and detect_rubric_format(config.rubric) == "tree":
                rubric = QueryRubric.model_validate(config.rubric)
                rubric_results = score.get("rubric_results")
                if isinstance(rubric_results, dict):
                    try:
                        derived = compute_rubric_score(rubric, rubric_results)
                    except (ValueError, TypeError):
                        pass
                    else:
                        score["completion"] = derived["completion"]
                        score["quality_score"] = derived["quality_score"]
                        score["score"] = derived["score"]
                        score["completion_rate"] = derived["completion_rate"]
                        score["complete_flag"] = derived["complete_flag"]
                        score["rubric_format"] = "tree"
        sessions: Any = None
        session_run = run_id if run_id != AVERAGE_RUN_ID else "run_1"
        try:
            sessions_dir = resolve_run_dir(case_dir, session_run)
            sessions_path = sessions_dir / "sessions.json"
            if sessions_path.is_file():
                sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
        except (ValueError, FileNotFoundError, OSError):
            pass
        config_data: Optional[dict] = config.model_dump() if config is not None else None
        if config is not None and isinstance(config_data, dict):
            config_data["rubric_format"] = detect_rubric_format(config.rubric)
        return {"task_name": task_name, "score": score, "config": config_data, "sessions": sessions}

    # ------------------------------------------------------------ 统计/对比

    def get_model_runs(self, model_id: str) -> dict:
        return list_model_runs(self._model_dir(model_id))

    def get_model_overall(self, model_id: str, run_id: str = AVERAGE_RUN_ID) -> dict:
        scores = load_all_results_multi(self._model_dir(model_id), run_id)
        return calculate_statistics(merge_task_data(scores, self._load_configs()))

    def get_categories(self, model_id: str, run_id: str = AVERAGE_RUN_ID) -> list[dict]:
        """`CategoryStats[]`（主/次场景、能力、难度、复杂度，扁平合并）。"""
        scores = load_all_results_multi(self._model_dir(model_id), run_id)
        stats = calculate_statistics(merge_task_data(scores, self._load_configs()))
        result: list[dict] = []
        for dimension_groups in stats["by_dimension"].values():
            for category, group in dimension_groups.items():
                result.append(
                    {
                        "category": category,
                        "count": group["count"],
                        "avg_score": group["avg_score"],
                        "pass_rate": group["pass_rate"],
                    }
                )
        result.sort(key=lambda c: -c["count"])
        return result

    def get_comparison_data(
        self, dimension: str = "primary_scenario", run_id: str = AVERAGE_RUN_ID
    ) -> dict:
        """`{dimension, categories[], models:[{id, name, scores, overall, pass_rate}]}`。
        overall/pass_rate 用本次 run_id 的 stats（保持 `?run_id=run_n` 一致）。
        """
        configs = self._load_configs()
        models: list[dict] = []
        categories: set[str] = set()
        for model in self.get_all_models():
            scores = load_all_results_multi(self.result_base_dir / model["id"], run_id)
            stats = calculate_statistics(merge_task_data(scores, configs))
            groups = stats["by_dimension"].get(dimension, {})
            entry = {
                "id": model["id"],
                "name": model["id"],
                "scores": {},
                "overall": stats["average_score"],
                "pass_rate": stats["pass_rate"],
            }
            for category, group in groups.items():
                if group["avg_score"] is not None:
                    entry["scores"][category] = round(group["avg_score"], 4)
                    categories.add(category)
            models.append(entry)
        return {"dimension": dimension, "categories": sorted(categories), "models": models}

    def get_dataset_distribution(self) -> dict:
        """`{difficulty:{level:count}, complexity:{level:count}}`（来自 tasks_dir 各 config.json）。"""
        difficulty: Counter = Counter()
        complexity: Counter = Counter()
        for config in self._load_configs().values():
            if config.difficulty:
                difficulty[config.difficulty] += 1
            if config.complexity:
                complexity[config.complexity] += 1
        return {
            "difficulty": dict(sorted(difficulty.items())),
            "complexity": dict(sorted(complexity.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)),
        }

    # ------------------------------------------------------------ 产物

    def get_sessions(self, model_id: str, task_name: str, run_id: str = "run_1") -> dict:
        run_dir = resolve_run_dir(self._model_dir(model_id) / task_name, run_id)
        sessions_path = run_dir / "sessions.json"
        if not sessions_path.is_file():
            raise FileNotFoundError(f"sessions.json 不存在：{task_name}/{run_id}")
        return json.loads(sessions_path.read_text(encoding="utf-8"))

    def build_workspace_zip(self, model_id: str, task_name: str, run_id: str = "run_1") -> Path:
        run_dir = resolve_run_dir(self._model_dir(model_id) / task_name, run_id)
        workspace = run_dir / "workspace"
        if not workspace.is_dir():
            raise FileNotFoundError(f"workspace 不存在：{task_name}/{run_id}")
        tmp_dir = Path(tempfile.mkdtemp(prefix="openclaw_ws_"))
        base = tmp_dir / f"{task_name}_{run_id}_workspace"
        shutil.make_archive(str(base), "zip", root_dir=str(workspace))
        return Path(str(base) + ".zip")

    def export_model(self, model_id: str, run_id: str = AVERAGE_RUN_ID) -> Path:
        """导出 `.xlsx`（`{model_id}_analysis_report.xlsx`，临时文件由 API 层 BackgroundTask 清理）。"""
        model_dir = self._model_dir(model_id)
        tmp_dir = Path(tempfile.mkdtemp(prefix="openclaw_export_"))
        out_path = tmp_dir / f"{model_id}_analysis_report.xlsx"
        if run_id == AVERAGE_RUN_ID and list_model_runs(model_dir)["max_run"] > 1:
            export_multi_run_to_excel(model_dir, out_path, self.tasks_dir)
        else:
            scores = load_all_results_multi(model_dir, run_id)
            task_data = merge_task_data(scores, self._load_configs())
            export_results_to_excel(task_data, out_path)
        return out_path


_data_loader: Optional[DataLoader] = None


def init_loader(result_dir: str | Path, tasks_dir: str | Path | None = None) -> DataLoader:
    """全局 `data_loader` 单例注入。"""
    global _data_loader
    _data_loader = DataLoader(result_dir, tasks_dir)
    return _data_loader


def get_loader() -> DataLoader:
    global _data_loader
    if _data_loader is None:
        _data_loader = DataLoader("results")
    return _data_loader

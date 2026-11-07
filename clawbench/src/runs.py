"""多轮(run_n)存储/发现/平均 + per-run result.json（核心）。

磁盘布局：`results/<model_dir>/<case>/` 下为 legacy run_1（score.json 等在 case 根）
或现代布局（`run_1/ .. run_n/` 子目录）。`build_per_run_result_json` 是 result.json
结构的唯一事实来源（纯函数不落盘）。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from src.rubric.compat import detect_score_format

RUN_PREFIX = "run_"
AVERAGE_RUN_ID = "average"
PASS_THRESHOLD_KEY = "pass_threshold"
LEGACY_THRESHOLD_KEY = "legacy_threshold"
DEFAULT_PASS_THRESHOLD = 0.75

# 损坏 run 跳过时捕获的异常（平均逻辑）
_CORRUPT_ERRORS = (
    FileNotFoundError,
    json.JSONDecodeError,
    OSError,
    TypeError,
    ValueError,
    AttributeError,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRACE_CONFIG_PATH = _PROJECT_ROOT / "configs" / "trace_config.json"

# k>1 均值字段（见 average_case_scores）
_MEAN_FIELDS = (
    "score",
    "duration",
    "input_tokens",
    "output_tokens",
    "input_cost",
    "output_cost",
    "tool_calls",
    "tool_success",
    "tool_failed",
    "error_recoveries",
    "api_calls",
    "completion_rate",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _run_number(run_id: str) -> int:
    m = re.fullmatch(r"run_(\d+)", run_id)
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------- 配置

def load_trace_config(path: str | Path | None = None) -> dict:
    """读取 trace_config.json（过程评价维度 + pass_threshold）。"""
    try:
        p = Path(path) if path else TRACE_CONFIG_PATH
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_pass_threshold(trace_config: dict | None = None) -> float:
    """统一通过阈值：`pass_threshold` 优先；旧 `legacy_threshold` 键兼容；
    两者都缺省时默认 0.75。
    """
    if trace_config is None:
        trace_config = load_trace_config()
    if isinstance(trace_config, dict):
        if PASS_THRESHOLD_KEY in trace_config:
            return float(trace_config[PASS_THRESHOLD_KEY])
        if LEGACY_THRESHOLD_KEY in trace_config:
            return float(trace_config[LEGACY_THRESHOLD_KEY])
    return DEFAULT_PASS_THRESHOLD


def derive_complete_flag(score: float | None, threshold: float | None = None) -> int | None:
    """score vs 0.75 → complete_flag（非 manual 任务打分时写入）。"""
    if score is None:
        return None
    thr = load_pass_threshold() if threshold is None else threshold
    return 1 if float(score) >= thr else 0


def _is_passed(score_data: dict, threshold: float | None = None) -> bool:
    """通过/失败判定（全链路一致）：`complete_flag == 1` 即通过、`== 0` 即未通过
    （完成度是硬性闸门）；旧数据（无该键或显式 null）回退 `score >= pass_threshold`。
    """
    if not isinstance(score_data, dict):
        return False
    flag = score_data.get("complete_flag")
    if flag == 1:
        return True
    if flag == 0:
        return False
    score = score_data.get("score")
    if score is None:
        return False
    thr = load_pass_threshold() if threshold is None else threshold
    try:
        return float(score) >= thr
    except (TypeError, ValueError):
        return False


is_passed = _is_passed  # 语义别名


# ---------------------------------------------------------------- run 发现/解析

def discover_runs(case_dir: str | Path) -> list[str]:
    """扫描 `run_*` 子目录取数字后缀升序；有 run_* 时忽略 case 根 score.json（视为陈旧）；
    无 run_* 但有根 score.json → `["run_1"]`（legacy）；都没有 → `[]`。
    """
    case_dir = Path(case_dir)
    if not case_dir.is_dir():
        return []
    nums: list[int] = []
    for child in case_dir.iterdir():
        if not child.is_dir() or not child.name.startswith(RUN_PREFIX):
            continue
        suffix = child.name[len(RUN_PREFIX):]
        if suffix.isdigit():
            nums.append(int(suffix))
    nums.sort()
    if nums:
        return [f"{RUN_PREFIX}{n}" for n in nums]
    if (case_dir / "score.json").is_file():
        return ["run_1"]
    return []


def resolve_run_dir(case_dir: str | Path, run_id: str) -> Path:
    """`"average"` 抛 ValueError（不是磁盘目录）；缺失 run 抛 FileNotFoundError；
    legacy run_1（无 run_* 子目录）解析到 case 根目录。
    """
    case_dir = Path(case_dir)
    if run_id == AVERAGE_RUN_ID:
        raise ValueError(f"'{AVERAGE_RUN_ID}' 不是磁盘目录，请使用具体 run_id")
    # 有 run_* 子目录 → 现代布局，必须解析到子目录
    if _has_run_subdirs(case_dir):
        if run_id.startswith(RUN_PREFIX) and (case_dir / run_id).is_dir():
            return case_dir / run_id
        raise FileNotFoundError(f"run '{run_id}' 不存在于 {case_dir}")
    # 无 run_* 子目录：legacy run_1 解析到 case 根
    if run_id == "run_1" and (case_dir / "score.json").is_file():
        return case_dir
    raise FileNotFoundError(f"run '{run_id}' 不存在于 {case_dir}")


def _has_run_subdirs(case_dir: Path) -> bool:
    return any(
        child.is_dir()
        and child.name.startswith(RUN_PREFIX)
        and child.name[len(RUN_PREFIX):].isdigit()
        for child in case_dir.iterdir()
    )


def is_legacy_single_run(case_dir: str | Path) -> bool:
    """无 run_* 子目录且 case 根存在 score.json（上传时用于「原样写入」vs「迁移到 run_1/」）。"""
    case_dir = Path(case_dir)
    if not case_dir.is_dir():
        return False
    return not _has_run_subdirs(case_dir) and (case_dir / "score.json").is_file()


# 迁移到 run_1/ 时随迁的内容
_MIGRATABLE = ("score.json", "sessions.json", "workspace", "verifier")


def migrate_legacy_to_run_1(case_dir: str | Path) -> Path:
    """把 case 根的 legacy run_1 内容迁移到 `run_1/` 子目录，返回新 run 目录。"""
    case_dir = Path(case_dir)
    run_dir = case_dir / "run_1"
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in _MIGRATABLE:
        src = case_dir / name
        dst = run_dir / name
        if src.exists() and not dst.exists():
            src.rename(dst)
    return run_dir


# ---------------------------------------------------------------- 模型级

def iter_case_dirs(model_dir: str | Path) -> list[Path]:
    """模型目录下的 case 目录（有 score.json 或 run_* 子目录的子目录，按名排序）。"""
    model_dir = Path(model_dir)
    if not model_dir.is_dir():
        return []
    return sorted(
        (child for child in model_dir.iterdir() if child.is_dir() and discover_runs(child)),
        key=lambda p: p.name,
    )


def list_model_runs(model_dir: str | Path) -> dict:
    """`{runs, max_run, per_case_runs: {case: [run ids]}}`，runs 为全 case 升序并集。"""
    per_case: dict[str, list[str]] = {}
    all_runs: list[str] = []
    for case_dir in iter_case_dirs(model_dir):
        runs = discover_runs(case_dir)
        per_case[case_dir.name] = runs
        for run_id in runs:
            if run_id not in all_runs:
                all_runs.append(run_id)
    all_runs.sort(key=_run_number)
    max_run = max((_run_number(r) for r in all_runs), default=0)
    return {"runs": all_runs, "max_run": max_run, "per_case_runs": per_case}


def next_run_id(model_dir: str | Path) -> str:
    """模型级 `max_run+1`（跨 case 保持 run id 对齐）。"""
    return f"{RUN_PREFIX}{list_model_runs(model_dir)['max_run'] + 1}"


# ---------------------------------------------------------------- legacy 兼容

def apply_legacy_compat(score_data: dict) -> dict:
    """从旧 `dimension_scores`/`manual_score` 格式合成 `rubric_scores`/`completion_rate`/
    `trace_quality`/`complete_flag`/`manual_feedback`/`doubtful`。

    - tree 格式短路（tree 数据自带派生字段）
    - `complete_flag` 仅在键完全缺失时推断
    - 非 tree 的 `score`/`completion_rate` 由 `rubric_scores` 权威派生（flat 公式）；
      无 rubric_scores 且无 manual_score/score 时不动分数（未打分任务保持未打分）
    """
    if not isinstance(score_data, dict):
        return score_data
    if detect_score_format(score_data) == "tree":
        return score_data

    # 旧 dimension_scores → trace_quality
    if "trace_quality" not in score_data:
        dims = score_data.get("dimension_scores")
        if isinstance(dims, dict) and dims:
            values = [float(v) for v in dims.values()]
            score_data["trace_quality"] = {
                "avg_score": _mean(values),
                "dimensions": {str(k): float(v) for k, v in dims.items()},
            }

    # 旧 manual_score/score → rubric_scores
    if not isinstance(score_data.get("rubric_scores"), list):
        base = score_data.get("manual_score")
        if base is None:
            base = score_data.get("score")
        if _is_number(base):
            score_data["rubric_scores"] = [
                {"completion": 1, "quality_score": float(base), "item_score": float(base)}
            ]

    # flat 公式权威派生（rubric_scores 为空列表时分数清零）
    rubric_scores = score_data.get("rubric_scores")
    if isinstance(rubric_scores, list):
        completions = [
            float(r.get("completion", 0) or 0) for r in rubric_scores if isinstance(r, dict)
        ]
        item_scores = [
            float(r.get("item_score", 0) or 0) for r in rubric_scores if isinstance(r, dict)
        ]
        score_data["completion_rate"] = _mean(completions) if completions else 0.0
        score_data["score"] = _mean(item_scores) if item_scores else 0.0

    # complete_flag 仅在键完全缺失时推断
    if "complete_flag" not in score_data:
        score = score_data.get("score")
        score_data["complete_flag"] = derive_complete_flag(score) if _is_number(score) else None
    score_data.setdefault("manual_feedback", 0)
    score_data.setdefault("doubtful", False)
    return score_data


# ---------------------------------------------------------------- 多轮平均

def _average_trace_quality(runs: list[dict]) -> dict | None:
    """per-run `avg_score` 与各维度取均值。"""
    dim_sums: dict[str, list[float]] = {}
    avg_scores: list[float] = []
    for run in runs:
        tq = run.get("trace_quality")
        if not isinstance(tq, dict):
            continue
        avg = tq.get("avg_score")
        if _is_number(avg):
            avg_scores.append(float(avg))
        dims = tq.get("dimensions")
        if isinstance(dims, dict):
            for key, value in dims.items():
                if _is_number(value):
                    dim_sums.setdefault(str(key), []).append(float(value))
    if not avg_scores and not dim_sums:
        return None
    result: dict[str, Any] = {}
    if avg_scores:
        result["avg_score"] = _mean(avg_scores)
    if dim_sums:
        result["dimensions"] = {k: _mean(v) for k, v in dim_sums.items()}
    return result


def average_case_scores(case_dir: str | Path, trace_config: dict | None = None) -> dict | None:
    """多轮平均核心逻辑。逐 run 加载 score.json + `apply_legacy_compat`，
    跳过损坏 run（捕获 `(FileNotFoundError, json.JSONDecodeError, OSError, TypeError,
    ValueError, AttributeError)`）；无可用 run → None。

    - k==1 短路：直接返回该 run 的真实 dict（平均单个 run 会把 per-run 字段抹成假 0）
    - k>1：均值字段平均；`quality_score` 仅当每个 run 都有数值才平均；`manual_score`
      对非 None 取均值
    - `status` = "completed" 需 `completed_count * 2 > k`（严格多数；k=2 平局判失败）
    - pass@k：`pass_rate_over_runs` = 通过 run 数 / k；`pass_at_1` = 至少一个 run 通过；
      `pass_k` = 全部 run 通过；`complete_flag` = pass_k 为真时 1，否则 0
    - `runs[]` 钻取（供前端）；额外字段 `run_count/pass_rate_over_runs/pass_at_1/pass_k/mean_score/runs`
    - 守卫：非 tree 的 manual 任务若 manual_score 有均值，合成一个 `rubric_scores` 项
    """
    case_dir = Path(case_dir)
    run_ids = discover_runs(case_dir)
    threshold = load_pass_threshold(trace_config)
    loaded: list[tuple[str, dict]] = []
    for run_id in run_ids:
        try:
            run_dir = resolve_run_dir(case_dir, run_id)
            raw = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
        except _CORRUPT_ERRORS:
            continue
        if not isinstance(raw, dict):
            continue
        loaded.append((run_id, apply_legacy_compat(dict(raw))))
    if not loaded:
        return None
    k = len(run_ids)
    if k == 1:
        return loaded[0][1]

    result: dict[str, Any] = {}
    for field in _MEAN_FIELDS:
        values = [d.get(field) for _, d in loaded if _is_number(d.get(field))]
        if values:
            result[field] = _mean([float(v) for v in values])
    # quality_score 仅当每个 run 都有数值才平均
    if all(_is_number(d.get("quality_score")) for _, d in loaded):
        result["quality_score"] = _mean([float(d["quality_score"]) for _, d in loaded])
    # manual_score 对非 None 取均值
    manual_values = [d.get("manual_score") for _, d in loaded if _is_number(d.get("manual_score"))]
    result["manual_score"] = _mean([float(v) for v in manual_values]) if manual_values else None

    completed_count = sum(1 for _, d in loaded if d.get("status") == "completed")
    result["status"] = "completed" if completed_count * 2 > k else "failed"

    passed_by_run = [(run_id, _is_passed(d, threshold)) for run_id, d in loaded]
    passed_count = sum(1 for _, passed in passed_by_run if passed)
    result["pass_rate_over_runs"] = passed_count / k
    result["pass_at_1"] = passed_count >= 1
    result["pass_k"] = passed_count == k
    result["complete_flag"] = 1 if result["pass_k"] else 0

    result["runs"] = [
        {
            "run_id": run_id,
            "score": d.get("score"),
            "status": d.get("status"),
            "complete_flag": d.get("complete_flag"),
            "quality_score": d.get("quality_score"),
            "completion_rate": d.get("completion_rate"),
            "duration": d.get("duration"),
            "passed": _is_passed(d, threshold),
            "rubric_results": d.get("rubric_results"),
        }
        for run_id, d in loaded
    ]
    result["run_count"] = k
    scores = [d.get("score") for _, d in loaded if _is_number(d.get("score"))]
    result["mean_score"] = _mean([float(v) for v in scores]) if scores else None

    trace_quality = _average_trace_quality([d for _, d in loaded])
    if trace_quality is not None:
        result["trace_quality"] = trace_quality

    # 全部 run 为 tree 时标记平均结果亦为 tree（避免后续 flat 兼容把分数清零）；
    # 平均视图不携带顶层 rubric_results（标签聚合从 runs[] 逐 run 取）
    if all(detect_score_format(d) == "tree" for _, d in loaded):
        result["rubric_format"] = "tree"

    # 守卫：非 tree 的 manual 任务若 manual_score 有均值，合成一个 rubric_scores 项，
    # 避免后续 apply_legacy_compat 把分数清零
    if detect_score_format(result) != "tree" and result.get("manual_score") is not None:
        m = float(result["manual_score"])
        result["rubric_scores"] = [{"completion": 1, "quality_score": m, "item_score": m}]
    return result


def synthesize_model_task_scores(
    model_dir: str | Path,
    run_id: str = AVERAGE_RUN_ID,
    trace_config: dict | None = None,
) -> dict[str, dict]:
    """委托 `average_case_scores` 或读具体 run：`"average"` → 逐 case 平均、
    无 run 的 case 丢弃；具体 run → 读该 run 原始 score.json，缺该 run 的 case 跳过。
    """
    model_dir = Path(model_dir)
    out: dict[str, dict] = {}
    for case_dir in iter_case_dirs(model_dir):
        if run_id == AVERAGE_RUN_ID:
            avg = average_case_scores(case_dir, trace_config)
            if avg is not None:
                out[case_dir.name] = avg
            continue
        try:
            run_dir = resolve_run_dir(case_dir, run_id)
            raw = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
        except _CORRUPT_ERRORS:
            continue
        if isinstance(raw, dict):
            out[case_dir.name] = apply_legacy_compat(dict(raw))
    return out


# ---------------------------------------------------------------- result.json

def build_per_run_result_json(task_scores: dict[str, dict[str, dict]]) -> dict:
    """result.json 结构的唯一事实来源（纯函数不落盘）。

    输入 `{task_name: {run_id: score_dict}}`。
    - `summary`：total_tasks/completed_tasks/failed_tasks/total_duration/overall_score
    - `tasks[]`：每任务 `runs` 对象（`{score, manual_score, status, duration}`）+ 镜像
      run_1 的扁平字段（legacy 消费方兼容）
    - 顶层 `manual_score` 保持 None、从不回退到 score
    - `total_duration` = 所有 run 的各 case 时长总和（非 legacy 重跑墙钟时间）；
      `overall_score` = 各 case 的 per-run 分数均值再对 case 取均值
    """
    tasks: list[dict] = []
    total_duration = 0.0
    case_means: list[float] = []
    completed = failed = 0
    for task_name in sorted(task_scores.keys()):
        runs_map = task_scores.get(task_name) or {}
        run_entries: dict[str, dict] = {}
        run_scores: list[float] = []
        for run_id in sorted(runs_map.keys(), key=_run_number):
            s = runs_map[run_id] if isinstance(runs_map[run_id], dict) else {}
            entry = {
                "score": s.get("score"),
                "manual_score": s.get("manual_score"),
                "status": s.get("status"),
                "duration": s.get("duration"),
            }
            run_entries[run_id] = entry
            if _is_number(entry["score"]):
                run_scores.append(float(entry["score"]))
            if _is_number(entry["duration"]):
                total_duration += float(entry["duration"])
        first = runs_map.get("run_1") or {}
        task_entry = {
            "task_name": task_name,
            "runs": run_entries,
            "score": first.get("score"),
            "manual_score": first.get("manual_score"),
            "status": first.get("status"),
            "duration": first.get("duration"),
        }
        if task_entry["status"] == "completed":
            completed += 1
        else:
            failed += 1
        tasks.append(task_entry)
        if run_scores:
            case_means.append(_mean(run_scores))
    summary = {
        "total_tasks": len(tasks),
        "completed_tasks": completed,
        "failed_tasks": failed,
        "total_duration": total_duration,
        "overall_score": _mean(case_means) if case_means else 0.0,
    }
    return {"summary": summary, "tasks": tasks}


def collect_per_run_scores(model_dir: str | Path) -> dict[str, dict[str, dict]]:
    """从磁盘收集 `{task_name: {run_id: score_dict}}`；损坏/缺失的 run score.json 跳过。"""
    model_dir = Path(model_dir)
    task_scores: dict[str, dict[str, dict]] = {}
    for case_dir in iter_case_dirs(model_dir):
        for run_id in discover_runs(case_dir):
            try:
                run_dir = resolve_run_dir(case_dir, run_id)
                data = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
            except _CORRUPT_ERRORS:
                continue
            if isinstance(data, dict):
                task_scores.setdefault(case_dir.name, {})[run_id] = data
    return task_scores


def build_result_json_from_disk(model_dir: str | Path) -> dict:
    """收集磁盘数据并构建 result.json（损坏的 result.json 整体重建亦走此路径）。"""
    return build_per_run_result_json(collect_per_run_scores(model_dir))


def write_json_atomic(path: str | Path, data: Any) -> None:
    """tempfile + `os.replace` 原子写。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_result_json(model_dir: str | Path) -> dict:
    """重建并原子写入 `{model_dir}/result.json`，返回写入的数据。"""
    data = build_result_json_from_disk(model_dir)
    write_json_atomic(Path(model_dir) / "result.json", data)
    return data

"""PROMPT-R 优化编排器：6 步循环 + 中止阈值。

循环：start_round → 批量生成 → submit_scores → save_round_metrics → analyze_round → apply_accepted_suggestions → check_stopping
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import metrics as metrics_mod
from . import storage
from .models import new_id, now_iso
from .models_optim import (
    FailureFinding,
    OptimizationRun,
    OptimizationSuggestion,
    RoundDiagnosis,
    RoundMetrics,
    RoundQualityReview,
    RoundResult,
    ScoreEntry,
    ScoreSheet,
    StoppingCheck,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RUNS_DIR = DATA_DIR / "optimization_runs"

_lock = threading.RLock()

# 人工质量初筛：可初筛/改判的轮次状态（进入评分或诊断后锁定）
REVIEWABLE_STATUSES = ("generated", "generate_error", "rejected")

# 中止阈值
DEFAULT_THRESHOLDS = {
    "pearson_r_target": 0.85,      # 达标标准
    "qwk_target": 0.75,            # 达标标准
    "min_delta": 0.02,             # 收敛判断：连续 2 轮改善不足
    "max_rounds": 10,              # 预算上限
    "degradation_threshold": -0.05,  # 退化判断
}

# ---------- 运行持久化 ----------

def _run_path(run_id: str) -> Path:
    # run_id 本身已含 run- 前缀（new_id("run")）
    return RUNS_DIR / f"{run_id}.json"


def _load_run(run_id: str) -> OptimizationRun | None:
    path = _run_path(run_id)
    if not path.exists():
        return None
    try:
        return OptimizationRun(**json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _save_run(run: OptimizationRun) -> None:
    with _lock:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        _run_path(run.run_id).write_text(run.model_dump_json(indent=2), encoding="utf-8")


def _require_run(run_id: str) -> OptimizationRun:
    run = _load_run(run_id)
    if run is None:
        raise ValueError(f"优化运行不存在: {run_id}")
    return run


def _require_round(run: OptimizationRun, round_number: int) -> RoundResult:
    for r in run.rounds:
        if r.round_number == round_number:
            return r
    raise ValueError(f"轮次不存在: round {round_number}")


# ---------- 运行 CRUD ----------

def create_run(name: str, query_ids: list[str], rater_ids: list[str], prompt_version: str) -> OptimizationRun:
    from . import prompt_modules
    if prompt_modules.load_version(prompt_version) is None:
        raise ValueError(f"prompt 版本不存在: {prompt_version}")
    if not query_ids:
        raise ValueError("query_ids 不能为空")
    if not rater_ids:
        raise ValueError("rater_ids 不能为空（含 gold）")
    from .query_store import get_query
    missing = [qid for qid in query_ids if get_query(qid) is None]
    if missing:
        raise ValueError(f"query 不存在: {missing}")
    run = OptimizationRun(
        run_id=new_id("run"),
        name=name or f"run-{len(list_runs()) + 1}",
        query_ids=query_ids,
        rater_ids=rater_ids,
        current_prompt_version=prompt_version,
        status="running",
    )
    _save_run(run)
    return run


def list_runs() -> list[OptimizationRun]:
    runs = []
    if RUNS_DIR.exists():
        for path in RUNS_DIR.glob("run-*.json"):
            try:
                runs.append(OptimizationRun(**json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
    runs.sort(key=lambda r: r.created_at, reverse=True)
    return runs


def get_run(run_id: str) -> OptimizationRun | None:
    return _load_run(run_id)


def delete_run(run_id: str) -> bool:
    """删除一个优化运行（含全部轮次记录）。文件不存在返回 False。"""
    with _lock:
        path = _run_path(run_id)
        if not path.exists():
            return False
        path.unlink()
        return True


def get_run_detail(run_id: str) -> dict | None:
    """运行详情：每个轮次附带该轮次生成的 rubric（query_ids × prompt_version）。"""
    run = get_run(run_id)
    if run is None:
        return None
    # 自愈：进程重启后内存任务注册表清空，卡在 generating 的轮次标记为 generate_error
    healed = False
    with _lock:
        for r in run.rounds:
            if r.status == "generating" and r.generation_task_id and get_batch_task(r.generation_task_id) is None:
                r.status = "generate_error"
                r.updated_at = now_iso()
                healed = True
        if healed:
            _save_run(run)
    data = run.model_dump()
    for round_data in data["rounds"]:
        round_data["rubrics"] = storage.list_rubrics_for_query_ids_version(
            run.query_ids, round_data["prompt_version"]
        )
    return data


# ---------- 批量生成引擎（/api/generate/batch 与轮次生成共用） ----------

_batch_tasks: dict[str, dict] = {}


def run_batch_generation(queries: list[tuple[str, str]], prompt_version: str,
                         concurrency: int = 16, model: str | None = None,
                         progress_cb=None, done_cb=None) -> str:
    """后台线程批量生成 rubric。queries: [(text, query_id)]。返回 task_id。

    流程：先删除同 (query, prompt_version) 的旧数据，再用线程池并行生成。
    """
    task_id = new_id("task")
    task = {
        "task_id": task_id,
        "status": "running",
        "prompt_version": prompt_version,
        "total": len(queries),
        "progress": {text: "pending" for text, _ in queries},  # pending/generating/done/error
        "errors": {},
    }
    with _lock:
        _batch_tasks[task_id] = task

    def _work():
        from .query_store import find_query_by_text
        from generate_rubric import generate_rubric

        task["status"] = "generating"
        # 删除同 (query, version) 旧数据，避免重复
        for text, _qid in queries:
            storage.remove_by_query_version(text, prompt_version)

        def _one(text_qid: tuple[str, str]):
            text, query_id = text_qid
            task["progress"][text] = "generating"
            if progress_cb:
                try:
                    progress_cb(task_id, text, "generating")
                except Exception:
                    pass
            try:
                rubric = generate_rubric(text, model=model, prompt_version=prompt_version)
                if not query_id:
                    item = find_query_by_text(text)
                    query_id = item.id if item else ""
                storage.create_rubric(rubric, query_id=query_id)
                task["progress"][text] = "done"
            except Exception as exc:  # noqa: BLE001
                task["progress"][text] = "error"
                task["errors"][text] = str(exc)

        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
            list(ex.map(_one, queries))

        task["status"] = "error" if (task["errors"] and len(task["errors"]) == len(queries)) else "done"
        if done_cb:
            try:
                done_cb(task_id, task)
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()
    return task_id


def get_batch_task(task_id: str) -> dict | None:
    with _lock:
        return _batch_tasks.get(task_id)


# ---------- 6 步循环 ----------

def start_round(run_id: str) -> RoundResult:
    """Step 1: 创建轮次，记录当前 prompt 版本，并触发后台批量生成。"""
    from .query_store import get_query
    with _lock:
        run = _require_run(run_id)
        for r in run.rounds:
            if r.status in ("generating", "pending"):
                raise ValueError(f"已有进行中的轮次: round {r.round_number}")
        if len(run.rounds) >= DEFAULT_THRESHOLDS["max_rounds"]:
            raise ValueError(f"已达最大轮次预算 ({DEFAULT_THRESHOLDS['max_rounds']})")
        # 先解析 query，避免创建出无任务可跑的轮次
        queries = []
        for qid in run.query_ids:
            q = get_query(qid)
            if q:
                queries.append((q.text, q.id))
        if not queries:
            raise ValueError("运行涉及的 query 不存在，请检查 query_ids")
        round_number = len(run.rounds) + 1
        round_result = RoundResult(
            round_number=round_number,
            prompt_version=run.current_prompt_version,
            status="generating",
        )
        run.rounds.append(round_result)
        run.updated_at = now_iso()
        _save_run(run)

    def _done(task_id: str, task: dict):
        with _lock:
            run2 = _load_run(run_id)
            if run2 is None:
                return
            for r in run2.rounds:
                if r.round_number == round_number:
                    r.generation_task_id = task_id
                    r.status = "generated" if task["status"] == "done" else "generate_error"
                    r.updated_at = now_iso()
                    break
            run2.updated_at = now_iso()
            _save_run(run2)

    task_id = run_batch_generation(queries, round_result.prompt_version, done_cb=_done)
    with _lock:
        run2 = _load_run(run_id)
        for r in run2.rounds:
            if r.round_number == round_number:
                r.generation_task_id = task_id
                break
        _save_run(run2)
    return round_result


def _review_rejected(round_result: RoundResult) -> bool:
    """粘性否决：只要初筛记录为 rejected 即拒绝评分/指标（否决轮诊断后 status 变 analyzed，守卫挂记录上）。"""
    return round_result.quality_review is not None and round_result.quality_review.decision == "rejected"


def review_round_quality(run_id: str, round_number: int, decision: str, comment: str = "") -> RoundResult:
    """Step 2.5: 本批 rubric 人工质量初筛（整批一次判断）。

    approved（尚可）→ 照常走评分流程，status 不变；rejected（不行）→ 跳过评分与指标，
    status 置 "rejected"，由人手动触发 RIFT 诊断。可改判窗口：generated/generate_error/rejected。
    """
    if decision not in ("approved", "rejected"):
        raise ValueError(f"未知初筛结论: {decision}（应为 approved / rejected）")
    with _lock:
        run = _require_run(run_id)
        round_result = _require_round(run, round_number)
        if round_result.status not in REVIEWABLE_STATUSES:
            raise ValueError(f"该轮当前状态 {round_result.status} 不允许初筛（仅 generated / generate_error / rejected）")
        rubrics = storage.list_rubrics_for_query_ids_version(run.query_ids, round_result.prompt_version)
        if not rubrics:
            raise ValueError("该轮没有 rubric 可审（生成可能失败）")
        round_result.quality_review = RoundQualityReview(
            decision=decision,
            comment=(comment or "").strip(),
        )
        if decision == "rejected":
            round_result.status = "rejected"
        elif round_result.status == "rejected":
            # 否决后改判回尚可：恢复可评分状态
            round_result.status = "generated"
        round_result.updated_at = now_iso()
        run.updated_at = now_iso()
        _save_run(run)
    return round_result


def submit_scores(run_id: str, round_number: int, entries: list[ScoreEntry]) -> RoundResult:
    """Step 3: 提交评分数据（gold 标准 + 多个评分者）。初筛否决的轮次不允许评分。"""
    with _lock:
        run = _require_run(run_id)
        round_result = _require_round(run, round_number)
        if _review_rejected(round_result):
            raise ValueError("该轮已被初筛否决，不能提交评分；请直接使用 RIFT 诊断")
        valid_raters = set(run.rater_ids)
        for e in entries:
            for rater_id in e.rater_scores:
                if rater_id not in valid_raters:
                    raise ValueError(f"未知评分者: {rater_id}（运行评分者为 {sorted(valid_raters)}）")
        round_result.score_sheet = ScoreSheet(entries=entries)
        if round_result.status in ("generated", "generate_error"):
            round_result.status = "scored"
        round_result.updated_at = now_iso()
        run.updated_at = now_iso()
        _save_run(run)
    return round_result


def compute_round_metrics(run_id: str, round_number: int) -> RoundMetrics:
    """Step 4a: 计算一致性指标（Pearson / QWK / Composite），不调 LLM。初筛否决的轮次已跳过指标。"""
    with _lock:
        run = _require_run(run_id)
        round_result = _require_round(run, round_number)
        if _review_rejected(round_result):
            raise ValueError("该轮已被初筛否决，已跳过指标计算")
        entries = round_result.score_sheet.entries
        if not entries:
            raise ValueError("该轮次还没有评分数据，请先提交评分")
        golds: list[float] = []
        means: list[float] = []
        deviations: dict[str, float] = {}
        for e in entries:
            golds.append(e.gold_score)
            rater_values = list(e.rater_scores.values())
            mean = sum(rater_values) / len(rater_values) if rater_values else e.gold_score
            means.append(mean)
            deviations[e.rubric_id] = round(mean - e.gold_score, 4)  # 评分者均值 - gold
        result = metrics_mod.compute_metrics(golds, means)
        round_result.metrics = RoundMetrics(
            pearson_r=result["pearson_r"],
            spearman_rho=result["spearman_rho"],
            qwk=result["qwk"],
            composite=result["composite"],
            per_query_deviation=deviations,
            n_entries=len(entries),
            error=result.get("error"),
        )
        if round_result.status in ("generated", "generate_error", "scored"):
            round_result.status = "metrics"
        round_result.updated_at = now_iso()
        run.updated_at = now_iso()
        _save_run(run)
    return round_result.metrics


def analyze_round(run_id: str, round_number: int) -> RoundResult:
    """Step 4b: RIFT 诊断（每条 rubric 各调一次 LLM）+ 聚合诊断（再调一次 LLM）。"""
    from . import diagnostics
    run = _require_run(run_id)
    round_result = _require_round(run, round_number)
    rubrics = storage.list_rubrics_for_query_ids_version(run.query_ids, round_result.prompt_version)
    if not rubrics:
        raise ValueError("该轮次没有可诊断的 rubric（生成可能失败）")

    findings: list[FailureFinding] = []
    errors: list[dict] = []
    for rubric in rubrics:
        try:
            findings.extend(diagnostics.diagnose_rubric(rubric))
        except Exception as exc:  # noqa: BLE001
            errors.append({"rubric_id": rubric["id"], "error": str(exc)})

    diagnosis = RoundDiagnosis(findings=findings, errors=errors)
    suggestions: list[OptimizationSuggestion] = []
    if findings:
        try:
            aggregated = diagnostics.aggregate_diagnosis(findings, rubrics)
            diagnosis.aggregated = aggregated.get("summary", "")
            for s in aggregated.get("suggestions", []):
                suggestions.append(OptimizationSuggestion(
                    id=new_id("suggestion"),
                    module=s.get("module", "structure"),
                    problem=s.get("problem", ""),
                    suggestion=s.get("suggestion", ""),
                    status="pending",
                ))
        except Exception as exc:  # noqa: BLE001
            errors.append({"error": f"聚合诊断失败: {exc}"})

    with _lock:
        run = _require_run(run_id)
        round_result = _require_round(run, round_number)
        round_result.diagnosis = diagnosis
        round_result.suggestions = suggestions
        if round_result.status in ("generated", "generate_error", "rejected", "scored", "metrics", "analyzed"):
            round_result.status = "analyzed"
        round_result.updated_at = now_iso()
        run.updated_at = now_iso()
        _save_run(run)
    return round_result


def apply_suggestions(run_id: str, round_number: int, accepted_ids: list[str], new_version: str) -> RoundResult:
    """Step 5: 人工审阅采纳建议 → LLM 精炼对应模块 → 保存为新版本 prompt。"""
    from . import prompt_modules, refiner
    with _lock:
        run = _require_run(run_id)
        round_result = _require_round(run, round_number)
        accepted = [s for s in round_result.suggestions if s.id in set(accepted_ids)]
        if not accepted:
            raise ValueError("未选中任何建议")
        if prompt_modules.load_version(new_version) is not None:
            raise ValueError(f"版本已存在: {new_version}")
    refined = refiner.refine_prompt(
        current_version=round_result.prompt_version,
        new_version=new_version,
        accepted_suggestions=[s.model_dump() for s in accepted],
    )
    with _lock:
        run = _require_run(run_id)
        round_result = _require_round(run, round_number)
        accepted_set = set(accepted_ids)
        for s in round_result.suggestions:
            if s.id in accepted_set:
                s.status = "accepted"
                s.accepted = True
        round_result.refined_prompt_version = new_version
        round_result.status = "refined"
        round_result.updated_at = now_iso()
        run.current_prompt_version = new_version
        run.updated_at = now_iso()
        _save_run(run)
    return round_result


def check_stopping(run_id: str) -> StoppingCheck:
    """Step 6: 中止判断（达标 / 收敛 / 预算 / 退化）。"""
    run = _require_run(run_id)
    thresholds = dict(DEFAULT_THRESHOLDS)
    scored_rounds = [r for r in run.rounds if r.metrics is not None and r.metrics.composite is not None]
    if not scored_rounds:
        return StoppingCheck(should_stop=False, reason="尚无指标，继续下一轮", thresholds=thresholds)

    latest = scored_rounds[-1]
    best_composite = max(r.metrics.composite for r in scored_rounds)
    metrics = latest.metrics

    # 达标
    if (metrics.pearson_r or 0) >= thresholds["pearson_r_target"] and (metrics.qwk or 0) >= thresholds["qwk_target"]:
        _set_run_status(run, "converged")
        return StoppingCheck(should_stop=True, reason="达标（pearson >= 0.85 且 qwk >= 0.75）",
                             metrics=metrics, thresholds=thresholds)
    # 预算
    if len(run.rounds) >= thresholds["max_rounds"]:
        _set_run_status(run, "stopped")
        return StoppingCheck(should_stop=True, reason=f"预算（已达 {thresholds['max_rounds']} 轮上限）",
                             metrics=metrics, thresholds=thresholds)
    # 退化
    if metrics.composite < best_composite + thresholds["degradation_threshold"]:
        _set_run_status(run, "stopped")
        return StoppingCheck(should_stop=True, reason="退化（最新轮 composite 低于历史最佳 0.05 以上）",
                             metrics=metrics, thresholds=thresholds)
    # 收敛
    if len(scored_rounds) >= 3:
        deltas = [scored_rounds[i].metrics.composite - scored_rounds[i - 1].metrics.composite
                  for i in range(1, len(scored_rounds))]
        if len(deltas) >= 2 and all(d < thresholds["min_delta"] for d in deltas[-2:]):
            _set_run_status(run, "converged")
            return StoppingCheck(should_stop=True, reason="收敛（连续 2 轮 composite 改善不足 0.02）",
                                 metrics=metrics, thresholds=thresholds)
    return StoppingCheck(should_stop=False, reason="继续优化",
                         metrics=metrics, thresholds=thresholds)


def _set_run_status(run: OptimizationRun, status: str) -> None:
    with _lock:
        run2 = _load_run(run.run_id)
        if run2 is None:
            return
        run2.status = status
        run2.updated_at = now_iso()
        _save_run(run2)

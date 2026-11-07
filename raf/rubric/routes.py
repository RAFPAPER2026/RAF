"""全部 API 路由定义（见 docs/rubr.md 第 6 节端点清单）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import optimizer, prompt_modules, storage
from . import query_store
from .models import QueryRubricCreate, RubricReviewCreate
from .models_optim import ScoreEntry
from .scoring import evaluate_completion, score_quality

router = APIRouter()


# ---------- 请求体模型 ----------

class ScoreRequest(BaseModel):
    scoring_mode: Optional[str] = None  # paper | legacy_mean
    results: dict[str, bool]


class ReviewRequest(BaseModel):
    rubric_id: str
    completion_score: int = Field(ge=1, le=5)
    quality_score: int = Field(ge=1, le=5)
    notes: list[str] = Field(default_factory=lambda: ["", "", ""])


class ModuleUpdateRequest(BaseModel):
    content: str


class CloneVersionRequest(BaseModel):
    new_version: str
    change_description: str = ""


class CapabilitiesRequest(BaseModel):
    capabilities: list[str]


class QueryCreateRequest(BaseModel):
    text: str
    tags: list[str] = Field(default_factory=list)


class QueryBatchRequest(BaseModel):
    texts: list[str]


class QueryUpdateRequest(BaseModel):
    text: str | None = None
    tags: list[str] | None = None


class QueryImportRequest(BaseModel):
    items: list[QueryCreateRequest]


class BatchGenerateRequest(BaseModel):
    prompt_version: str | None = None
    queries: list[str] = Field(default_factory=list)
    query_ids: list[str] = Field(default_factory=list)
    concurrency: int = 16


class OptimizeRunCreateRequest(BaseModel):
    name: str = ""
    query_ids: list[str]
    rater_ids: list[str]
    prompt_version: str


class RoundScoresRequest(BaseModel):
    entries: list[ScoreEntry]


class RoundQualityReviewRequest(BaseModel):
    """人工质量初筛结论（整批一次判断，decision 合法性在 optimizer 内校验）。"""

    decision: str  # "approved"（尚可，进入评分）/ "rejected"（不行，跳过评分直接诊断）
    comment: str = Field(default="", max_length=2000)


class ApplySuggestionsRequest(BaseModel):
    accepted_suggestion_ids: list[str]
    new_version: str


# ================= 6.1 Rubric CRUD =================

@router.get("/api/rubrics")
def api_list_rubrics(search: str = "", limit: int = 0, offset: int = 0, dedup: bool = False):
    """列表（search/limit/offset/dedup，附带审核统计与 query tags）。"""
    items = storage.list_rubrics(
        search=search or None,
        limit=limit or None,
        offset=offset or None,
        dedup=dedup,
    )
    for item in items:
        reviews = storage.list_reviews_for_rubric(item["id"])
        item["review_count"] = len(reviews)
        item["review_avg_completion"] = (
            round(sum(r["completion_score"] for r in reviews) / len(reviews), 2) if reviews else None
        )
        item["review_avg_quality"] = (
            round(sum(r["quality_score"] for r in reviews) / len(reviews), 2) if reviews else None
        )
        q = query_store.get_query(item["query_id"]) if item.get("query_id") else None
        item["query_tags"] = q.tags if q else []
    return items


@router.post("/api/rubrics")
def api_create_rubric(data: QueryRubricCreate):
    """创建（Pydantic 校验节点结构：group 带 tags 直接 422）。"""
    query_id = data.query_id
    if not query_id:
        item = query_store.find_query_by_text(data.query)
        if item:
            query_id = item.id
    return storage.create_rubric(data, query_id=query_id)


@router.post("/api/rubrics/cleanup")
def api_cleanup_rubrics():
    """按 (query, prompt_version) 去重，保留最新。"""
    removed = storage.cleanup_rubrics()
    return {"removed": removed}


@router.get("/api/rubrics/{rubric_id}")
def api_get_rubric(rubric_id: str):
    rubric = storage.get_rubric(rubric_id)
    if rubric is None:
        raise HTTPException(status_code=404, detail=f"rubric 不存在: {rubric_id}")
    return rubric


@router.put("/api/rubrics/{rubric_id}")
def api_update_rubric(rubric_id: str, data: QueryRubricCreate):
    updated = storage.update_rubric(rubric_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"rubric 不存在: {rubric_id}")
    return updated


@router.delete("/api/rubrics/{rubric_id}")
def api_delete_rubric(rubric_id: str):
    deleted = storage.delete_rubric(rubric_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"rubric 不存在: {rubric_id}")
    return {"deleted": True}


@router.post("/api/rubrics/{rubric_id}/score")
def api_score_rubric(rubric_id: str, body: ScoreRequest):
    """提交勾选结果（{results: {leaf_id: bool}}），返回 completion + quality 分数。"""
    rubric = storage.get_rubric(rubric_id)
    if rubric is None:
        raise HTTPException(status_code=404, detail=f"rubric 不存在: {rubric_id}")
    from .models import QueryRubric
    model = QueryRubric(**rubric)
    return {
        "completion": evaluate_completion(model.completion_rubric, body.results),
        "quality": score_quality(model.quality_rubric, body.results, body.scoring_mode),
    }


# ================= 6.2 审核 =================

@router.get("/api/reviews")
def api_list_reviews():
    return storage.list_reviews()


@router.get("/api/reviews/stats")
def api_review_stats():
    """按 prompt_version 聚合统计（平均分、分数分布）。"""
    return storage.review_stats()


@router.get("/api/reviews/{rubric_id}")
def api_get_review(rubric_id: str):
    review = storage.get_review_for_rubric(rubric_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"该 rubric 暂无审核: {rubric_id}")
    return review


@router.post("/api/reviews")
def api_create_review(body: ReviewRequest):
    rubric = storage.get_rubric(body.rubric_id)
    if rubric is None:
        raise HTTPException(status_code=404, detail=f"rubric 不存在: {body.rubric_id}")
    return storage.create_review(
        RubricReviewCreate(
            rubric_id=body.rubric_id,
            completion_score=body.completion_score,
            quality_score=body.quality_score,
            notes=body.notes[:3],
        ),
        prompt_version=rubric.get("prompt_version", ""),
    )


# ================= 6.3 Prompt 版本管理 =================

@router.get("/api/prompt-versions")
def api_list_prompt_versions():
    """列出版本（摘要，不含模块全文）+ 活跃版本。"""
    active = prompt_modules.get_active_version()
    versions = []
    for record in prompt_modules.list_versions():
        versions.append({
            "version": record.get("version"),
            "parent_version": record.get("parent_version", ""),
            "created_at": record.get("created_at", ""),
            "change_description": record.get("change_description", ""),
            "metrics_summary": record.get("metrics_summary", {}),
            "module_sizes": {k: len(record.get("modules", {}).get(k, "")) for k in prompt_modules.MODULE_ORDER},
            "active": record.get("version") == active,
        })
    return {"versions": versions, "active": active}


@router.get("/api/prompt-versions/{version}")
def api_get_prompt_version(version: str):
    record = prompt_modules.load_version(version)
    if record is None:
        raise HTTPException(status_code=404, detail=f"版本不存在: {version}")
    record["assembled_prompt"] = prompt_modules.build_system_prompt(version)
    record["module_order"] = prompt_modules.MODULE_ORDER
    return record


@router.get("/api/prompt-versions/{version}/diff")
def api_diff_prompt_versions(version: str, compare_to: str = ""):
    """模块级 diff；{version} 与 compare_to 中较新者作为 new 侧。"""
    if not compare_to:
        raise HTTPException(status_code=400, detail="缺少 compare_to 参数")
    # 较新者作为 new 侧
    old, new = sorted([version, compare_to], key=prompt_modules._version_sort_key)
    return prompt_modules.diff_versions(new, old)


@router.put("/api/prompt-versions/{version}/modules/{module_key}")
def api_update_prompt_module(version: str, module_key: str, body: ModuleUpdateRequest):
    """手动修改模块（body: {content}）。"""
    record = prompt_modules.load_version(version)
    if record is None:
        raise HTTPException(status_code=404, detail=f"版本不存在: {version}")
    if module_key not in prompt_modules.MODULE_ORDER:
        raise HTTPException(status_code=400, detail=f"未知模块: {module_key}（可选 {prompt_modules.MODULE_ORDER}）")
    record["modules"][module_key] = body.content
    prompt_modules.save_version(record)
    return {"version": version, "module": module_key, "updated": True}


@router.post("/api/prompt-versions/{version}/clone")
def api_clone_prompt_version(version: str, body: CloneVersionRequest):
    """克隆版本（body: {new_version, change_description}）。"""
    record = prompt_modules.load_version(version)
    if record is None:
        raise HTTPException(status_code=404, detail=f"版本不存在: {version}")
    if prompt_modules.load_version(body.new_version) is not None:
        raise HTTPException(status_code=409, detail=f"版本已存在: {body.new_version}")
    from .models import now_iso
    clone = {
        "version": body.new_version,
        "parent_version": version,
        "created_at": now_iso(),
        "change_description": body.change_description or f"克隆自 {version}",
        "metrics_summary": {},
        "modules": dict(record.get("modules", {})),
    }
    prompt_modules.save_version(clone)
    return clone


@router.put("/api/prompt-versions/{version}/activate")
def api_activate_prompt_version(version: str):
    record = prompt_modules.load_version(version)
    if record is None:
        raise HTTPException(status_code=404, detail=f"版本不存在: {version}")
    prompt_modules.set_active_version(version)
    return {"active": version}


# ================= 6.4 能力项 =================

@router.get("/api/capabilities")
def api_get_capabilities():
    """读取 capabilities.txt。"""
    return {"capabilities": prompt_modules.load_capabilities()}


@router.put("/api/capabilities")
def api_update_capabilities(body: CapabilitiesRequest):
    """更新（同步内存缓存）。"""
    saved = prompt_modules.save_capabilities(body.capabilities)
    return {"capabilities": saved}


# ================= 6.5 Query 管理 =================

@router.get("/api/queries")
def api_list_queries():
    items = []
    for q in query_store.list_queries():
        item = q.model_dump()
        item["rubric_count"] = query_store.rubric_reference_count(q.id)
        items.append(item)
    return items


@router.post("/api/queries")
def api_create_query(body: QueryCreateRequest):
    return query_store.create_query(body.text, body.tags)


@router.post("/api/queries/batch")
def api_batch_create_queries(body: QueryBatchRequest):
    """批量创建（text 去重）。"""
    items, created = query_store.batch_create_query(body.texts)
    return {"created": created, "total": len(items), "items": [q.model_dump() for q in items]}


@router.get("/api/queries/export")
def api_export_queries():
    """导出 Excel（列：id/text/tags）。"""
    content = query_store.export_excel()
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="queries.xlsx"'},
    )


@router.get("/api/queries/{query_id}")
def api_get_query(query_id: str):
    q = query_store.get_query(query_id)
    if q is None:
        raise HTTPException(status_code=404, detail=f"query 不存在: {query_id}")
    item = q.model_dump()
    item["rubric_count"] = query_store.rubric_reference_count(query_id)
    return item


@router.put("/api/queries/{query_id}")
def api_update_query(query_id: str, body: QueryUpdateRequest):
    q = query_store.update_query(query_id, text=body.text, tags=body.tags)
    if q is None:
        raise HTTPException(status_code=404, detail=f"query 不存在: {query_id}")
    return q


@router.delete("/api/queries/{query_id}")
def api_delete_query(query_id: str):
    """删除时检查 rubric 引用。"""
    if query_store.get_query(query_id) is None:
        raise HTTPException(status_code=404, detail=f"query 不存在: {query_id}")
    refs = query_store.rubric_reference_count(query_id)
    if refs > 0:
        raise HTTPException(status_code=409, detail=f"该 query 被 {refs} 条 rubric 引用，无法删除")
    query_store.delete_query(query_id)
    return {"deleted": True}


@router.post("/api/queries/import")
def api_import_queries(body: QueryImportRequest):
    """JSON 批量导入。"""
    created_total = 0
    for item in body.items:
        existing = query_store.find_query_by_text(item.text)
        if existing:
            continue
        query_store.create_query(item.text, item.tags)
        created_total += 1
    return {"created": created_total, "total": len(query_store.list_queries())}


@router.post("/api/queries/import-excel")
async def api_import_queries_excel(file: UploadFile = File(...)):
    content = await file.read()
    try:
        items, created = query_store.import_excel(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Excel 解析失败: {exc}")
    return {"created": created, "total": len(items)}


@router.post("/api/queries/migrate")
def api_migrate_queries():
    """从 rubrics.json 迁移：提取唯一 query 建 QueryItem 并回填 query_id。"""
    return query_store.migrate_from_rubrics()


# ================= 6.6 批量生成 =================

@router.post("/api/generate/batch")
def api_generate_batch(body: BatchGenerateRequest):
    """后台线程批量生成，返回 task_id。"""
    version = body.prompt_version or prompt_modules.get_active_version()
    if prompt_modules.load_version(version) is None:
        raise HTTPException(status_code=400, detail=f"prompt 版本不存在: {version}")
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for qid in body.query_ids:
        q = query_store.get_query(qid)
        if q is None:
            raise HTTPException(status_code=400, detail=f"query 不存在: {qid}")
        if q.text not in seen:
            pairs.append((q.text, q.id))
            seen.add(q.text)
    for text in body.queries:
        text = text.strip()
        if not text or text in seen:
            continue
        item = query_store.find_query_by_text(text)
        pairs.append((text, item.id if item else ""))
        seen.add(text)
    if not pairs:
        raise HTTPException(status_code=400, detail="请提供 queries 或 query_ids")
    task_id = optimizer.run_batch_generation(pairs, version, concurrency=body.concurrency)
    return {"task_id": task_id, "total": len(pairs), "prompt_version": version}


@router.get("/api/generate/status/{task_id}")
def api_generate_status(task_id: str):
    """轮询进度（running/generating/done/error；每 query pending/generating/done/error）。"""
    task = optimizer.get_batch_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return task


# ================= 6.7 优化运行（PROMPT-R） =================

def _opt_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/api/optimize/runs")
def api_create_optimize_run(body: OptimizeRunCreateRequest):
    try:
        run = optimizer.create_run(body.name, body.query_ids, body.rater_ids, body.prompt_version)
    except ValueError as exc:
        raise _opt_error(exc)
    return run


@router.get("/api/optimize/runs")
def api_list_optimize_runs():
    return [r.model_dump() for r in optimizer.list_runs()]


@router.get("/api/optimize/runs/{run_id}")
def api_get_optimize_run(run_id: str):
    detail = optimizer.get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
    return detail


@router.delete("/api/optimize/runs/{run_id}")
def api_delete_optimize_run(run_id: str):
    if not optimizer.delete_run(run_id):
        raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
    return {"deleted": True}


@router.post("/api/optimize/runs/{run_id}/rounds")
def api_start_round(run_id: str):
    """开始新轮次（创建轮次 + 触发后台批量生成）。"""
    try:
        return optimizer.start_round(run_id)
    except ValueError as exc:
        raise _opt_error(exc)


@router.post("/api/optimize/runs/{run_id}/rounds/{round_number}/scores")
def api_submit_round_scores(run_id: str, round_number: int, body: RoundScoresRequest):
    try:
        return optimizer.submit_scores(run_id, round_number, body.entries)
    except ValueError as exc:
        raise _opt_error(exc)


@router.get("/api/optimize/runs/{run_id}/rounds/{round_number}/scores")
def api_get_round_scores(run_id: str, round_number: int):
    run = optimizer.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
    try:
        round_result = optimizer._require_round(run, round_number)
    except ValueError as exc:
        raise _opt_error(exc)
    return round_result.score_sheet


@router.post("/api/optimize/runs/{run_id}/rounds/{round_number}/quality-review")
def api_review_round_quality(run_id: str, round_number: int, body: RoundQualityReviewRequest):
    """人工质量初筛（body: decision "approved"/"rejected" + comment）。"""
    try:
        return optimizer.review_round_quality(run_id, round_number, body.decision, body.comment)
    except ValueError as exc:
        raise _opt_error(exc)


@router.post("/api/optimize/runs/{run_id}/rounds/{round_number}/metrics")
def api_compute_round_metrics(run_id: str, round_number: int):
    """计算指标（不调 LLM）。"""
    try:
        return optimizer.compute_round_metrics(run_id, round_number)
    except ValueError as exc:
        raise _opt_error(exc)


@router.post("/api/optimize/runs/{run_id}/rounds/{round_number}/analyze")
def api_analyze_round(run_id: str, round_number: int):
    """RIFT 诊断 + 建议（调 LLM：每条 rubric 一次 + 聚合一次）。"""
    try:
        return optimizer.analyze_round(run_id, round_number)
    except ValueError as exc:
        raise _opt_error(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM 诊断失败: {exc}")


@router.post("/api/optimize/runs/{run_id}/rounds/{round_number}/re-diagnose")
def api_re_diagnose_round(run_id: str, round_number: int):
    """重新诊断（不重算指标）。"""
    try:
        return optimizer.analyze_round(run_id, round_number)
    except ValueError as exc:
        raise _opt_error(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM 诊断失败: {exc}")


@router.post("/api/optimize/runs/{run_id}/rounds/{round_number}/apply")
def api_apply_suggestions(run_id: str, round_number: int, body: ApplySuggestionsRequest):
    """采纳建议 + 精炼（body: accepted_suggestion_ids/new_version）。"""
    try:
        return optimizer.apply_suggestions(
            run_id, round_number, body.accepted_suggestion_ids, body.new_version
        )
    except ValueError as exc:
        raise _opt_error(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"精炼失败: {exc}")


@router.get("/api/optimize/runs/{run_id}/check-stop")
def api_check_stop(run_id: str):
    try:
        return optimizer.check_stopping(run_id)
    except ValueError as exc:
        raise _opt_error(exc)

"""人工打分页 REST 路由（除注明外均在 `/api` 下）。

全局单例由 `server.py:create_app` 注入：`data_loader`（ManualScorerDataLoader）、
`_agent_manager`、`_batch_manager`、`_agent_config_path`。

本服务默认仅在本机使用，不内置鉴权；请勿直接暴露到公网。
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from manual_scorer.data_loader import ManualScorerDataLoader
from src.agent_scorer.batch_models import BatchEvalSession
from src.agent_scorer.exceptions import AgentConcurrentError
from src.agent_scorer.models import AgentReview
from src.agent_scorer.task_manager import AgentTaskManager
from src.rubric.compat import detect_rubric_format
from src.rubric.models import QueryRubric
from src.rubric.scoring import compute_rubric_score
from src.runs import AVERAGE_RUN_ID, load_trace_config, next_run_id

router = APIRouter()

# 上传限制：staging 会话 30 分钟 TTL；单次上传 1GB；单文件 50MB
_UPLOAD_TTL_SECONDS = 30 * 60
_MAX_UPLOAD_BYTES = 1 << 30
_MAX_FILE_BYTES = 50 << 20

# ---------------------------------------------------------------- 请求模型

class CreateModelRequest(BaseModel):
    model_name: str
    prefix: Optional[str] = None


class ManualScoreRequest(BaseModel):
    rubric_results: Optional[dict[str, bool]] = None  # tree 模式
    rubric_scores: Optional[list[dict]] = None  # flat 模式
    score: Optional[float] = None  # 直接模式
    dimensions: Optional[dict[str, float]] = None
    comment: Optional[str] = None
    scored_by: Optional[str] = None
    scoring_mode: Optional[str] = None  # paper | legacy_mean
    run_id: str = "run_1"


class CompleteFlagRequest(BaseModel):
    complete_flag: Optional[int] = None  # 0|1|null
    run_id: str = "run_1"


class ManualFeedbackRequest(BaseModel):
    manual_feedback: int = 0  # 1|-1|0
    run_id: str = "run_1"


class DoubtfulRequest(BaseModel):
    doubtful: bool = False
    run_id: str = "run_1"


class TraceQualityRequest(BaseModel):
    dimensions: dict[str, float]
    run_id: str = "run_1"


class UploadConfirmRequest(BaseModel):
    session_id: str
    results_overwrite: bool = True
    run_id: Optional[str] = None


class UploadCancelRequest(BaseModel):
    session_id: str


class AgentEvalRequest(BaseModel):
    evaluate_trace: bool = False
    run_id: str = "run_1"


class AgentEvalAdoptRequest(BaseModel):
    run_id: str = "run_1"


class BatchEvalRequest(BaseModel):
    task_names: list[str]
    evaluate_trace: bool = False
    skip_existing: bool = True
    auto_adopt: bool = False
    concurrency: int = Field(default=32, ge=1, le=128)
    run_id: str = "run_1"


# ---------------------------------------------------------------- 全局单例注入

_loader: Optional[ManualScorerDataLoader] = None
_agent_manager: Optional[AgentTaskManager] = None
_batch_manager: Optional[Any] = None
_agent_config_path: Optional[str] = None

_upload_staging: dict[str, dict] = {}
_model_locks: dict[str, asyncio.Lock] = {}


def init_globals(
    loader: ManualScorerDataLoader,
    agent_manager: AgentTaskManager,
    batch_manager: Any,
    agent_config_path: Optional[str] = None,
) -> None:
    """server.py:create_app 注入全局单例。"""
    global _loader, _agent_manager, _batch_manager, _agent_config_path
    _loader = loader
    _agent_manager = agent_manager
    _batch_manager = batch_manager
    _agent_config_path = agent_config_path


def _get_loader() -> ManualScorerDataLoader:
    if _loader is None:
        raise HTTPException(status_code=500, detail="数据加载器未初始化")
    return _loader


def _get_agent_manager() -> AgentTaskManager:
    if _agent_manager is None:
        raise HTTPException(status_code=500, detail="Agent 评测管理器未初始化")
    return _agent_manager


def _get_batch_manager() -> Any:
    if _batch_manager is None:
        raise HTTPException(status_code=500, detail="批量评测管理器未初始化")
    return _batch_manager


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------- 基础/鉴权

@router.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/stats")
def stats() -> dict:
    return _get_loader().get_global_stats()


@router.get("/api/trace-config")
def trace_config() -> dict:
    return load_trace_config()


# ---------------------------------------------------------------- 模型管理

@router.get("/api/models")
def list_models() -> list[dict]:
    """`ModelSummary[]`（仅统计 manual 任务；含 run 平均分数与 per-run 统计）。"""
    return _get_loader().get_models()


@router.post("/api/models")
def create_model(body: CreateModelRequest) -> dict:
    try:
        model_id = _get_loader().create_model(body.model_name, body.prefix)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"success": True, "message": f"已创建模型 {model_id}", "model_id": model_id}


@router.delete("/api/model/{model_id}")
def delete_model(model_id: str, confirm_name: str) -> dict:
    """`{confirm_name}` 必须等于 model_id 才删。"""
    try:
        _get_loader().delete_model(model_id, confirm_name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"success": True, "message": f"已删除模型 {model_id}"}


@router.delete("/api/model/{model_id}/task/{task_name}")
def delete_task(model_id: str, task_name: str) -> dict:
    """删 case 目录 + 重建 result.json。"""
    try:
        _get_loader().delete_task(model_id, task_name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    return {"success": True, "message": f"已删除任务 {task_name}"}


# ---------------------------------------------------------------- runs / 任务列表

@router.get("/api/model/{model_id}/runs")
def model_runs(model_id: str) -> dict:
    try:
        return _get_loader().get_runs(model_id)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/api/model/{model_id}/tasks")
def model_tasks(model_id: str, run_id: str = AVERAGE_RUN_ID) -> list[dict]:
    """`?run_id=average|run_1..n`；`TaskSummary[]`，只含 `verifier_type=="manual"` 任务。"""
    try:
        return _get_loader().get_task_summaries(model_id, run_id)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/api/model/{model_id}/task/{task_name}")
def task_detail(model_id: str, task_name: str, run_id: str = "run_1") -> dict:
    """`?run_id=run_1..n`（具体 run；average 拒绝）；
    `{task_name, score(兼容处理+tree 重算), config(+rubric_format), sessions[]}`。
    """
    try:
        return _get_loader().get_task_detail(model_id, task_name, run_id)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/api/model/{model_id}/task/{task_name}/sessions")
def task_sessions(model_id: str, task_name: str, run_id: str = "run_1") -> dict:
    """原始 sessions.json。"""
    try:
        return _get_loader().get_sessions(model_id, task_name, run_id)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc


# ---------------------------------------------------------------- 评分写入

@router.post("/api/model/{model_id}/task/{task_name}/score")
def save_score(model_id: str, task_name: str, body: ManualScoreRequest) -> dict:
    """三种模式（均针对具体 run_id）：
    (a) tree `{rubric_results}` → 按 config 树校验，compute_rubric_score 派生，score=quality_score
    (b) flat `{rubric_scores}` → score=mean(item_score)
    (c) 直接 `{score}` 或 `{dimensions}`
    写 score.json + 重建 result.json，返回 `{success, message, score}`。
    """
    loader = _get_loader()
    try:
        if body.rubric_results is not None:
            return loader.save_tree_score(
                model_id, task_name, body.run_id, body.rubric_results,
                body.comment, body.scored_by, body.scoring_mode,
            )
        if body.rubric_scores is not None:
            return loader.save_flat_score(
                model_id, task_name, body.run_id, body.rubric_scores,
                body.comment, body.scored_by,
            )
        if body.score is not None or body.dimensions is not None:
            return loader.save_direct_score(
                model_id, task_name, body.run_id, body.score, body.dimensions,
                body.comment, body.scored_by,
            )
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except (ValueError, TypeError) as exc:
        raise _bad_request(exc) from exc
    raise _bad_request(ValueError("评分请求体为空（需 rubric_results/rubric_scores/score/dimensions 之一）"))


@router.patch("/api/model/{model_id}/task/{task_name}/complete-flag")
def patch_complete_flag(model_id: str, task_name: str, body: CompleteFlagRequest) -> dict:
    """只写 complete_flag；不碰 result.json；null 存显式 null。"""
    if body.complete_flag not in (0, 1, None):
        raise _bad_request(ValueError("complete_flag 必须为 0/1/null"))
    try:
        _get_loader().save_complete_flag(model_id, task_name, body.run_id, body.complete_flag)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    return {"success": True, "message": "已更新完成标记"}


@router.patch("/api/model/{model_id}/task/{task_name}/manual-feedback")
def patch_manual_feedback(model_id: str, task_name: str, body: ManualFeedbackRequest) -> dict:
    """只写该标记（1=好/-1=差/0=未标）。"""
    if body.manual_feedback not in (1, -1, 0):
        raise _bad_request(ValueError("manual_feedback 必须为 1/-1/0"))
    try:
        _get_loader().save_manual_feedback(
            model_id, task_name, body.run_id, body.manual_feedback
        )
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    return {"success": True, "message": "已更新反馈标记"}


@router.patch("/api/model/{model_id}/task/{task_name}/doubtful")
def patch_doubtful(model_id: str, task_name: str, body: DoubtfulRequest) -> dict:
    """只写存疑标记。"""
    try:
        _get_loader().save_doubtful(model_id, task_name, body.run_id, body.doubtful)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    return {"success": True, "message": "已更新存疑标记"}


@router.post("/api/model/{model_id}/task/{task_name}/trace-quality")
def save_trace_quality(model_id: str, task_name: str, body: TraceQualityRequest) -> dict:
    """写 `trace_quality: {avg_score, dimensions}`（独立于总分，仅分析用）。"""
    try:
        _get_loader().save_trace_quality(
            model_id, task_name, body.run_id, {"dimensions": body.dimensions}
        )
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"success": True, "message": "已保存过程评价"}


# ---------------------------------------------------------------- 工作区

_MEDIA_TYPES = {
    ".jsonl": "application/jsonl",
    ".json": "application/json",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".sh": "text/plain",
    ".py": "text/plain",
    ".js": "text/plain",
    ".ts": "text/plain",
    ".tsx": "text/plain",
    ".css": "text/css",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip",
}


def _guess_media_type(name: str) -> str:
    return _MEDIA_TYPES.get(Path(name).suffix.lower(), "application/octet-stream")


def _cleanup_dir(path: str) -> None:
    try:
        shutil.rmtree(Path(path), ignore_errors=True)
    except OSError:
        pass


@router.get("/api/model/{model_id}/task/{task_name}/workspace")
def download_workspace(
    model_id: str, task_name: str, root: str = "workspace", run_id: str = "run_1"
) -> FileResponse:
    """流式下载任务子目录 ZIP（临时文件，响应后删除）。root=workspace(默认)|judge。"""
    try:
        zip_path, tmp_dir = _get_loader().build_workspace_zip(
            model_id, task_name, run_id, root
        )
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{task_name}_{run_id}_{root}.zip",
        background=BackgroundTask(_cleanup_dir, str(tmp_dir)),
    )


@router.get("/api/model/{model_id}/task/{task_name}/workspace/files")
def workspace_files(
    model_id: str, task_name: str, root: str = "workspace", run_id: str = "run_1"
) -> dict:
    """递归文件树 `{files[], total_size, total_files}`。"""
    try:
        return _get_loader().list_workspace_files(model_id, task_name, run_id, root)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/api/model/{model_id}/task/{task_name}/workspace/file")
def workspace_file(
    model_id: str,
    task_name: str,
    path: str,
    root: str = "workspace",
    run_id: str = "run_1",
    token: str = "",
) -> FileResponse:
    """单文件（防路径穿越、50MB 上限→413、自定义 Content-Type 含 `application/jsonl`）；
    接受 `?token=` 供 `<img>`/`<iframe>`（当前鉴权被绕过，token 仅作兼容参数）。
    """
    try:
        target = _get_loader().resolve_workspace_file(model_id, task_name, run_id, path, root)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise _not_found(exc) from exc
    if size > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 50MB 上限")
    return FileResponse(target, media_type=_guess_media_type(target.name), filename=target.name)


# ---------------------------------------------------------------- 上传

def _extract_archive(file_data: bytes, dest: Path) -> None:
    """magic-byte 解压（防路径穿越，1GB 上限）：PK\x03\x04 → zip；Rar!\x1a\x07 → rar。"""
    if file_data[:4] == b"PK\x03\x04":
        import zipfile

        with zipfile.ZipFile(io.BytesIO(file_data)) as zf:
            total = sum(info.file_size for info in zf.infolist())
            if total > _MAX_UPLOAD_BYTES:
                raise ValueError("压缩包解压后超过 1GB 上限")
            for info in zf.infolist():
                target = (dest / info.filename).resolve()
                if not target.is_relative_to(dest.resolve()):
                    raise ValueError(f"路径穿越：{info.filename}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
        return
    if file_data[:8] == b"Rar!\x1a\x07":
        try:
            import rarfile
        except ImportError as exc:
            raise ValueError("需要 rarfile 库解析 .rar（并安装 unrar 工具）") from exc
        try:
            rf = rarfile.RarFile(io.BytesIO(file_data))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"rar 解析失败：{exc}") from exc
        total = sum(info.file_size for info in rf.infolist())
        if total > _MAX_UPLOAD_BYTES:
            raise ValueError("压缩包解压后超过 1GB 上限")
        for info in rf.infolist():
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise ValueError(f"路径穿越：{info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with rf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
        return
    raise ValueError("不支持的文件格式（仅 .zip/.rar）")


def _case_has_run(loader: ManualScorerDataLoader, model_id: str, case_name: str, run_id: str) -> bool:
    from src.runs import resolve_run_dir

    case_dir = loader.result_dir / model_id / case_name
    if not case_dir.is_dir():
        return False
    try:
        resolve_run_dir(case_dir, run_id)
        return True
    except (ValueError, FileNotFoundError):
        return False


@router.post("/api/model/{model_id}/upload/check")
async def upload_check(
    model_id: str,
    file: UploadFile = File(...),
    run_id: str = Form("new"),
) -> dict:
    """multipart：`file`(.zip/.rar)、`run_id`(run_1..n 或 `"new"`)。

    magic-byte 解压（防路径穿越，1GB 上限），逐用例扫描冲突，`"new"` 分配
    `run_{max_run+1}`，staging 会话 30 分钟 TTL。

    `UploadCheckResponse`：`{session_id, results_to_import[], results_conflicts[],
    has_conflicts, run_id}`。
    """
    loader = _get_loader()
    try:
        model_dir = loader._resolve_model_dir(model_id)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="上传文件超过 1GB 上限")

    staging_dir = Path(tempfile.mkdtemp(prefix="openclaw_upload_"))
    try:
        try:
            _extract_archive(data, staging_dir / "raw")
        except ValueError as exc:
            raise _bad_request(exc) from exc

        # run_id 解析："new" → run_{max_run+1}
        resolved_run_id = run_id
        if run_id == "new":
            resolved_run_id = next_run_id(model_dir)
        elif not re.fullmatch(r"run_\d+", run_id):
            raise _bad_request(ValueError(f"非法 run_id：{run_id}"))

        results_src = staging_dir / "raw"
        results_to_import: list[str] = []
        results_conflicts: list[str] = []
        for case_dir in sorted(p for p in results_src.iterdir() if p.is_dir()):
            results_to_import.append(case_dir.name)
            if _case_has_run(loader, model_id, case_dir.name, resolved_run_id):
                results_conflicts.append(case_dir.name)

        session_id = uuid.uuid4().hex
        _upload_staging[session_id] = {
            "dir": staging_dir,
            "created": time.monotonic(),
            "run_id": resolved_run_id,
            "results_src": str(results_src),
        }
        return {
            "success": True,
            "message": "检查完成",
            "session_id": session_id,
            "run_id": resolved_run_id,
            "results_to_import": results_to_import,
            "results_conflicts": results_conflicts,
            "has_conflicts": bool(results_conflicts),
        }
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _get_staging(session_id: str) -> dict:
    item = _upload_staging.get(session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="上传会话不存在")
    if time.monotonic() - item["created"] > _UPLOAD_TTL_SECONDS:
        _upload_staging.pop(session_id, None)
        shutil.rmtree(item["dir"], ignore_errors=True)
        raise HTTPException(status_code=410, detail="上传会话已过期（30 分钟 TTL）")
    return item


@router.post("/api/model/{model_id}/upload/confirm")
async def upload_confirm(model_id: str, body: UploadConfirmRequest) -> dict:
    """`{session_id, results_overwrite=true, run_id?}`；按模型 asyncio 锁；拷贝结果 case 进
    `{model}/<case>/{run}`（legacy run_1 原样写入；其他 run 先迁移 legacy→run_1/）；
    拷 result.json；`_reconcile_result_json`。
    """
    loader = _get_loader()
    staging = _get_staging(body.session_id)
    run_id = body.run_id or staging["run_id"]
    lock = _model_locks.setdefault(model_id, asyncio.Lock())
    imported = 0
    skipped = 0
    async with lock:
        results_src = Path(staging["results_src"])
        for case_dir in sorted(p for p in results_src.iterdir() if p.is_dir()):
            status = loader.import_result_case(
                model_id, case_dir.name, case_dir, run_id, body.results_overwrite
            )
            if status == "imported":
                imported += 1
            else:
                skipped += 1
        # 拷 result.json（随后 rebuild 权威重建）
        top_result = results_src / "result.json"
        if top_result.is_file():
            try:
                shutil.copy2(top_result, loader.result_dir / model_id / "result.json")
            except OSError:
                pass
        loader._reconcile_result_json(model_id)
    _upload_staging.pop(body.session_id, None)
    shutil.rmtree(staging["dir"], ignore_errors=True)
    return {
        "success": True,
        "message": f"导入完成：{imported} 个用例导入，{skipped} 个跳过（run {run_id}）",
        "run_id": run_id,
    }


@router.delete("/api/model/{model_id}/upload/cancel")
def upload_cancel(model_id: str, body: UploadCancelRequest) -> dict:
    """删 staging 目录。"""
    item = _upload_staging.pop(body.session_id, None)
    if item is not None:
        shutil.rmtree(item["dir"], ignore_errors=True)
    return {"success": True, "message": "已取消上传"}


# ---------------------------------------------------------------- Agent 评测（单任务）

@router.post("/api/model/{model_id}/task/{task_name}/agent-eval")
def start_agent_eval(model_id: str, task_name: str, body: AgentEvalRequest) -> dict:
    """body `{evaluate_trace: bool=False, run_id="run_1"}`；非 manual/非 tree → 400；
    `AgentConcurrentError` → 409；返回 `{task_key, status, run_id}`。
    """
    loader = _get_loader()
    config = loader.get_task_config(task_name)
    if config is None:
        raise _not_found(FileNotFoundError(f"任务配置缺失：{task_name}"))
    if config.verifier_type != "manual":
        raise _bad_request(ValueError("仅 manual 任务支持 Agent 评测"))
    if detect_rubric_format(config.rubric) != "tree":
        raise _bad_request(ValueError("Agent 评分仅支持 tree 格式 rubric（flat 不支持）"))
    try:
        run_dir = loader._resolve_writable_run_dir(model_id, task_name, body.run_id)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    if loader.tasks_dir is None:
        raise _bad_request(ValueError("tasks_dir 未配置"))
    task_dir = loader.tasks_dir / task_name
    manager = _get_agent_manager()
    try:
        task = manager.start_eval(
            model_id=model_id,
            task_name=task_name,
            run_id=body.run_id,
            config=config,
            task_dir=task_dir,
            result_dir=run_dir,
            evaluate_trace=body.evaluate_trace,
        )
    except AgentConcurrentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"task_key": task.task_key, "status": task.status.value, "run_id": task.run_id}


@router.get("/api/model/{model_id}/task/{task_name}/agent-eval")
def get_agent_eval(model_id: str, task_name: str, run_id: str = "run_1") -> dict:
    """未知 → `{"status":"none"}`，否则 task `to_dict()`。"""
    manager = _get_agent_manager()
    task = manager.get_task(AgentTaskManager.task_key(model_id, task_name, run_id))
    if task is None:
        return {"status": "none"}
    return task.to_dict()


@router.post("/api/model/{model_id}/task/{task_name}/agent-eval/adopt")
def adopt_agent_eval(model_id: str, task_name: str, body: AgentEvalAdoptRequest) -> dict:
    """采纳：读 run 的 score.json，要求 `agent_review`（否则 400）。

    - **tree 路径**（默认）：config rubric → `QueryRubric.model_validate` →
      `{leaf:{passed,reasoning}}` → `{leaf:bool}`（非 dict 用 `bool(v)` 防御）→
      `compute_rubric_score` 派生 → `score = round(quality_score, 4)` → 逐叶子拼 comment
      `"[{id}] ✓/✗ {reasoning}"` → `save_manual_score(..., scored_by="agent",
      adopted_agent_timestamp=agent_review.timestamp, run_id)`
    - **flat 路径**（向后兼容）：重算 `item_score`/`score`/`completion_rate`；
      comment 用 `agent_review.get("reasoning","")`
    - agent_review 含 `trace_quality` 时一并 `save_trace_quality`
    """
    loader = _get_loader()
    try:
        run_dir = loader._resolve_writable_run_dir(model_id, task_name, body.run_id)
        score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except (OSError, ValueError) as exc:
        raise _bad_request(exc) from exc
    review_data = score.get("agent_review") if isinstance(score, dict) else None
    if not isinstance(review_data, dict):
        raise _bad_request(ValueError("该任务尚无 agent_review，无法采纳"))
    review = AgentReview.from_dict(review_data)
    config = loader.get_task_config(task_name)
    if config is None:
        raise _not_found(FileNotFoundError(f"任务配置缺失：{task_name}"))

    result: dict[str, Any]
    if detect_rubric_format(config.rubric) == "tree":
        rubric = QueryRubric.model_validate(config.rubric)
        leaf_bools = {
            leaf: (bool(v.get("passed")) if isinstance(v, dict) else bool(v))
            for leaf, v in review.rubric_results.items()
        }
        derived = compute_rubric_score(rubric, leaf_bools)
        score_value = round(derived["quality_score"], 4)
        comment = "\n".join(
            f"[{leaf}] {'✓' if leaf_bools.get(leaf) else '✗'} "
            f"{(v.get('reasoning') if isinstance(v, dict) else '') or ''}"
            for leaf, v in review.rubric_results.items()
        )
        result = loader.save_manual_score(
            model_id=model_id,
            task_name=task_name,
            run_id=body.run_id,
            score=score_value,
            rubric_results=leaf_bools,
            completion=derived["completion"],
            quality_score=derived["quality_score"],
            completion_rate=derived["completion_rate"],
            complete_flag=derived["complete_flag"],
            comment=comment,
            scored_by="agent",
            adopted_agent_timestamp=review.timestamp,
        )
    else:
        flat_items = review_data.get("rubric_scores")
        if not isinstance(flat_items, list):
            raise _bad_request(ValueError("旧 agent_review 缺少 rubric_scores，无法采纳"))
        result = loader.save_flat_score(
            model_id=model_id,
            task_name=task_name,
            run_id=body.run_id,
            rubric_scores=flat_items,
            comment=str(review_data.get("reasoning", "")),
            scored_by="agent",
        )
    if review.trace_quality is not None:
        try:
            loader.save_trace_quality(model_id, task_name, body.run_id, review.trace_quality)
        except (FileNotFoundError, ValueError):
            pass
    return {
        "success": True,
        "message": "已采纳 Agent 评测结果",
        "score": result.get("score"),
    }


# ---------------------------------------------------------------- Agent 评测（批量）

@router.post("/api/model/{model_id}/batch-agent-eval")
def start_batch_eval(model_id: str, body: BatchEvalRequest) -> dict:
    """body `{task_names, evaluate_trace=False, skip_existing=True, auto_adopt=False,
    concurrency=32(1..128), run_id="run_1"}`；返回 `{batch_id, total, skipped, started, tasks[]}`。
    """
    if not body.task_names:
        raise _bad_request(ValueError("task_names 不能为空"))
    manager = _get_batch_manager()
    session: BatchEvalSession = manager.start_batch(
        model_id=model_id,
        task_names=body.task_names,
        evaluate_trace=body.evaluate_trace,
        skip_existing=body.skip_existing,
        auto_adopt=body.auto_adopt,
        concurrency=body.concurrency,
        run_id=body.run_id,
    )
    return {
        "batch_id": session.batch_id,
        "total": session.total,
        "skipped": session.skipped,
        "started": session.started,
        "tasks": [task.to_dict() for task in session.tasks],
    }


@router.get("/api/model/{model_id}/batch-agent-eval/{batch_id}")
def get_batch_eval(model_id: str, batch_id: str) -> dict:
    session = _get_batch_manager().get_session(batch_id)
    if session is None:
        raise _not_found(FileNotFoundError(f"批次不存在：{batch_id}"))
    return session.to_dict()


@router.post("/api/model/{model_id}/batch-agent-eval/{batch_id}/cancel")
def cancel_batch_eval(model_id: str, batch_id: str) -> dict:
    session = _get_batch_manager().cancel_batch(batch_id)
    if session is None:
        raise _not_found(FileNotFoundError(f"批次不存在：{batch_id}"))
    return {"success": True, "message": "已取消批量评测"}


@router.get("/api/model/{model_id}/batch-agent-eval")
def latest_batch_eval(model_id: str) -> dict:
    """每模型最新批次（前端重开弹窗用）。"""
    session = _get_batch_manager().latest_session(model_id)
    return session.to_dict() if session is not None else {}

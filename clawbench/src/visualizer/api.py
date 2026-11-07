"""报告页 API 路由表（全部 GET，run_id 语义：average 默认 / run_1..n 具体 run；
产物端点拒绝 average——不是磁盘目录）。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse

from src.analyzer.core import (
    COMPARISON_DIMENSIONS,
    calculate_statistics,
    load_all_results_multi,
    merge_task_data,
)
from src.runs import AVERAGE_RUN_ID, load_trace_config
from src.visualizer.data_loader import DataLoader, get_loader

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ZIP_MEDIA_TYPE = "application/zip"


def _loader() -> DataLoader:
    return get_loader()


def _check_artifact_run(run_id: str) -> None:
    if run_id == AVERAGE_RUN_ID:
        raise HTTPException(
            status_code=400, detail=f"'{AVERAGE_RUN_ID}' 不是磁盘目录，请使用具体 run_id"
        )


def _cleanup_path(path: str) -> None:
    """BackgroundTask：删除临时文件及其目录。"""
    p = Path(path)
    try:
        shutil.rmtree(p.parent, ignore_errors=True)
    except OSError:
        pass


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/models")
def list_models() -> list[dict]:
    return _loader().get_all_models()


@router.get("/api/comparison")
def comparison(dimension: str = "primary_scenario", run_id: str = AVERAGE_RUN_ID) -> dict:
    if dimension not in COMPARISON_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"dimension 非法（合法：{'/'.join(COMPARISON_DIMENSIONS)}）",
        )
    return _loader().get_comparison_data(dimension, run_id)


@router.get("/api/model/{model_id}/runs")
def model_runs(model_id: str) -> dict:
    try:
        return _loader().get_model_runs(model_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/model/{model_id}")
def model_detail(model_id: str, run_id: str = AVERAGE_RUN_ID) -> dict:
    loader = _loader()
    try:
        model_dir = loader._model_dir(model_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    scores = load_all_results_multi(model_dir, run_id)
    configs = loader._load_configs()
    stats = calculate_statistics(merge_task_data(scores, configs))
    return {
        "model_id": model_id,
        "model_name": "_".join(model_id.split("_")[:2]),
        "stats": stats,
        "task_scores": scores,
        "task_configs": {name: cfg.model_dump() for name, cfg in configs.items()},
        "run_id": run_id,
    }


@router.get("/api/model/{model_id}/tasks")
def model_tasks(model_id: str, run_id: str = AVERAGE_RUN_ID) -> list[dict]:
    try:
        return _loader().get_task_scores(model_id, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/model/{model_id}/categories")
def model_categories(model_id: str, run_id: str = AVERAGE_RUN_ID) -> list[dict]:
    try:
        return _loader().get_categories(model_id, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/model/{model_id}/overall")
def model_overall(model_id: str, run_id: str = AVERAGE_RUN_ID) -> dict:
    try:
        return _loader().get_model_overall(model_id, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/case/{model_id}/{task_name}")
def case_detail(model_id: str, task_name: str, run_id: str = AVERAGE_RUN_ID) -> dict:
    try:
        return _loader().get_case_detail(model_id, task_name, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/dataset/distribution")
def dataset_distribution() -> dict:
    return _loader().get_dataset_distribution()


@router.get("/api/model/{model_id}/export")
def export_model(model_id: str, run_id: str = AVERAGE_RUN_ID) -> FileResponse:
    try:
        path = _loader().export_model(model_id, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=XLSX_MEDIA_TYPE,
        filename=f"{model_id}_analysis_report.xlsx",
        background=BackgroundTask(_cleanup_path, str(path)),
    )


@router.get("/api/model/{model_id}/task/{task_name}/sessions")
def task_sessions(model_id: str, task_name: str, run_id: str = "run_1") -> dict:
    _check_artifact_run(run_id)
    try:
        return _loader().get_sessions(model_id, task_name, run_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/model/{model_id}/task/{task_name}/workspace")
def task_workspace(model_id: str, task_name: str, run_id: str = "run_1") -> FileResponse:
    _check_artifact_run(run_id)
    try:
        path = _loader().build_workspace_zip(model_id, task_name, run_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=ZIP_MEDIA_TYPE,
        filename=f"{task_name}_{run_id}_workspace.zip",
        background=BackgroundTask(_cleanup_path, str(path)),
    )


@router.get("/api/trace-config")
def trace_config() -> dict:
    return load_trace_config()

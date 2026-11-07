"""报告页服务入口（FastAPI + React，端口 4999）。

启动：`uv run python main.py visualize --result-dir results --port 4999`
（或 `uv run python src/visualizer/server.py --result-dir results --port 4999`）。
前端构建：`cd web && npm install && npm run build`（产物 web/dist，由后端托管；
SPA fallback：未匹配 API 的路径回 index.html；dist 缺失时 `/` 返回 JSON 提示）。
开发代理：Vite dev 代理 `/api` → `http://localhost:4999`。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.visualizer.api import router as api_router
from src.visualizer.data_loader import init_loader

WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


def _resolve_tasks_dir(tasks_dir: str | None) -> str | None:
    """未显式给出 tasks_dir 时，默认使用项目根下的 tasks/。"""
    if tasks_dir:
        return tasks_dir
    root = Path(__file__).resolve().parent.parent.parent
    for name in ("tasks",):
        candidate = root / name
        if candidate.is_dir():
            return str(candidate)
    return None


def create_app(result_dir: str | None = None, tasks_dir: str | None = None) -> FastAPI:
    """全局 `data_loader` 单例由 `init_loader()` 注入。"""
    app = FastAPI(title="ClawBench 评测报告页", version="1.0.0")
    init_loader(result_dir or "results", _resolve_tasks_dir(tasks_dir))
    app.include_router(api_router)
    if WEB_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            # SPA fallback：未匹配 API 的路径回 index.html
            target = WEB_DIST / full_path
            if full_path and target.is_file():
                return FileResponse(target)
            return FileResponse(WEB_DIST / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        async def dist_missing() -> JSONResponse:
            return JSONResponse(
                {"message": "前端未构建：请先在 web 目录执行 npm install && npm run build"}
            )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="ClawBench 评测报告页")
    parser.add_argument("--result-dir", default="results")
    parser.add_argument("--tasks-dir", default=None)
    parser.add_argument("--port", type=int, default=4999)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    app = create_app(args.result_dir, args.tasks_dir)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

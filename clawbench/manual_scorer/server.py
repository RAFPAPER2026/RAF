"""人工打分页服务入口：`create_app` 注入 api 模块全局单例
（`data_loader`、`_agent_manager`、`_batch_manager`、`_agent_config_path`）。

前端构建：`cd manual_scorer/web && npm install && npm run build`（产物 `web/dist/`，
由 FastAPI 托管）。开发代理：Vite dev（5173）代理 `/api` → `http://localhost:5002`。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import manual_scorer.api as api
from manual_scorer.data_loader import ManualScorerDataLoader
from src.agent_scorer import BatchEvalManager, init_agent_manager
from src.i18n import SUPPORTED_LANGUAGES

WEB_DIST = Path(__file__).resolve().parent / "web" / "dist"
DEFAULT_AGENT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "configs" / "agent_scorer_config.json"
)


def create_app(
    result_dir: str | Path,
    tasks_dir: str | Path | None = None,
    agent_config_path: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="ClawBench 人工打分页", version="1.0.0")

    config_path = str(agent_config_path or DEFAULT_AGENT_CONFIG_PATH)
    loader = ManualScorerDataLoader(result_dir, tasks_dir)
    agent_manager = init_agent_manager(config_path)
    batch_manager = BatchEvalManager(
        result_base_dir=result_dir,
        tasks_dir=tasks_dir,
        agent_config_path=config_path,
        loader=loader,
        agent_manager=agent_manager,
    )
    api.init_globals(
        loader=loader,
        agent_manager=agent_manager,
        batch_manager=batch_manager,
        agent_config_path=config_path,
    )
    app.include_router(api.router)

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
                {
                    "message": "前端未构建：请先在 manual_scorer/web 目录执行 "
                    "npm install && npm run build"
                }
            )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="ClawBench 人工打分页")
    parser.add_argument("--result-dir", default="results")
    parser.add_argument("--tasks-dir", default=None)
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--agent-config", default=None)
    parser.add_argument("--lang", choices=SUPPORTED_LANGUAGES, default="zh")
    parser.add_argument("--quality-aggregation", choices=("paper", "legacy_mean"), default="paper")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    os.environ["CLAWBENCH_LANG"] = args.lang
    os.environ["CLAWBENCH_SCORING_MODE"] = args.quality_aggregation
    app = create_app(args.result_dir, args.tasks_dir, args.agent_config)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

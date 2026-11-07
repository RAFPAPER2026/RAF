"""ClawBench CLI 入口（eval/run/analyze/visualize/rerun/judge）。

- 评测：`uv run python main.py eval --tasks-dir tasks --result-base-dir results --workers 4`
- 评测+分析：`uv run python main.py run --tasks-dir tasks --model-name <model> --workers 4`
- 多轮：`uv run python main.py run --tasks-dir tasks --runs 3 --workers 4`
- 分析：`uv run python main.py analyze --result-dir results/<model_dir>`
- 报告页：`uv run python main.py visualize --result-dir results --port 4999`
- 重跑失败任务：`uv run python main.py rerun --result-dir results/<model_dir> --tasks-dir tasks`
- 裁判打分：`uv run python main.py judge --result-dir results/<model_dir> --tasks-dir tasks --adopt`

语言：`--lang {zh,en}`（默认 zh；en 读取 `config.en.json`，缺失回退中文）。
评分口径：`--quality-aggregation {paper,legacy_mean}`（默认 paper，论文 Eq.1）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

from src.i18n import SUPPORTED_LANGUAGES

_SCORING_MODES = ("paper", "legacy_mean")


def main(argv: Optional[list[str]] = None) -> int:
    # Windows 控制台默认 GBK：切换为 UTF-8（无法显示时以 ? 替换，避免崩溃）
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    parser = argparse.ArgumentParser(prog="clawbench", description="ClawBench evaluator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("eval", help="仅评测（起容器→初始化→发请求→采集轨迹）")
    _apply_eval_args(p_eval)

    p_run = sub.add_parser("run", help="评测 + 分析")
    _apply_eval_args(p_run)  # 参数与 eval 一致

    p_analyze = sub.add_parser("analyze", help="分析既有结果")
    p_analyze.add_argument("--result-dir", required=True)
    p_analyze.add_argument("--tasks-dir", default=None)
    p_analyze.add_argument("--run-id", default="average")
    _apply_runtime_args(p_analyze)

    p_visualize = sub.add_parser("visualize", help="起报告页（端口 4999）")
    p_visualize.add_argument("--result-dir", default="results")
    p_visualize.add_argument("--tasks-dir", default=None)
    p_visualize.add_argument("--port", type=int, default=4999)
    p_visualize.add_argument("--host", default="127.0.0.1")
    _apply_runtime_args(p_visualize)

    p_rerun = sub.add_parser("rerun", help="重跑失败任务（写入既有 run）")
    p_rerun.add_argument("--result-dir", required=True)
    p_rerun.add_argument("--tasks-dir", required=True)
    p_rerun.add_argument("--workers", type=int, default=4)
    p_rerun.add_argument("--retries", type=int, default=0)
    _apply_runtime_args(p_rerun)

    p_judge = sub.add_parser("judge", help="用裁判 agent 对既有结果打分（可自动采纳）")
    p_judge.add_argument("--result-dir", required=True, help="结果目录（模型目录或其父目录）")
    p_judge.add_argument("--tasks-dir", required=True)
    p_judge.add_argument("--run-id", default="run_1")
    p_judge.add_argument("--workers", type=int, default=1)
    p_judge.add_argument("--evaluate-trace", action="store_true", help="同时评过程质量维度")
    p_judge.add_argument("--skip-existing", action="store_true", help="已有 agent_review 的任务跳过")
    p_judge.add_argument("--adopt", action="store_true", help="把裁判结果采纳为 manual_score")
    p_judge.add_argument("--agent-config", default=None)
    _apply_runtime_args(p_judge)

    args = parser.parse_args(argv)
    _apply_runtime(args)

    if args.command in ("eval", "run"):
        from src.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            args.tasks_dir,
            args.result_base_dir,
            workers=args.workers,
            runs=args.runs,
            model_name=args.model_name,
            retries=args.retries,
        )
        result_dir = orchestrator.run()
        print(f"评测完成：{result_dir}")
        if args.command == "run":
            from src.analyzer import analyze_and_print, analyze_results

            analyze_and_print(result_dir, args.tasks_dir)
            report = analyze_results(result_dir, args.tasks_dir)
            print(f"分析报告：{report}")
        return 0

    if args.command == "analyze":
        from src.analyzer import analyze_and_print, analyze_results

        analyze_and_print(args.result_dir, args.tasks_dir, args.run_id)
        report = analyze_results(args.result_dir, args.tasks_dir, args.run_id)
        print(f"分析报告：{report}")
        return 0

    if args.command == "visualize":
        import uvicorn

        from src.visualizer.server import create_app

        app = create_app(args.result_dir, args.tasks_dir)
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    if args.command == "rerun":
        from src.orchestrator import rerun_failed

        result_dir = rerun_failed(args.result_dir, args.tasks_dir, args.workers, args.retries)
        print(f"重跑完成：{result_dir}")
        return 0

    if args.command == "judge":
        return _run_judge(args)

    parser.print_help()
    return 1


def _apply_eval_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tasks-dir", required=True)
    parser.add_argument("--result-base-dir", default="results")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--runs", type=int, default=1, help="每任务跑 k 轮（pass@k）")
    parser.add_argument("--retries", type=int, default=0)
    _apply_runtime_args(parser)


def _apply_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lang", choices=SUPPORTED_LANGUAGES, default="zh",
        help="任务语言：zh 读 config.json，en 读 config.en.json（缺失回退中文）",
    )
    parser.add_argument(
        "--quality-aggregation", choices=_SCORING_MODES, default="paper",
        help="质量分口径：paper=论文 Eq.1（AND 组全过才得分）；legacy_mean=AND 组取均值",
    )


def _apply_runtime(args: argparse.Namespace) -> None:
    os.environ["CLAWBENCH_LANG"] = args.lang
    os.environ["CLAWBENCH_SCORING_MODE"] = args.quality_aggregation


def _run_judge(args: argparse.Namespace) -> int:
    """用 BatchEvalManager 对结果目录跑裁判 agent（可选自动采纳）。"""
    from manual_scorer.data_loader import ManualScorerDataLoader
    from src.agent_scorer import BatchEvalManager, init_agent_manager
    from src.agent_scorer.batch_models import BatchTaskStatus
    from src.runs import resolve_run_dir

    result_dir = Path(args.result_dir)
    if not result_dir.is_dir():
        print(f"结果目录不存在：{result_dir}")
        return 1
    model_dirs = (
        [result_dir]
        if (result_dir / "result.json").is_file()
        else [p for p in sorted(result_dir.iterdir()) if p.is_dir() and (p / "result.json").is_file()]
    )
    if not model_dirs:
        print(f"未找到模型结果目录：{result_dir}")
        return 1

    project_root = Path(__file__).resolve().parent
    agent_config = args.agent_config or str(project_root / "configs" / "agent_scorer_config.json")
    loader = ManualScorerDataLoader(result_dir, args.tasks_dir)
    agent_manager = init_agent_manager(agent_config)
    batch_manager = BatchEvalManager(
        result_base_dir=result_dir,
        tasks_dir=args.tasks_dir,
        agent_config_path=agent_config,
        loader=loader,
        agent_manager=agent_manager,
    )

    sessions = []
    for model_dir in model_dirs:
        model_id = model_dir.name
        task_names = []
        for case_dir in sorted(p for p in model_dir.iterdir() if p.is_dir()):
            try:
                resolve_run_dir(case_dir, args.run_id)
            except (ValueError, FileNotFoundError):
                continue
            task_names.append(case_dir.name)
        if not task_names:
            print(f"[{model_id}] 无可用任务（run {args.run_id}）")
            continue
        session = batch_manager.start_batch(
            model_id=model_id,
            task_names=task_names,
            evaluate_trace=args.evaluate_trace,
            skip_existing=args.skip_existing,
            auto_adopt=args.adopt,
            concurrency=max(1, args.workers),
            run_id=args.run_id,
        )
        sessions.append((model_id, session))
        print(f"[{model_id}] 裁判任务已启动：{session.started}/{session.total}（跳过 {session.skipped}）")

    if not sessions:
        return 1

    final_states = {
        BatchTaskStatus.COMPLETED,
        BatchTaskStatus.FAILED,
        BatchTaskStatus.TIMEOUT,
        BatchTaskStatus.CANCELLED,
    }
    while True:
        pending = sum(
            1
            for _, session in sessions
            for task in session.tasks
            if task.status not in final_states
        )
        if pending == 0:
            break
        time.sleep(2)

    exit_code = 0
    for model_id, session in sessions:
        counts = session.summary()
        print(f"[{model_id}] 裁判完成：{counts}")
        if counts.get("failed") or counts.get("timeout"):
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

"""评测日志：控制台 + 文件双通道配置。

- 控制台短格式（时间 + 级别 + 消息）：评测终端实时看进度
- 文件完整格式（时间 + 级别 + logger + 线程 + 消息）：落盘 `{log_dir}/eval.log` 排查用
- `setup_logging()` 幂等：控制台 handler 全局只挂一次；文件 handler 按路径登记，
  同一进程切换到新的结果目录时先关闭上一个文件句柄，避免多条评测互相串写

用法：评测编排入口先 `setup_logging()`（控制台），拿到结果目录后直接
`setup_logging(result_dir)`，日志文件落在结果目录根（`{result_dir}/eval.log`），
不另建 `logs/` 子目录。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FILE_NAME = "eval.log"

_CONSOLE_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s %(threadName)s - %(message)s"
_CONSOLE_DATE = "%H:%M:%S"
_FILE_DATE = "%Y-%m-%d %H:%M:%S"

_console_installed = False
_file_handlers: list[logging.FileHandler] = []
_active_log_file: Path | None = None


def _make_console_handler() -> logging.Handler:
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt=_CONSOLE_DATE))
    return handler


def _make_file_handler(log_dir: str | Path) -> logging.FileHandler:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / LOG_FILE_NAME, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_FILE_DATE))
    return handler


def setup_logging(
    log_dir: str | Path | None = None,
    *,
    level: int = logging.INFO,
    console: bool = True,
) -> None:
    """初始化根 logger；`log_dir` 非空时把 `{log_dir}/eval.log` 挂为文件输出
    （日志文件直接写进该目录，不再套 `logs/` 子目录）。

    - 幂等：进程内重复调用不会重复挂 handler
    - 同一进程切换新结果目录时，关闭上一个文件 handler，日志只写当前目录
    - 文件不可写时仅降级控制台，不阻断评测
    """
    global _console_installed
    root = logging.getLogger()
    if not _console_installed:
        root.setLevel(level)
        if console:
            root.addHandler(_make_console_handler())
        _console_installed = True
    if log_dir is None:
        return

    global _file_handlers, _active_log_file
    target = Path(log_dir).resolve() / LOG_FILE_NAME
    if _active_log_file == target:
        return
    for handler in _file_handlers:
        handler.close()
        root.removeHandler(handler)
    _file_handlers = []
    _active_log_file = None
    try:
        handler = _make_file_handler(log_dir)
    except OSError as exc:
        logging.getLogger(__name__).warning("日志文件不可写 %s：%s", target, exc)
        return
    root.addHandler(handler)
    _file_handlers = [handler]
    _active_log_file = target
    root.info("日志落盘：%s", target)

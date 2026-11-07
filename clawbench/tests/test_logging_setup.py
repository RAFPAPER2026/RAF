"""logging_setup：控制台 + 文件双通道、幂等、切换结果目录后只写新日志。"""

import io
import logging
from pathlib import Path

import pytest

from src import logging_setup
from src.logging_setup import LOG_FILE_NAME, setup_logging


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """快照根 logger 并在用例后恢复，避免污染同一进程内其它测试的日志配置。"""
    root = logging.getLogger()
    before_handlers = list(root.handlers)
    before_level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in before_handlers:
            handler.close()
            root.removeHandler(handler)
    root.setLevel(before_level)
    # 重置模块内部登记状态（下一用例从干净状态开始）
    logging_setup._console_installed = False
    logging_setup._file_handlers = []
    logging_setup._active_log_file = None


def _file_handlers_for(root: logging.Logger, path: Path) -> list[logging.FileHandler]:
    path = path.resolve()
    return [
        h for h in root.handlers
        if isinstance(h, logging.FileHandler) and Path(h.baseFilename).resolve() == path
    ]


def test_setup_logging_writes_console_and_file(tmp_path, monkeypatch):
    """控制台（stderr）与文件 `{log_dir}/eval.log` 都能收到日志（文件直接落在所给目录根）。"""
    stderr = io.StringIO()
    monkeypatch.setattr("sys.stderr", stderr)

    # 模拟评测场景：传入结果目录本身，日志文件直接落在其下，不套 logs/ 子目录
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    setup_logging(result_dir)
    logger = logging.getLogger("test.logging_setup")
    logger.info("hello 评测日志")
    logger.warning("warning 信息")

    # 控制台：短格式（时间 + 级别 + 消息）
    console = stderr.getvalue()
    assert "[INFO]" in console and "hello 评测日志" in console
    assert "[WARNING]" in console and "warning 信息" in console

    # 文件：完整格式 + 消息内容（{result_dir}/eval.log，无中间 logs 目录）
    log_file = result_dir / LOG_FILE_NAME
    assert not (result_dir / "logs").exists()
    content = log_file.read_text(encoding="utf-8")
    assert "hello 评测日志" in content
    assert "warning 信息" in content


def test_setup_logging_idempotent_and_switches_dir(tmp_path):
    """同目录重复 setup 不重复挂文件 handler；切换目录后旧句柄关闭，只写新文件。"""
    root = logging.getLogger()
    dir1 = tmp_path / "result_a"
    dir2 = tmp_path / "result_b"
    dir1.mkdir()
    dir2.mkdir()

    setup_logging(dir1)
    log1 = dir1 / LOG_FILE_NAME
    assert len(_file_handlers_for(root, log1)) == 1

    # 幂等：同目录再 setup，不新增
    setup_logging(dir1)
    assert len(_file_handlers_for(root, log1)) == 1

    # 切换新结果目录：旧文件 handler 移除，新目录有且仅有一个
    setup_logging(dir2)
    log2 = dir2 / LOG_FILE_NAME
    assert len(_file_handlers_for(root, log1)) == 0
    assert len(_file_handlers_for(root, log2)) == 1

    logger = logging.getLogger("test.logging_setup")
    logger.info("second run line")
    assert "second run line" in log2.read_text(encoding="utf-8")

"""runner 的 openclaw 配置注入回归测试（tasks 目录顶层共享 openclaw.json）。"""

import json
from pathlib import Path

from src.models import TaskConfig
from src.runner import TaskRunner


class _FakeContainerClient:
    """记录 start 调用参数的假容器客户端。"""

    def __init__(self):
        self.start_kwargs = None

    def start(self, **kwargs):
        self.start_kwargs = kwargs
        worker_path = kwargs.get("worker_path")
        return {
            "container_name": "c1",
            "port": 51234,
            "worker_path": str(worker_path) if worker_path else "",
        }


def _runner(tasks_dir: Path) -> TaskRunner:
    client = _FakeContainerClient()
    runner = TaskRunner(container_client=client, tasks_dir=tasks_dir)
    return runner, client


def _task(task_dir: Path, extra: dict | None = None) -> TaskConfig:
    base = {"id": "t1", "prompt": "p"}
    if extra is not None:
        base["openclaw_config_path"] = extra.get("openclaw_config_path")
    return TaskConfig.model_validate(base)


def test_shared_config_used_when_task_has_no_key(tmp_path):
    """tasks 目录顶层 openclaw.json 存在且任务无自定义键 → 使用共享配置。"""
    tasks_dir = tmp_path / "tasks"
    task_dir = tasks_dir / "case1"
    task_dir.mkdir(parents=True)
    shared = tasks_dir / "openclaw.json"
    shared.write_text("{}", encoding="utf-8")

    runner, client = _runner(tasks_dir)
    config = _task(task_dir)
    runner._create_container(config, task_dir)

    assert client.start_kwargs["openclaw_config_path"] == str(shared)


def test_task_key_overrides_shared_config(tmp_path):
    """任务 config.json 顶层的 openclaw_config_path 键优先于共享配置。"""
    tasks_dir = tmp_path / "tasks"
    task_dir = tasks_dir / "case1"
    task_dir.mkdir(parents=True)
    (tasks_dir / "openclaw.json").write_text("{}", encoding="utf-8")
    override = tmp_path / "my_openclaw.json"
    override.write_text("{}", encoding="utf-8")

    runner, client = _runner(tasks_dir)
    config = _task(task_dir, {"openclaw_config_path": str(override)})
    runner._create_container(config, task_dir)

    assert client.start_kwargs["openclaw_config_path"] == str(override)


def test_no_config_when_neither_present(tmp_path):
    """无共享配置且任务无自定义键 → 不注入（用镜像内置配置）。"""
    tasks_dir = tmp_path / "tasks"
    task_dir = tasks_dir / "case1"
    task_dir.mkdir(parents=True)

    runner, client = _runner(tasks_dir)
    config = _task(task_dir)
    runner._create_container(config, task_dir)

    assert client.start_kwargs["openclaw_config_path"] is None


def test_nested_extra_object_is_not_read(tmp_path):
    """嵌套 extra 对象不是有效注入形式（runner 只读顶层未知键）。"""
    tasks_dir = tmp_path / "tasks"
    task_dir = tasks_dir / "case1"
    task_dir.mkdir(parents=True)
    (tasks_dir / "openclaw.json").write_text("{}", encoding="utf-8")
    nested = tmp_path / "nested.json"
    nested.write_text("{}", encoding="utf-8")
    config = TaskConfig.model_validate(
        {"id": "t1", "prompt": "p", "extra": {"openclaw_config_path": str(nested)}}
    )

    runner, client = _runner(tasks_dir)
    runner._create_container(config, task_dir)

    # 嵌套 extra 被忽略 → 回退到共享配置
    assert client.start_kwargs["openclaw_config_path"] == str(tasks_dir / "openclaw.json")


def test_worker_path_not_forced(tmp_path):
    """方案 A：runner 不传 worker_path，由容器管理服务使用默认 workspace 目录。"""
    tasks_dir = tmp_path / "tasks"
    task_dir = tasks_dir / "case1"
    task_dir.mkdir(parents=True)

    runner, client = _runner(tasks_dir)
    config = _task(task_dir)
    runner._create_container(config, task_dir)

    assert "worker_path" not in client.start_kwargs


def test_manual_runner_does_not_write_scores(tmp_path, monkeypatch):
    """manual-only：runner 只采集轨迹/工作区，不写 score/complete_flag，也不拷贝 verifier/。"""
    tasks_dir = tmp_path / "tasks"
    task_dir = tasks_dir / "case1"
    (task_dir / "verifier").mkdir(parents=True)
    script = task_dir / "verifier" / "check.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    config = TaskConfig.model_validate({"id": "t1", "prompt": "p", "verifier_type": "manual"})

    import src.runner as runner_mod
    from src.container_client import OpenclawGatewayClient

    class _FakeClient:
        def start(self, **kw):
            worker = tmp_path / "w"
            worker.mkdir(exist_ok=True)
            return {"container_name": "c1", "port": 1, "worker_path": str(worker)}

        def delete(self, name):
            pass

    class _FakeGateway(OpenclawGatewayClient):
        def __init__(self, *a, **kw):
            pass

        def chat(self, prompt):
            return {"choices": []}

    monkeypatch.setattr(runner_mod, "ContainerManagerClient", lambda *a, **kw: _FakeClient())
    monkeypatch.setattr(runner_mod, "OpenclawGatewayClient", _FakeGateway)
    monkeypatch.setattr(runner_mod.TaskRunner, "_wait_gateway_ready", staticmethod(lambda *a, **k: None))

    runner = runner_mod.TaskRunner(tasks_dir=tasks_dir)
    run_dir = tmp_path / "results" / "case1" / "run_1"
    data = runner.run_task(config, task_dir, run_dir, "run_1")

    score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    for key in ("score", "complete_flag", "passed_verifiers", "failed_verifiers", "llm_score"):
        assert key not in score
    assert not (run_dir / "verifier").exists()
    assert (run_dir / "sessions.json").is_file()


def test_non_manual_verifier_type_rejected():
    """rule/llm/both 任务类型不再受支持。"""
    import pytest

    for verifier_type in ("rule", "llm", "both"):
        with pytest.raises(Exception):
            TaskConfig.model_validate({"id": "t1", "prompt": "p", "verifier_type": verifier_type})


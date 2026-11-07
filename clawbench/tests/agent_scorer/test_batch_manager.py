"""批量编排测试：total==eligible、即时回填不死锁、原地重试恰一次、取消语义。

同步测试用 asyncio.run / 守护线程 loop 驱动，仓库无 pytest-asyncio。
"""

import asyncio
import json
import threading
import time

from manual_scorer.data_loader import ManualScorerDataLoader
from src.agent_scorer.batch_manager import BatchEvalManager
from src.agent_scorer.batch_models import BatchTaskStatus
from src.agent_scorer.exceptions import AgentConcurrentError
from src.agent_scorer.models import AgentReview

TREE_RUBRIC = {
    "completion_rubric": [{"id": "a", "type": "leaf", "name": "A"}],
    "quality_rubric": [{"weight": 1.0, "node": {"id": "q", "type": "leaf", "name": "Q"}}],
}
FLAT_RUBRIC = [{"completion_rubric": "做A", "quality_rubric": {"1.0": "好"}}]


def _make_env(tmp_path, task_names, rubrics=None):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    results_dir = tmp_path / "results"
    model_dir = results_dir / "model1"
    model_dir.mkdir(parents=True)
    for name in task_names:
        task_dir = tasks_dir / name
        task_dir.mkdir()
        rubric = (rubrics or {}).get(name, TREE_RUBRIC)
        (task_dir / "config.json").write_text(
            json.dumps(
                {"id": name, "prompt": "p", "verifier_type": "manual", "rubric": rubric},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        run_dir = model_dir / name / "run_1"
        run_dir.mkdir(parents=True)
        (run_dir / "score.json").write_text(
            json.dumps({"task_name": name, "status": "completed", "score": None}),
            encoding="utf-8",
        )
    (model_dir / "result.json").write_text("{}", encoding="utf-8")
    return tasks_dir, results_dir


class FakeScorer:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def evaluate(self, config, evaluate_trace, task_dir, result_dir):
        self.calls += 1
        item = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(item, Exception):
            raise item
        if item == "timeout":
            await asyncio.sleep(30)  # 超过 wait_for 超时
        return item


def _review(passed=True) -> AgentReview:
    return AgentReview(
        rubric_results={
            "a": {"passed": passed, "reasoning": "r"},
            "q": {"passed": passed, "reasoning": "r"},
        },
        confidence=0.9,
        time_analysis="无",
        info_fidelity_analysis="无",
        needs_human_review=False,
        review_notes="无需人工复核",
        timestamp="t",
    )


def _wait(session, timeout=10):
    deadline = time.time() + timeout
    while session.finished_at is None:
        if time.time() > deadline:
            raise TimeoutError("batch 未完成")
        time.sleep(0.01)


def _make_manager(results_dir, tasks_dir, loader, outcomes, timeout_seconds=5):
    cfg_path = results_dir.parent / "agent_cfg.json"
    cfg_path.write_text(json.dumps({"timeout_seconds": timeout_seconds}), encoding="utf-8")
    fake = FakeScorer(outcomes)
    return (
        BatchEvalManager(
            results_dir,
            tasks_dir,
            agent_config_path=cfg_path,
            loader=loader,
            scorer_factory=lambda: fake,
        ),
        fake,
    )


def test_total_equals_eligible(tmp_path):
    tasks_dir, results_dir = _make_env(tmp_path, ["ok1", "ok2"])
    (tasks_dir / "ok2" / "config.json").write_text(
        json.dumps(
            {"id": "ok2", "prompt": "p", "verifier_type": "manual", "rubric": FLAT_RUBRIC},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    manager, fake = _make_manager(results_dir, tasks_dir, loader, [_review()])
    session = manager.start_batch(model_id="model1", task_names=["ok1", "ok2"], concurrency=2)
    assert session.total == 2  # total == 请求数
    assert session.skipped == 1  # ok2 非 tree → 不合资格
    assert session.started == 1  # eligible == started
    assert len(session.tasks) == 1
    assert session.tasks[0].task_name == "ok1"


def test_skip_existing_agent_review(tmp_path):
    tasks_dir, results_dir = _make_env(tmp_path, ["t1"])
    score_path = results_dir / "model1" / "t1" / "run_1" / "score.json"
    data = json.loads(score_path.read_text(encoding="utf-8"))
    data["agent_review"] = {"rubric_format": "tree"}
    score_path.write_text(json.dumps(data), encoding="utf-8")
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    manager, _ = _make_manager(results_dir, tasks_dir, loader, [_review()])
    session = manager.start_batch(model_id="model1", task_names=["t1"], skip_existing=True)
    assert session.skipped == 1 and session.started == 0


def test_retry_exactly_once_in_place(tmp_path):
    tasks_dir, results_dir = _make_env(tmp_path, ["t1"])
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    manager, fake = _make_manager(results_dir, tasks_dir, loader, [ValueError("boom"), _review()])
    session = manager.start_batch(model_id="model1", task_names=["t1"], concurrency=1)
    _wait(session)
    task = session.tasks[0]
    assert fake.calls == 2  # 原地重试恰一次
    assert task.retried is True
    assert task.status == BatchTaskStatus.COMPLETED
    assert task.score == 1.0  # 不采纳时用 _compute_score_from_review 显示百分比


def test_no_deadlock_retry_concurrency_one(tmp_path):
    """concurrency=1 原地重试不死锁：首个任务失败重试成功后，队列即时回填。"""
    tasks_dir, results_dir = _make_env(tmp_path, ["t1", "t2"])
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    manager, _ = _make_manager(
        results_dir, tasks_dir, loader, [ValueError("x"), _review(), _review()]
    )
    session = manager.start_batch(model_id="model1", task_names=["t1", "t2"], concurrency=1)
    _wait(session)
    assert [t.status for t in session.tasks] == [
        BatchTaskStatus.COMPLETED,
        BatchTaskStatus.COMPLETED,
    ]


def test_concurrent_error_immediate_fail(tmp_path):
    """AgentConcurrentError 立即 FAILED（重试无意义）。"""
    tasks_dir, results_dir = _make_env(tmp_path, ["t1"])
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    manager, fake = _make_manager(
        results_dir, tasks_dir, loader, [AgentConcurrentError("busy")]
    )
    session = manager.start_batch(model_id="model1", task_names=["t1"])
    _wait(session)
    task = session.tasks[0]
    assert task.status == BatchTaskStatus.FAILED
    assert fake.calls == 1  # 未重试
    assert task.retried is False


def test_timeout_after_retry(tmp_path):
    """重试后 TIMEOUT → 标 TIMEOUT「(after retry)」。"""
    tasks_dir, results_dir = _make_env(tmp_path, ["t1"])
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    manager, _ = _make_manager(
        results_dir, tasks_dir, loader, ["timeout", "timeout"], timeout_seconds=0.05
    )
    session = manager.start_batch(model_id="model1", task_names=["t1"])
    _wait(session)
    task = session.tasks[0]
    assert task.status == BatchTaskStatus.TIMEOUT
    assert "(after retry)" in task.error
    assert task.retried is True


def test_cancel_marks_queued_cancelled(tmp_path):
    """取消语义：QUEUED 立即置 CANCELLED，RUNNING 自然跑完。"""
    tasks_dir, results_dir = _make_env(tmp_path, ["t1", "t2"])
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    started = threading.Event()
    release = threading.Event()

    class BlockingScorer:
        def __init__(self):
            self.calls = 0

        async def evaluate(self, config, evaluate_trace, task_dir, result_dir):
            self.calls += 1
            started.set()
            await asyncio.to_thread(release.wait, 5)
            return _review()

    blocking = BlockingScorer()
    manager = BatchEvalManager(
        results_dir, tasks_dir, loader=loader, scorer_factory=lambda: blocking
    )
    session = manager.start_batch(model_id="model1", task_names=["t1", "t2"], concurrency=1)
    assert started.wait(5)
    time.sleep(0.05)  # 让 t2 留在队列中
    manager.cancel_batch(session.batch_id)
    assert session.cancelled is True
    assert session.tasks[1].status == BatchTaskStatus.CANCELLED  # QUEUED 立即取消
    release.set()
    _wait(session)
    assert session.tasks[0].status == BatchTaskStatus.COMPLETED  # RUNNING 自然跑完


def test_auto_adopt_writes_manual_score(tmp_path):
    tasks_dir, results_dir = _make_env(tmp_path, ["t1"])
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    manager, _ = _make_manager(results_dir, tasks_dir, loader, [_review(passed=True)])
    session = manager.start_batch(model_id="model1", task_names=["t1"], auto_adopt=True)
    _wait(session)
    data = json.loads(
        (results_dir / "model1" / "t1" / "run_1" / "score.json").read_text(encoding="utf-8")
    )
    assert data["manual_score"] == 1.0
    assert data["manual_scored_by"] == "agent"
    assert data["rubric_results"] == {"a": True, "q": True}
    assert data["rubric_format"] == "tree"

"""持久化测试：doubtful 单向语义、缺失 score.json→FileNotFoundError、清旧产物。"""

import json

import pytest

from src.agent_scorer.models import AgentReview
from src.agent_scorer.scorer import AgentScorer


def test_save_agent_review_requires_score_json(tmp_path):
    with pytest.raises(FileNotFoundError):
        AgentScorer.save_agent_review(tmp_path, AgentReview())


def test_doubtful_one_way_semantics(tmp_path):
    score_path = tmp_path / "score.json"
    score_path.write_text(
        json.dumps({"task_name": "t", "status": "completed", "doubtful": False}),
        encoding="utf-8",
    )
    review = AgentReview(needs_human_review=True, timestamp="2026-08-21T00:00:00+00:00")
    AgentScorer.save_agent_review(tmp_path, review)
    data = json.loads(score_path.read_text(encoding="utf-8"))
    assert data["doubtful"] is True
    assert data["agent_review"]["needs_human_review"] is True
    assert data["agent_review"]["rubric_format"] == "tree"


def test_doubtful_never_cleared(tmp_path):
    """人工或前轮设置的存疑在重跑后保留（单向，只写 True 从不清除）。"""
    score_path = tmp_path / "score.json"
    score_path.write_text(json.dumps({"task_name": "t", "doubtful": True}), encoding="utf-8")
    AgentScorer.save_agent_review(tmp_path, AgentReview(needs_human_review=False))
    data = json.loads(score_path.read_text(encoding="utf-8"))
    assert data["doubtful"] is True


def test_clear_previous_result_removes_artifacts(tmp_path):
    judge_dir = tmp_path / "verifier" / "judge"
    judge_dir.mkdir(parents=True)
    (judge_dir / "agent_judge.jsonl").write_text("x\n", encoding="utf-8")
    (judge_dir / "exceptions.md").write_text("x", encoding="utf-8")
    proof = judge_dir / "proof"
    proof.mkdir()
    (proof / "shot.png").write_bytes(b"x")
    score_path = tmp_path / "score.json"
    score_path.write_text(
        json.dumps({"task_name": "t", "agent_review": {"rubric_format": "tree"}, "manual_score": 0.5}),
        encoding="utf-8",
    )
    AgentScorer.clear_previous_result(tmp_path)
    assert not (judge_dir / "agent_judge.jsonl").exists()
    assert not (judge_dir / "exceptions.md").exists()
    assert not proof.exists()
    data = json.loads(score_path.read_text(encoding="utf-8"))
    assert "agent_review" not in data
    assert data["manual_score"] == 0.5  # 不碰 manual_score

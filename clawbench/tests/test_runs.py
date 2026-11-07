"""多轮存储/发现/平均 + result.json 测试（src/runs.py）。"""

import json

import pytest

from src.runs import (
    _is_passed,
    apply_legacy_compat,
    average_case_scores,
    build_per_run_result_json,
    discover_runs,
    is_legacy_single_run,
    list_model_runs,
    migrate_legacy_to_run_1,
    next_run_id,
    resolve_run_dir,
    write_result_json,
)


def _make_score(**kwargs):
    base = {
        "task_name": "t",
        "status": "completed",
        "score": 1.0,
        "duration": 10.0,
        "input_tokens": 100,
        "output_tokens": 50,
    }
    base.update(kwargs)
    return base


def _write_modern_case(case_dir, run_scores):
    for run_id, score in run_scores.items():
        run_dir = case_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "score.json").write_text(
            json.dumps(score, ensure_ascii=False), encoding="utf-8"
        )


# ---------------------------------------------------------------- 发现/解析

def test_discover_runs_modern_ignores_stale_root(tmp_path):
    _write_modern_case(tmp_path, {"run_2": _make_score(), "run_1": _make_score(), "run_10": _make_score()})
    (tmp_path / "score.json").write_text("{}", encoding="utf-8")  # 陈旧根 score.json
    assert discover_runs(tmp_path) == ["run_1", "run_2", "run_10"]


def test_discover_runs_legacy_and_empty(tmp_path):
    (tmp_path / "score.json").write_text("{}", encoding="utf-8")
    assert discover_runs(tmp_path) == ["run_1"]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert discover_runs(empty) == []


def test_resolve_run_dir(tmp_path):
    _write_modern_case(tmp_path, {"run_1": _make_score()})
    assert resolve_run_dir(tmp_path, "run_1").name == "run_1"
    with pytest.raises(ValueError):
        resolve_run_dir(tmp_path, "average")
    with pytest.raises(FileNotFoundError):
        resolve_run_dir(tmp_path, "run_9")


def test_resolve_run_dir_legacy_root(tmp_path):
    (tmp_path / "score.json").write_text("{}", encoding="utf-8")
    assert resolve_run_dir(tmp_path, "run_1") == tmp_path


def test_is_legacy_single_run_and_migrate(tmp_path):
    (tmp_path / "score.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sessions.json").write_text("{}", encoding="utf-8")
    assert is_legacy_single_run(tmp_path) is True
    run_dir = migrate_legacy_to_run_1(tmp_path)
    assert (run_dir / "score.json").is_file()
    assert (run_dir / "sessions.json").is_file()
    assert discover_runs(tmp_path) == ["run_1"]
    assert is_legacy_single_run(tmp_path) is False


def test_next_run_id_and_list_model_runs(tmp_path):
    _write_modern_case(tmp_path / "case1", {"run_1": _make_score(), "run_2": _make_score()})
    _write_modern_case(tmp_path / "case2", {"run_2": _make_score()})
    info = list_model_runs(tmp_path)
    assert info["runs"] == ["run_1", "run_2"]
    assert info["max_run"] == 2
    assert info["per_case_runs"] == {"case1": ["run_1", "run_2"], "case2": ["run_2"]}
    assert next_run_id(tmp_path) == "run_3"


# ---------------------------------------------------------------- 通过判定

def test_is_passed_complete_flag_priority():
    assert _is_passed({"complete_flag": 1, "score": 0.0})
    assert not _is_passed({"complete_flag": 0, "score": 0.9})
    assert _is_passed({"complete_flag": None, "score": 0.9})
    assert not _is_passed({"score": 0.5})
    assert not _is_passed({"status": "completed"})


# ---------------------------------------------------------------- legacy 兼容

def test_apply_legacy_compat_tree_short_circuit():
    data = {
        "rubric_format": "tree",
        "rubric_results": {"a": True},
        "score": 0.8,
        "quality_score": 0.8,
        "complete_flag": 1,
    }
    assert apply_legacy_compat(dict(data)) == data


def test_apply_legacy_compat_synthesizes_from_manual_score():
    out = apply_legacy_compat({"manual_score": 0.5})
    assert out["rubric_scores"] == [{"completion": 1, "quality_score": 0.5, "item_score": 0.5}]
    assert out["score"] == 0.5
    assert out["completion_rate"] == 1.0
    assert out["complete_flag"] == 0  # 0.5 < 0.75
    assert out["manual_feedback"] == 0
    assert out["doubtful"] is False


def test_apply_legacy_compat_complete_flag_only_inferred_when_missing():
    out = apply_legacy_compat({"manual_score": 0.9, "complete_flag": None})
    assert out["complete_flag"] is None  # 键存在（None）时不推断


def test_apply_legacy_compat_dimension_scores_to_trace_quality():
    out = apply_legacy_compat(
        {"manual_score": 0.8, "dimension_scores": {"task_understanding": 0.5, "tool_usage": 1.0}}
    )
    assert out["trace_quality"]["avg_score"] == 0.75
    assert out["trace_quality"]["dimensions"]["tool_usage"] == 1.0


def test_apply_legacy_compat_unscored_untouched():
    """未打分任务（无 score/manual_score/rubric_scores）保持未打分。"""
    out = apply_legacy_compat({"status": "completed", "manual_score": None})
    assert "score" not in out
    assert out["manual_score"] is None


# ---------------------------------------------------------------- 多轮平均

def test_average_case_scores_single_run_short_circuit(tmp_path):
    score = _make_score(quality_score=0.8, complete_flag=1, rubric_results={"a": True})
    _write_modern_case(tmp_path, {"run_1": score})
    avg = average_case_scores(tmp_path)
    assert avg["quality_score"] == 0.8
    assert avg["rubric_results"] == {"a": True}  # k==1 返回真实 dict（per-run 字段不被抹掉）


def test_average_case_scores_multi(tmp_path):
    _write_modern_case(
        tmp_path,
        {
            "run_1": _make_score(score=1.0, duration=10.0, quality_score=1.0, complete_flag=1),
            "run_2": _make_score(score=0.6, duration=20.0, quality_score=0.6, complete_flag=0),
        },
    )
    avg = average_case_scores(tmp_path)
    assert avg["score"] == 0.8
    assert avg["duration"] == 15.0
    assert avg["quality_score"] == 0.8  # 每个 run 都有数值才平均
    assert avg["status"] == "completed"  # 2/2 严格多数
    assert avg["pass_rate_over_runs"] == 0.5
    assert avg["pass_at_1"] is True
    assert avg["pass_k"] is False
    assert avg["complete_flag"] == 0
    assert avg["run_count"] == 2
    assert avg["mean_score"] == 0.8
    assert [r["run_id"] for r in avg["runs"]] == ["run_1", "run_2"]
    assert avg["runs"][0]["passed"] is True
    assert avg["runs"][1]["passed"] is False


def test_average_case_scores_tie_fails(tmp_path):
    """k=2 平局判失败（严格多数）。"""
    _write_modern_case(
        tmp_path,
        {"run_1": _make_score(status="completed"), "run_2": _make_score(status="failed")},
    )
    assert average_case_scores(tmp_path)["status"] == "failed"


def test_average_case_scores_corrupt_run_skipped(tmp_path):
    _write_modern_case(tmp_path, {"run_1": _make_score(score=1.0), "run_2": _make_score(score=0.5)})
    (tmp_path / "run_2" / "score.json").write_text("{broken", encoding="utf-8")
    avg = average_case_scores(tmp_path)
    assert avg["score"] == 1.0  # 均值仅计入有效 run
    assert avg["run_count"] == 2
    assert len(avg["runs"]) == 1


def test_average_case_scores_no_runs_returns_none(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    assert average_case_scores(tmp_path) is None


def test_average_case_scores_manual_guard(tmp_path):
    """非 tree 的 manual 任务若 manual_score 有均值，合成一个 rubric_scores 项。"""
    _write_modern_case(
        tmp_path,
        {"run_1": _make_score(manual_score=0.5), "run_2": _make_score(manual_score=0.7)},
    )
    avg = average_case_scores(tmp_path)
    assert avg["manual_score"] == 0.6
    assert avg["rubric_scores"][0]["item_score"] == 0.6


# ---------------------------------------------------------------- result.json

def test_build_per_run_result_json():
    data = {
        "case2": {"run_1": _make_score(score=0.5, duration=5.0, status="failed", manual_score=None)},
        "case1": {
            "run_1": _make_score(score=1.0, duration=10.0, manual_score=0.9),
            "run_2": _make_score(score=0.8, duration=20.0, manual_score=0.8),
        },
    }
    result = build_per_run_result_json(data)
    assert result["summary"]["total_tasks"] == 2
    assert result["summary"]["completed_tasks"] == 1
    assert result["summary"]["failed_tasks"] == 1
    assert result["summary"]["total_duration"] == 35.0  # 所有 run 的时长总和
    assert result["summary"]["overall_score"] == (0.5 + (1.0 + 0.8) / 2) / 2
    case1 = next(t for t in result["tasks"] if t["task_name"] == "case1")
    assert case1["runs"]["run_2"]["score"] == 0.8
    assert case1["score"] == 1.0  # 镜像 run_1
    assert case1["manual_score"] == 0.9
    case2 = next(t for t in result["tasks"] if t["task_name"] == "case2")
    assert case2["manual_score"] is None  # 保持 None、从不回退到 score


def test_write_result_json_skips_corrupt_runs(tmp_path):
    _write_modern_case(tmp_path / "case1", {"run_1": _make_score(score=1.0)})
    (tmp_path / "case1" / "run_1" / "score.json").write_text("{bad", encoding="utf-8")
    data = write_result_json(tmp_path)
    assert data["summary"]["total_tasks"] == 0  # 损坏 run 跳过

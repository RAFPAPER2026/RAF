"""人工打分页数据层测试（回归：config 加载路径、manual 过滤、tree 评分写入）。"""

import json

from manual_scorer.data_loader import ManualScorerDataLoader

TREE_RUBRIC = {
    "completion_rubric": [
        {"id": "a", "type": "leaf", "name": "A"},
        {
            "id": "bc",
            "type": "group",
            "combinator": "or",
            "name": "BC",
            "children": [
                {"id": "b", "type": "leaf", "name": "B"},
                {"id": "c", "type": "leaf", "name": "C"},
            ],
        },
    ],
    "quality_rubric": [
        {"weight": 2.0, "node": {"id": "q", "type": "leaf", "name": "Q"}},
    ],
}


def _make_env(tmp_path, manual=True):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "t1").mkdir(parents=True)
    (tasks_dir / "t1" / "config.json").write_text(
        json.dumps(
            {
                "id": "t1",
                "prompt": "任务1",
                "verifier_type": "manual" if manual else "rule",
                "rubric": TREE_RUBRIC,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    results_dir = tmp_path / "results"
    model_dir = results_dir / "model1"
    run_dir = model_dir / "t1" / "run_1"
    run_dir.mkdir(parents=True)
    (run_dir / "score.json").write_text(
        json.dumps(
            {"task_name": "t1", "status": "completed", "duration": 10.0, "manual_score": None},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (model_dir / "result.json").write_text("{}", encoding="utf-8")
    return tasks_dir, results_dir


def test_get_task_config_loads(tmp_path):
    """回归：_load_task_config 必须把任务目录（非 config.json 文件）交给 TaskConfig.load。"""
    tasks_dir, results_dir = _make_env(tmp_path)
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    config = loader.get_task_config("t1")
    assert config is not None
    assert config.verifier_type == "manual"


def test_task_summaries_only_manual(tmp_path):
    tasks_dir, results_dir = _make_env(tmp_path / "rule_env", manual=False)  # rule 任务
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    assert loader.get_task_summaries("model1", "run_1") == []  # 只含 manual 任务
    tasks_dir, results_dir = _make_env(tmp_path / "manual_env", manual=True)
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    summaries = loader.get_task_summaries("model1", "run_1")
    assert [s["task_name"] for s in summaries] == ["t1"]
    assert summaries[0]["manual_score"] is None  # 未打分


def test_save_tree_score_and_result_json(tmp_path):
    tasks_dir, results_dir = _make_env(tmp_path)
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    result = loader.save_tree_score(
        "model1", "t1", "run_1",
        {"a": True, "b": True, "c": False, "q": True},
        comment="人工打分", scored_by="张三",
    )
    assert result["success"] is True
    assert result["score"] == 1.0  # quality: q=1.0
    # score.json 写入 + 派生字段
    score = json.loads(
        (results_dir / "model1" / "t1" / "run_1" / "score.json").read_text(encoding="utf-8")
    )
    assert score["manual_score"] == 1.0
    assert score["manual_scored_by"] == "张三"
    assert score["rubric_format"] == "tree"
    assert score["complete_flag"] == 1  # a ✓ + or(b✓,c✗) ✓ → 完成
    assert score["rubric_results"] == {"a": True, "b": True, "c": False, "q": True}
    # result.json 重建
    result_json = json.loads(
        (results_dir / "model1" / "result.json").read_text(encoding="utf-8")
    )
    assert result_json["tasks"][0]["runs"]["run_1"]["score"] == 1.0
    assert result_json["tasks"][0]["manual_score"] == 1.0


def test_save_tree_score_missing_leaf_rejected(tmp_path):
    tasks_dir, results_dir = _make_env(tmp_path)
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    try:
        loader.save_tree_score("model1", "t1", "run_1", {"a": True}, "c")
    except ValueError as exc:
        assert "未覆盖叶子" in str(exc)
    else:
        raise AssertionError("缺少叶子应报错")


def test_writable_run_dir_rejects_missing_run(tmp_path):
    tasks_dir, results_dir = _make_env(tmp_path)
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    try:
        loader._resolve_writable_run_dir("model1", "t1", "run_9")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("磁盘上不存在的 run 应被拒绝")


def test_model_summary_manual_only(tmp_path):
    tasks_dir, results_dir = _make_env(tmp_path)
    loader = ManualScorerDataLoader(results_dir, tasks_dir)
    models = loader.get_models()
    assert len(models) == 1
    assert models[0]["total"] == 1
    assert models[0]["scored"] == 0
    assert models[0]["name"] == "model1"  # 真实名取前两个 _ 段

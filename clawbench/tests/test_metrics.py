"""指标计算测试（src/metrics.py）。"""

from src.metrics import (
    calculate_metrics,
    is_tool_result_success,
    pair_tool_calls_and_results,
)


def _tool_use(name, input_data):
    return {"type": "assistant", "content": [{"type": "tool_use", "name": name, "input": input_data}]}


def _tool_result(content, is_error=None):
    block = {"type": "tool_result", "content": content}
    if is_error is not None:
        block["is_error"] = is_error
    return {"type": "toolresult", "content": [block]}


def test_pair_tool_calls_in_appearance_order():
    events = [
        _tool_use("read", {"file_path": "a.txt"}),
        _tool_result("内容", False),
        _tool_use("exec", {"command": "ls"}),
        _tool_result("Error: not found", True),
    ]
    pairs = pair_tool_calls_and_results(events)
    assert len(pairs) == 2
    assert pairs[0][0]["name"] == "read"
    assert pairs[1][0]["name"] == "exec"
    assert pairs[1][1]["is_error"] is True


def test_is_tool_result_success():
    assert is_tool_result_success({"content": "ok", "is_error": False})
    assert not is_tool_result_success({"content": "x", "is_error": True})
    assert not is_tool_result_success({"content": "Error: boom"})
    assert not is_tool_result_success({"content": "Exception raised"})
    assert is_tool_result_success({"content": ""})  # 无内容视为无错误信号


def test_calculate_metrics_basic():
    events = [
        _tool_use("read", {"file_path": "a.txt"}),
        _tool_result("内容", False),
        _tool_use("exec", {"command": "bad"}),
        _tool_result("Error", True),
        {"type": "assistant", "content": [{"type": "text", "text": "完成"}]},
    ]
    m = calculate_metrics(events, model_name="")
    assert m["tool_calls"] == 2
    assert m["tool_success"] == 1
    assert m["tool_failed"] == 1
    assert m["tool_success_rate"] == 0.5
    assert m["api_calls"] == 3
    assert m["error_recoveries"] == 0  # 失败之后没有成功调用
    assert m["error_recovery_rate"] == 0.0
    assert m["tool_names"] == ["read", "exec"]


def test_calculate_metrics_recovery():
    events = [
        _tool_use("exec", {"command": "bad"}),
        _tool_result("Error", True),
        _tool_use("exec", {"command": "good"}),
        _tool_result("ok", False),
    ]
    m = calculate_metrics(events)
    assert m["error_recoveries"] == 1
    assert m["error_recovery_rate"] == 1.0

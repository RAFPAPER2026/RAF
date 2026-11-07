"""Prompt 版本与模块装配测试。"""

from __future__ import annotations

from rubric import prompt_modules


def test_only_released_versions():
    versions = [v["version"] for v in prompt_modules.list_versions()]
    assert versions == ["v5.1", "v5.10"]


def test_active_version_is_latest():
    assert prompt_modules.get_active_version() == "v5.10"


def test_all_modules_present():
    for version in ("v5.1", "v5.10"):
        record = prompt_modules.load_version(version)
        assert record is not None
        for key in prompt_modules.MODULE_ORDER:
            assert record["modules"].get(key), f"{version} missing module {key}"


def test_capabilities_injected():
    prompt = prompt_modules.build_system_prompt("v5.10")
    assert "{capabilities}" not in prompt
    assert "意图理解" in prompt
    assert prompt.startswith("你是一个 AI Agent 评估标准设计专家")


def test_output_schema_weights():
    schema = prompt_modules.OUTPUT_SCHEMA["json_schema"]["schema"]
    weight = schema["$defs"]["weighted_item"]["properties"]["weight"]
    assert set(weight["enum"]) == {1, 2, 3, 4, 6}

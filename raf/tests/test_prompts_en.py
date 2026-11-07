"""英文 prompt 资产测试。"""

from __future__ import annotations

from rubric import prompt_modules


def test_english_capabilities_available():
    names = prompt_modules.capability_names("en")
    assert "Intent Understanding" in names
    assert "Tool Usage" in names
    assert len(names) == 12


def test_english_versions_exist():
    assert prompt_modules.has_english_version("v5.1")
    assert prompt_modules.has_english_version("v5.10")
    record = prompt_modules.load_version("v5.10", "en")
    assert record is not None
    assert record.get("language") == "en"
    assert record["modules"]["role"].strip()


def test_english_prompt_assembly():
    prompt = prompt_modules.build_system_prompt("v5.10", "en")
    assert "{capabilities}" not in prompt
    assert "Intent Understanding" in prompt
    assert "Rubric" in prompt
    assert len(prompt) > 1000


def test_missing_english_version_falls_back_to_chinese():
    # v5.1.en.json exists today; simulate a missing file by asking for a bogus version
    assert prompt_modules.load_version("does-not-exist", "en") is None
    # and the Chinese file remains the source for zh
    assert prompt_modules.load_version("v5.1", "zh") is not None


def test_rift_english_prompt(monkeypatch):
    from rubric import diagnostics

    captured = {}

    def fake_chat_json(messages):
        captured["messages"] = messages
        return {"findings": []}

    monkeypatch.setattr(diagnostics, "chat_json", fake_chat_json)
    diagnostics.diagnose_rubric(
        {"query": "x", "completion_rubric": [], "quality_rubric": []}, lang="en"
    )
    system = captured["messages"][0]["content"]
    user = captured["messages"][1]["content"]
    assert "RIFT framework" in system
    assert "Please diagnose" in user
    assert "subjective" in system and "evaluative words" in system


def test_refiner_english_prompt_assets():
    from rubric import refiner

    assert "prompt-engineering expert" in refiner.REFINE_SYSTEM_EN
    assert "{capabilities}" in refiner.REFINE_SYSTEM_EN

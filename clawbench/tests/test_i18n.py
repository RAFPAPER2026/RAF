"""语言选择与 config.en.json 回退测试。"""

from __future__ import annotations

import json

import pytest

from src.i18n import current_language
from src.models import TaskConfig

ZH = {"id": "t1", "prompt": "中文任务", "verifier_type": "manual", "language": "zh"}
EN = {"id": "t1", "prompt": "English task", "verifier_type": "manual", "language": "en"}


def _write(tmp_path, name: str, payload: dict) -> None:
    (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_load_falls_back_to_chinese(tmp_path):
    _write(tmp_path, "config.json", ZH)
    config = TaskConfig.load(tmp_path, "en")
    assert config.prompt == "中文任务"
    assert config.language == "zh"


def test_load_english_when_present(tmp_path):
    _write(tmp_path, "config.json", ZH)
    _write(tmp_path, "config.en.json", EN)
    config = TaskConfig.load(tmp_path, "en")
    assert config.prompt == "English task"
    assert config.language == "en"


def test_language_env_var(monkeypatch, tmp_path):
    _write(tmp_path, "config.json", ZH)
    _write(tmp_path, "config.en.json", EN)
    monkeypatch.setenv("CLAWBENCH_LANG", "en")
    assert current_language() == "en"
    assert TaskConfig.load(tmp_path).prompt == "English task"


def test_invalid_language_rejected():
    with pytest.raises(ValueError):
        current_language("fr")


def test_verifier_type_must_be_manual(tmp_path):
    payload = dict(ZH, verifier_type="rule")
    _write(tmp_path, "config.json", payload)
    with pytest.raises(ValueError):
        TaskConfig.load(tmp_path)

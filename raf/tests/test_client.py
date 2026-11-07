"""LLM 配置加载测试（环境变量优先于 local config）。"""

from __future__ import annotations

import pytest

from rubric import client


def test_env_overrides_local_config(monkeypatch):
    monkeypatch.setenv("RAF_LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("RAF_LLM_API_KEY", "test-key")
    monkeypatch.setenv("RAF_LLM_MODEL", "test-model")
    cfg = client.load_llm_config()
    assert cfg["base_url"] == "https://example.test/v1"
    assert cfg["api_key"] == "test-key"
    assert cfg["model"] == "test-model"


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("RAF_LLM_API_KEY", raising=False)
    monkeypatch.setattr(client, "load_llm_config", lambda: {"base_url": "", "api_key": "", "model": ""})
    with pytest.raises(RuntimeError):
        client.get_client()

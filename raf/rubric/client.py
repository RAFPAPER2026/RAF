"""统一 LLM 客户端：OpenAI 兼容 API 封装。

配置来源：data/llm_config.json（可选）与环境变量 RAF_LLM_BASE_URL / RAF_LLM_API_KEY /
RAF_LLM_MODEL / RAF_LLM_TIMEOUT（环境变量优先）。配置每次调用重新读取，改配置无需重启。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from openai import OpenAI

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LLM_CONFIG_FILE = DATA_DIR / "llm_config.json"


def load_llm_config() -> dict:
    """每次调用都重新读取配置。"""
    cfg: dict = {}
    if LLM_CONFIG_FILE.exists():
        try:
            loaded = json.loads(LLM_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg = loaded
        except Exception:
            pass
    cfg.setdefault("base_url", "")
    cfg.setdefault("api_key", "")
    cfg.setdefault("model", "")
    for key, env_name in (
        ("base_url", "RAF_LLM_BASE_URL"),
        ("api_key", "RAF_LLM_API_KEY"),
        ("model", "RAF_LLM_MODEL"),
        ("timeout", "RAF_LLM_TIMEOUT"),
    ):
        value = os.environ.get(env_name)
        if value:
            cfg[key] = value
    return cfg


def get_client() -> OpenAI:
    """HTTP 客户端不走系统代理（httpx.Client(proxy=None, trust_env=False)）。"""
    cfg = load_llm_config()
    if not cfg.get("api_key"):
        raise RuntimeError("LLM 未配置：请设置 RAF_LLM_API_KEY 或填写 data/llm_config.json 中的 api_key")
    return OpenAI(
        base_url=cfg.get("base_url") or None,
        api_key=cfg.get("api_key"),
        timeout=float(cfg.get("timeout", 300)),
        http_client=httpx.Client(proxy=None, trust_env=False),
    )


def _create_kwargs(cfg: dict, response_format=None) -> dict:
    kwargs = {"model": cfg.get("model", "")}
    if response_format is not None:
        kwargs["response_format"] = response_format
    # temperature 仅在 llm_config 显式配置时才发送，否则用模型默认值
    # （reasoning 模型在低温下会对深度分析任务产生超长思考、吃光 max_tokens）
    if cfg.get("temperature") is not None:
        kwargs["temperature"] = float(cfg["temperature"])
    if cfg.get("max_tokens"):
        kwargs["max_tokens"] = int(cfg["max_tokens"])
    return kwargs


def _content(resp) -> str:
    content = resp.choices[0].message.content
    if content is None:
        raise RuntimeError("LLM 返回了空内容")
    return content


def chat(messages, model: str | None = None, temperature: float | None = None) -> str:
    """普通对话，返回文本。"""
    cfg = load_llm_config()
    kwargs = _create_kwargs(cfg)
    if model:
        kwargs["model"] = model
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = get_client().chat.completions.create(messages=messages, **kwargs)
    return _content(resp)


def chat_json(messages, model: str | None = None, temperature: float | None = None) -> dict:
    """JSON 输出（response_format=json_object），返回解析后的 dict。"""
    cfg = load_llm_config()
    kwargs = _create_kwargs(cfg, response_format={"type": "json_object"})
    if model:
        kwargs["model"] = model
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = get_client().chat.completions.create(messages=messages, **kwargs)
    return json.loads(_content(resp))


def chat_structured(messages, output_schema: dict, model: str | None = None,
                    temperature: float | None = None) -> dict:
    """结构化输出（json_schema / strict）。output_schema 形如
    {"type": "json_schema", "json_schema": {"name": ..., "strict": ..., "schema": {...}}}"""
    cfg = load_llm_config()
    kwargs = _create_kwargs(cfg)
    if model:
        kwargs["model"] = model
    if temperature is not None:
        kwargs["temperature"] = temperature
    js = output_schema["json_schema"]
    kwargs["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": js["name"],
            "strict": js.get("strict", False),
            "schema": js["schema"],
        },
    }
    resp = get_client().chat.completions.create(messages=messages, **kwargs)
    return json.loads(_content(resp))

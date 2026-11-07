"""数据类定义：评测任务配置（config.json）与状态常量。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from src.i18n import SUPPORTED_LANGUAGES, current_language

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# ClawBench only ships tasks evaluated by human / agent judges ("manual").
VERIFIER_TYPES = ("manual",)


class TaskConfig(BaseModel):
    """评测任务配置（config.json / config.en.json）。extra 键保留，兼容未知字段。"""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    prompt: str = ""
    verifier_type: str = "manual"
    name: str | None = None
    # 分类字段（主场景缺失时回退 scenario_category，仅为兼容旧数据）
    primary_scenario: str | None = None
    scenario_category: str | None = None
    secondary_scenario: str | None = None
    ability_category: list[str] = Field(default_factory=list)
    ability_category_canonical: list[str] = Field(default_factory=list)
    difficulty: str | None = None
    # 配置文件字段名为 environment_complexity；内部沿用 complexity 供旧逻辑使用
    complexity: str | None = Field(
        default=None,
        validation_alias=AliasChoices("complexity", "environment_complexity"),
    )
    env_init_needed: bool = False
    skills: list[str] = Field(default_factory=list)
    language: str = "zh"
    # rubric：tree 为对象（QueryRubric dict）、flat 为 list，检测见 src/rubric/compat.py
    rubric: Any = None
    verifier: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ability_category", "ability_category_canonical", "skills", mode="before")
    @classmethod
    def _normalize_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v]

    @field_validator("complexity", mode="before")
    @classmethod
    def _normalize_complexity(cls, v: Any) -> str | None:
        return None if v is None else str(v)

    @field_validator("verifier_type")
    @classmethod
    def _check_verifier_type(cls, v: str) -> str:
        if v not in VERIFIER_TYPES:
            raise ValueError(
                f"unsupported verifier_type {v!r}; ClawBench tasks are evaluated as 'manual'"
            )
        return v

    @field_validator("language")
    @classmethod
    def _check_language(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language {v!r}; expected one of {SUPPORTED_LANGUAGES}")
        return v

    @property
    def task_name(self) -> str:
        return self.name or self.id

    @classmethod
    def config_path(cls, task_dir: str | Path, lang: str | None = None) -> Path:
        """语言对应的 config 文件路径（en 回退 zh）。"""
        language = current_language(lang)
        base = Path(task_dir)
        if language == "en":
            en_path = base / "config.en.json"
            if en_path.is_file():
                return en_path
        return base / "config.json"

    @classmethod
    def load(cls, task_dir: str | Path, lang: str | None = None) -> "TaskConfig":
        """读取 `{task_dir}/config.json`（lang=en 时读 `config.en.json`，缺失回退中文）。"""
        language = current_language(lang)
        path = cls.config_path(task_dir, language)
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("language", "zh" if path.name == "config.json" else "en")
        return cls.model_validate(data)

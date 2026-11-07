"""全部 Pydantic 数据模型：RubricNode / WeightedItem / QueryRubric / QueryItem / RubricReview 等。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def new_id(prefix: str) -> str:
    """自动生成 id，格式为 {prefix}-{uuid12}。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def now_iso() -> str:
    """当前时间戳（ISO 格式）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RubricNode(BaseModel):
    """Rubric 递归树节点：leaf 或 group。"""

    id: str = Field(default_factory=lambda: new_id("node"))
    type: Literal["leaf", "group"] = "leaf"
    name: str
    combinator: Literal["and", "or"] = "and"  # 仅 group 有意义
    children: list["RubricNode"] = Field(default_factory=list)  # leaf 为空数组
    tags: list[str] = Field(default_factory=list)  # 能力项标签，仅 leaf 填写

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.type == "group":
            # group 节点带 tags → 构造失败
            if self.tags:
                raise ValueError(f"group 节点不允许携带 tags: {self.name}")
            if not self.children:
                raise ValueError(f"group 节点必须至少有一个子节点: {self.name}")
        else:
            if self.children:
                raise ValueError(f"leaf 节点不允许有子节点: {self.name}")
            # leaf 节点无 tags → 警告（不阻断）
            if not self.tags:
                print(f"[warn] leaf 节点缺少 tags（不阻断）: {self.name}")
        return self


class WeightedItem(BaseModel):
    """质量量规顶层项：权重 × 根节点。权重范围 1-6（两层级权重：重要性 1/2/3 × 难度 1/2）。"""

    weight: float = Field(default=1.0, ge=1.0, le=6.0)
    node: RubricNode


class QueryRubric(BaseModel):
    """一条完整量规。"""

    id: str = Field(default_factory=lambda: new_id("rubric"))
    query: str
    query_id: str = ""  # 关联 QueryItem.id（集中管理后）
    prompt_version: str = ""  # 生成时使用的 prompt 版本
    language: str = "zh"  # zh | en
    completion_rubric: list[RubricNode] = Field(default_factory=list)  # 完成量规，无权重
    quality_rubric: list[WeightedItem] = Field(default_factory=list)  # 质量量规，加权


class QueryRubricCreate(BaseModel):
    """创建 rubric 用的载荷：id 由存储层生成。"""

    query: str
    query_id: str = ""
    prompt_version: str = ""
    language: str = "zh"
    completion_rubric: list[RubricNode] = Field(default_factory=list)
    quality_rubric: list[WeightedItem] = Field(default_factory=list)


class QueryItem(BaseModel):
    """集中管理的 query。"""

    id: str = Field(default_factory=lambda: new_id("query"))
    text: str
    tags: list[str] = Field(default_factory=list)
    language: str = "zh"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class RubricReview(BaseModel):
    """人工审核：1-5 星 + 三条备注。"""

    id: str = Field(default_factory=lambda: new_id("review"))
    rubric_id: str
    prompt_version: str = ""
    completion_score: int = Field(ge=1, le=5)
    quality_score: int = Field(ge=1, le=5)
    notes: list[str] = Field(default_factory=lambda: ["", "", ""])  # 三条 notes
    created_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def _check_notes(self):
        if len(self.notes) > 3:
            raise ValueError("notes 最多 3 条")
        return self


class RubricReviewCreate(RubricReview):
    """创建审核用的载荷。"""

    pass

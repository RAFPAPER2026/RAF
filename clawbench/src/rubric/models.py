"""Rubric 树形数据模型（字段精确，extra 字段忽略）。

- `RubricNode`：叶子与组共用；leaf=检查项（children 必须为空），group=容器（至少一个子节点）
- `WeightedItem`：仅质量树顶层使用；权重约束 1.0–6.0；组内子节点等权（and）或互斥（or）
- `QueryRubric`：任务 rubric 配置（对象形式，无外层数组；外层数组只是用例文件信封）
- `RubricResults`：叶子 id → 通过/失败；缺失叶子在评分时视为失败
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RubricNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    type: Literal["leaf", "group"] = "leaf"
    name: str = ""
    # 仅 group 生效：and=全部子节点通过、or=任一子节点通过
    combinator: Literal["and", "or"] = "and"
    children: list["RubricNode"] = Field(default_factory=list)  # leaf 必须为空数组
    tags: list[str] = Field(default_factory=list)  # 叶子标签（标签通过率统计用）


class WeightedItem(BaseModel):
    weight: float = Field(default=1.0, ge=1.0, le=6.0)
    node: RubricNode


class QueryRubric(BaseModel):
    id: str = ""
    query: str = ""
    query_id: str = ""
    prompt_version: str = ""
    completion_rubric: list[RubricNode] = Field(default_factory=list)  # 完成判定树
    quality_rubric: list[WeightedItem] = Field(default_factory=list)  # 质量评分树（顶层带权重）


class RubricResults(BaseModel):
    results: dict[str, bool] = Field(default_factory=dict)

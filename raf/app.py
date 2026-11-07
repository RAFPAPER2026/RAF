"""FastAPI 应用入口：挂载 API 路由、服务前端静态文件（frontend/dist）、启动时 seed demo 数据。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rubric.routes import router
from rubric.storage import DATA_DIR

app = FastAPI(title="RAF", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


# ---------- seed demo 数据（仅在文件缺失时创建） ----------

DEFAULT_CAPABILITIES = """\
意图理解：准确理解用户的核心目标、显式需求和隐含约束
条件判断：识别任务中的条件分支（"如果有冲突则…否则…"）和隐含前提
逻辑推理：从已知信息推导正确结论，做出合理判断（冲突判断、优先级排序等）
时间推理：处理时间计算、时序关系、日程冲突等时间相关问题
检索策略：构造有效的搜索关键词，选择合适的信息源
信息筛选：从返回结果中识别和提取与任务相关的信息
工具使用：选择正确的工具/API，给出准确的参数
上下文保持：在多步操作中不遗忘、不混淆关键信息
异常处理：识别执行过程中的错误并采取合理的修正措施
事实准确性：不编造不存在的信息、数据或引用
通用知识：正确运用领域知识和常识完成任务
沟通表达：向用户清晰完整地说明操作结果和决策理由
"""

DEMO_QUERIES = [
    {
        "id": "query-seed00000001",
        "text": "查看我本周的日程安排，如果有会议冲突帮我调整一下，再新建一个明天下午3点的项目专利讨论的提醒",
        "tags": ["日程管理"],
        "created_at": "2026-08-01T10:00:00+08:00",
        "updated_at": "2026-08-01T10:00:00+08:00",
    },
    {
        "id": "query-seed00000002",
        "text": "根据我的旅行备忘录，生成一份详细的行程安排，包含每天的时间规划和注意事项",
        "tags": ["内容生成"],
        "created_at": "2026-08-01T10:05:00+08:00",
        "updated_at": "2026-08-01T10:05:00+08:00",
    },
]


def _leaf(id_: str, name: str, tags: list[str]) -> dict:
    return {"id": id_, "type": "leaf", "name": name, "combinator": "and", "children": [], "tags": tags}


def _group(id_: str, name: str, combinator: str, children: list[dict]) -> dict:
    return {"id": id_, "type": "group", "name": name, "combinator": combinator, "children": children, "tags": []}


DEMO_RUBRICS = [
    {
        "id": "rubric-seed00000001",
        "query": DEMO_QUERIES[0]["text"],
        "query_id": "query-seed00000001",
        "prompt_version": "v5.10",
        "completion_rubric": [
            _leaf("node-seed00000001", "正确读取了本周日程安排", ["工具使用"]),
            _group("node-seed00000002", "会议冲突处理目标", "or", [
                _leaf("node-seed00000003", "有冲突时，建议了新时间或自行调整了日程", ["逻辑推理", "异常处理"]),
                _leaf("node-seed00000004", "无冲突时，成功创建了明天下午三点的提醒", ["工具使用", "时间推理"]),
            ]),
        ],
        "quality_rubric": [
            {"weight": 6, "node": _group("node-seed00000005", "冲突处理与决策质量", "and", [
                _leaf("node-seed00000006", "没有漏判任何时间重叠的会议，也没有把不相邻的会议误判为冲突", ["逻辑推理", "时间推理"]),
                _group("node-seed00000007", "处理路径与实际情况匹配", "or", [
                    _leaf("node-seed00000008", "有冲突时：调整了日程时间而不仅仅是提示存在冲突", ["异常处理"]),
                    _leaf("node-seed00000009", "无冲突时：直接创建了提醒而没有多余的询问或操作", ["工具使用"]),
                ]),
            ])},
            {"weight": 2, "node": _group("node-seed00000010", "日程信息处理质量", "and", [
                _leaf("node-seed00000011", "日程读取覆盖了本周每一天，没有遗漏任何日程条目", ["工具使用"]),
                _leaf("node-seed00000012", "明天下午3点被正确解析为具体日期和时间的值", ["时间推理"]),
            ])},
            {"weight": 1, "node": _group("node-seed00000013", "用户沟通得当", "or", [
                _leaf("node-seed00000014", "调整日程时：说明了被调整会议的原时间、新时间及避开冲突的判断依据", ["沟通表达"]),
                _leaf("node-seed00000015", "无冲突时：准确识别了无冲突状态且跳过调整步骤，未引入不必要的日程修改", ["沟通表达"]),
            ])},
        ],
    },
    {
        "id": "rubric-seed00000002",
        "query": DEMO_QUERIES[1]["text"],
        "query_id": "query-seed00000002",
        "prompt_version": "v5.10",
        "completion_rubric": [
            _leaf("node-seed00000016", "正确读取了旅行备忘录的内容", ["工具使用"]),
            _group("node-seed00000017", "行程文档交付目标", "and", [
                _leaf("node-seed00000018", "行程按天组织了每一天的内容", ["条件判断"]),
                _leaf("node-seed00000019", "每天都有对应的时间规划", ["时间推理"]),
                _leaf("node-seed00000020", "每天都有对应的注意事项", ["意图理解"]),
            ]),
        ],
        "quality_rubric": [
            {"weight": 2, "node": _leaf("node-seed00000021", "备忘录的读取没有遗漏关键信息", ["信息筛选"])},
            {"weight": 6, "node": _group("node-seed00000022", "行程文档整体质量", "and", [
                _leaf("node-seed00000023", "各天之间的目的地顺序在地理和交通上合理，没有出现折返或绕路", ["逻辑推理", "通用知识"]),
                _leaf("node-seed00000024", "备忘录中的日期、地点、偏好、约束都已纳入行程，没有遗漏", ["上下文保持"]),
                _leaf("node-seed00000025", "每天各活动的时间安排合理，没有出现明显过高或过低的预估", ["逻辑推理", "通用知识"]),
                _leaf("node-seed00000026", "每天的注意事项与该天行程场景直接相关，不是泛泛的通用提醒", ["逻辑推理"]),
                _leaf("node-seed00000027", "日期、时间段、活动内容三层排列清晰，便于逐天执行", ["沟通表达"]),
            ])},
        ],
    },
]

DEMO_REVIEWS = [
    {
        "id": "review-seed00000001",
        "rubric_id": "rubric-seed00000001",
        "prompt_version": "v5.10",
        "completion_score": 4,
        "quality_score": 4,
        "notes": [
            "OR 组分支覆盖了冲突/无冲突两条路径，区分度不错",
            "权重分配符合重要性×难度体系",
            "部分叶子可进一步打磨行为锚点",
        ],
        "created_at": "2026-08-05T14:30:00+08:00",
    },
]


def seed_demo_data() -> None:
    """启动时 seed demo 数据：仅在文件缺失时创建。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    caps_file = DATA_DIR / "capabilities.txt"
    if not caps_file.exists():
        caps_file.write_text(DEFAULT_CAPABILITIES, encoding="utf-8")

    active_file = DATA_DIR / "active_prompt_version.txt"
    if not active_file.exists():
        active_file.write_text("v5.10\n", encoding="utf-8")

    llm_file = DATA_DIR / "llm_config.json"
    if not llm_file.exists():
        llm_file.write_text(json.dumps({
            "base_url": "",
            "api_key": "",
            "model": "",
            "temperature": 0.2,
            "max_tokens": 4096,
            "timeout": 300,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    rubrics_file = DATA_DIR / "rubrics.json"
    if not rubrics_file.exists():
        rubrics_file.write_text(json.dumps(DEMO_RUBRICS, ensure_ascii=False, indent=2), encoding="utf-8")

    queries_file = DATA_DIR / "queries.json"
    if not queries_file.exists():
        queries_file.write_text(json.dumps(DEMO_QUERIES, ensure_ascii=False, indent=2), encoding="utf-8")

    reviews_file = DATA_DIR / "reviews.json"
    if not reviews_file.exists():
        reviews_file.write_text(json.dumps(DEMO_REVIEWS, ensure_ascii=False, indent=2), encoding="utf-8")


seed_demo_data()


# ---------- 前端静态文件托管（frontend/dist） ----------

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """SPA 回退：非 API 路径返回 index.html（支持前端路由深链接）。"""
        file_path = FRONTEND_DIST / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("RAF_HOST", "127.0.0.1"), port=int(os.environ.get("RAF_PORT", "8081")))

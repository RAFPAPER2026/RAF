"""Agent 自动评测（Claude Agent SDK）。

依赖 `claude_agent_sdk`（v0.2.98，query / ClaudeAgentOptions / ResultMessage）、
`src.rubric`（tree 格式模型+评分）、`src.runs`（resolve_run_dir/discover_runs）。
"""

from src.agent_scorer.batch_manager import BatchEvalManager
from src.agent_scorer.models import AgentEvalStatus, AgentEvalTask, AgentReview
from src.agent_scorer.scorer import AgentScorer
from src.agent_scorer.task_manager import (
    AgentTaskManager,
    get_agent_manager,
    init_agent_manager,
)

__all__ = [
    "AgentReview",
    "AgentEvalTask",
    "AgentEvalStatus",
    "AgentScorer",
    "AgentTaskManager",
    "init_agent_manager",
    "get_agent_manager",
    "BatchEvalManager",
]

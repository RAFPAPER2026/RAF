"""Agent 评测异常类型。"""


class AgentScorerError(Exception):
    """Agent 评测基础异常。"""


class AgentTimeoutError(AgentScorerError):
    """评测超时。"""


class AgentParseError(AgentScorerError):
    """结构化输出解析失败（无 ResultMessage / is_error / 无 structured_output / 非 dict）。"""


class AgentConcurrentError(AgentScorerError):
    """已有运行中的评测（API 层转 409）。"""


class AgentValidationError(AgentScorerError):
    """结构化输出校验失败。"""

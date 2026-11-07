"""报告页后端（FastAPI + React）。端口 4999。

读取 `results/` 磁盘目录提供报告；三个路由：`/` Dashboard、`/compare` 模型对比、
`/model/:modelId` 模型详情。
"""

from src.visualizer.data_loader import DataLoader, get_loader, init_loader, parse_model_timestamp

__all__ = ["DataLoader", "init_loader", "get_loader", "parse_model_timestamp"]

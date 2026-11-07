"""容器管理器 API 客户端 + Openclaw gateway 客户端。

- 容器管理器：FastAPI 服务（端口 10800），管理评测容器的启停删查
- gateway：容器内 Openclaw 网关 `http://localhost:{port}/v1/chat/completions`
"""

from __future__ import annotations

import os

import requests

CONTAINER_MANAGER_DEFAULT_URL = "http://localhost:10800"
GATEWAY_TOKEN_ENV = "OPENCLAW_GATEWAY_TOKEN"


def gateway_token() -> str:
    token = os.environ.get(GATEWAY_TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(
            f"未设置 {GATEWAY_TOKEN_ENV}：请先 export {GATEWAY_TOKEN_ENV}=<shared-token>，"
            "并确保容器以同一 token 启动（容器管理服务会自动注入）"
        )
    return token


class ContainerManagerError(RuntimeError):
    """容器管理器调用失败。"""


class ContainerManagerClient:
    """容器管理器 REST API 客户端（启动/停止/删除/查询）。"""

    def __init__(self, base_url: str = CONTAINER_MANAGER_DEFAULT_URL, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, json_body: dict | None = None) -> dict:
        try:
            resp = requests.request(
                method,
                f"{self.base_url}{path}",
                json=json_body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ContainerManagerError(f"容器管理器不可达：{exc}") from exc
        if resp.status_code >= 400:
            raise ContainerManagerError(f"容器管理器 {method} {path} 失败：{resp.status_code} {resp.text}")
        try:
            return resp.json()
        except ValueError:
            return {}

    def health(self) -> dict:
        return self._request("GET", "/health")

    def start(
        self,
        worker_path: str | None = None,
        openclaw_config_path: str | None = None,
        name: str | None = None,
        skills_path: str | None = None,
        preset_path: str | None = None,
    ) -> dict:
        """启动容器，返回 `{container_name, port, worker_path}`。"""
        body: dict = {
            "worker_path": worker_path,
            "openclaw_config_path": openclaw_config_path,
            "skills_path": skills_path,
            "preset_path": preset_path,
        }
        if name:
            body["name"] = name
        return self._request("POST", "/start", body)

    def stop(self, name: str) -> dict:
        return self._request("POST", "/stop", {"name": name})

    def list_containers(self) -> list:
        data = self._request("GET", "/containers")
        return data if isinstance(data, list) else []

    def get(self, name: str) -> dict:
        return self._request("GET", f"/containers/{name}")

    def delete(self, name: str) -> dict:
        return self._request("DELETE", f"/containers/{name}")


class OpenclawGatewayClient:
    """容器内 Openclaw 网关客户端（任务下发）。"""

    def __init__(
        self,
        port: int,
        host: str = "localhost",
        token: str | None = None,
        timeout: int = 1800,
    ):
        self.base_url = f"http://{host}:{port}/v1"
        self.token = token or gateway_token()
        self.timeout = timeout

    def chat(self, prompt: str, model: str = "openclaw") -> dict:
        """向 gateway 下发任务提问，返回完整响应 JSON（含会话事件时一并带回）。"""
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

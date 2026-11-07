"""Docker 容器管理服务（FastAPI，端口 10800）。

通过 REST API 管理评测容器的启停删查：
- 容器命名自动生成 `openclaw_worker_{8-hex}`
- 端口随机 50000-65535（线程安全锁 + 失败重试）
- worker 目录默认 `./workspace/openclaw_workers`，挂载到容器 `/root/Desktop`
- 自定义配置注入：`/start` 请求带 `openclaw_config_path`（绝对或相对路径，相对解析到
  当前工作目录），挂载为 `-v {path}:/root/.openclaw/openclaw.json`
- 容器启动命令：`bash -l -c "openclaw gateway"`（容器内 gateway 端口 18789）

启动：`uv run python src/container_manager.py`（镜像载入：
`docker load -i docker/openclaw/dist/openclaw-base.4.2.tar`，镜像默认
`openclaw:base.4.2`；`OPENCLAW_IMAGE` 环境变量可切换为 6 月版 `openclaw:base.6.34`）。
"""

from __future__ import annotations

import logging
import os
import random
import socket
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:  # 作为模块被引用（uv run python -m src.container_manager）
    from src.logging_setup import setup_logging
except ImportError:  # 直接 `python src/container_manager.py` 时 src 目录在 sys.path
    from logging_setup import setup_logging  # type: ignore[no-redef]

logger = logging.getLogger("container_manager")

IMAGE_NAME = os.environ.get("OPENCLAW_IMAGE", "openclaw:base.4.2")
# 容器内出网代理（OpenClaw 模型调用需要公网时设置，如 http://host.docker.internal:7898）
PROXY_URL = os.environ.get("OPENCLAW_PROXY", "")
CONTAINER_LABEL = "app=openclaw_worker"
CONTAINER_PREFIX = "openclaw_worker"
GATEWAY_PORT = 18789
DEFAULT_WORKERS_DIR = "./workspace/openclaw_workers"
PORT_RANGE = (50000, 65535)
PORT_ALLOC_RETRIES = 50


class StartRequest(BaseModel):
    worker_path: Optional[str] = None
    openclaw_config_path: Optional[str] = None
    name: Optional[str] = None
    # 环境初始化挂载：.skills/ → /root/.openclaw/workspace/skills，.preset/ → .../presets
    skills_path: Optional[str] = None
    preset_path: Optional[str] = None


class StopRequest(BaseModel):
    name: str


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


class ContainerRegistry:
    """内存容器注册表 + docker run/stop/rm 执行器。"""

    def __init__(self, workers_dir: str | Path):
        self.workers_dir = Path(workers_dir)
        self.workers_dir.mkdir(parents=True, exist_ok=True)
        self.containers: dict[str, dict] = {}
        self._lock = threading.Lock()

    def allocate_port(self) -> int:
        """随机端口 50000-65535（线程安全锁 + 失败重试）。"""
        with self._lock:
            used = {c["port"] for c in self.containers.values()}
            for _ in range(PORT_ALLOC_RETRIES):
                port = random.randint(*PORT_RANGE)
                if port in used:
                    continue
                if _port_available(port):
                    return port
        raise RuntimeError("无法分配空闲端口（50000-65535）")

    @staticmethod
    def _resolve_config_path(openclaw_config_path: str | None) -> str | None:
        """相对路径解析到当前工作目录。"""
        if not openclaw_config_path:
            return None
        path = Path(openclaw_config_path)
        return str(path if path.is_absolute() else Path.cwd() / path)

    def _docker_run_cmd(
        self,
        name: str,
        port: int,
        worker_path: str,
        config_path: str | None,
        skills_path: str | None,
        preset_path: str | None,
    ) -> list[str]:
        cmd = [
            "docker", "run", "-d",
            "--name", name,
            "-l", CONTAINER_LABEL,
            "-p", f"{port}:{GATEWAY_PORT}",
            "-v", f"{os.path.abspath(worker_path)}:/root/Desktop",
        ]
        if config_path:
            cmd += ["-v", f"{os.path.abspath(config_path)}:/root/.openclaw/openclaw.json"]
        if skills_path:
            cmd += ["-v", f"{os.path.abspath(skills_path)}:/root/.openclaw/workspace/skills"]
        if preset_path:
            cmd += ["-v", f"{os.path.abspath(preset_path)}:/root/.openclaw/workspace/presets"]
        # 会话转录挂载：容器内 ~/.openclaw/agents → 宿主 worker/.openclaw_agents
        # （openclaw HTTP API 响应不带 session，评测后从该目录读取会话事件）
        agents_host = Path(worker_path) / ".openclaw_agents"
        agents_host.mkdir(parents=True, exist_ok=True)
        cmd += ["-v", f"{os.path.abspath(agents_host)}:/root/.openclaw/agents"]
        if PROXY_URL:
            cmd += [
                "-e", f"http_proxy={PROXY_URL}",
                "-e", f"https_proxy={PROXY_URL}",
                "-e", "no_proxy=localhost,127.0.0.1,::1,0.0.0.0",
            ]
        token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
        if not token:
            raise HTTPException(
                status_code=500,
                detail="未设置 OPENCLAW_GATEWAY_TOKEN（容器与评测客户端需使用同一 token）",
            )
        cmd += ["-e", f"OPENCLAW_GATEWAY_TOKEN={token}"]
        cmd += [IMAGE_NAME, "bash", "-l", "-c", "openclaw gateway"]
        return cmd

    def create_container(
        self,
        worker_path: str | None = None,
        openclaw_config_path: str | None = None,
        name: str | None = None,
        skills_path: str | None = None,
        preset_path: str | None = None,
    ) -> dict:
        name = name or f"{CONTAINER_PREFIX}_{uuid.uuid4().hex[:8]}"
        with self._lock:
            if name in self.containers:
                logger.warning("容器已存在，拒绝重复创建：%s", name)
                raise HTTPException(status_code=409, detail=f"容器 {name} 已存在")
        resolved_worker = Path(worker_path) if worker_path else self.workers_dir / name
        resolved_worker.mkdir(parents=True, exist_ok=True)
        config_path = self._resolve_config_path(openclaw_config_path)
        logger.info(
            "创建容器 %s：worker=%s config=%s skills=%s preset=%s",
            name, resolved_worker, config_path, skills_path, preset_path,
        )
        # docker run 失败（如端口被外部占用）时换端口重试
        last_error: Exception | None = None
        for attempt in range(1, 4):
            port = self.allocate_port()
            cmd = self._docker_run_cmd(
                name, port, str(resolved_worker), config_path, skills_path, preset_path
            )
            logger.info("docker run 第 %d 次尝试：name=%s port=%d", attempt, name, port)
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            except FileNotFoundError as exc:
                logger.error("docker 命令不可用（请先安装 Docker 并载入镜像）")
                raise HTTPException(
                    status_code=500, detail="docker 命令不可用（请先安装 Docker 并载入镜像）"
                ) from exc
            if proc.returncode == 0:
                info = {
                    "container_name": name,
                    "port": port,
                    "worker_path": str(resolved_worker),
                    "config_path": config_path,
                }
                with self._lock:
                    self.containers[name] = info
                logger.info("容器启动成功：%s port=%d", name, port)
                return info
            last_error = RuntimeError(proc.stderr.strip() or "docker run 失败")
            logger.warning("docker run 失败（attempt %d/3）：%s", attempt, last_error)
        raise HTTPException(status_code=500, detail=f"容器启动失败：{last_error}")

    def _docker_status(self, name: str) -> str:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", name],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return "not_found"
        return proc.stdout.strip() or "unknown"

    def stop_container(self, name: str) -> dict:
        logger.info("停止容器：%s", name)
        proc = subprocess.run(["docker", "stop", name], capture_output=True, text=True, timeout=60)
        if proc.returncode != 0 and "No such container" not in proc.stderr:
            logger.warning("容器停止失败：%s：%s", name, proc.stderr.strip())
            raise HTTPException(status_code=500, detail=f"容器停止失败：{proc.stderr.strip()}")
        return {"container_name": name, "status": "stopped"}

    def remove_container(self, name: str) -> dict:
        logger.info("删除容器：%s", name)
        self.stop_container(name)
        subprocess.run(
            ["docker", "rm", name], capture_output=True, text=True, timeout=60
        )
        with self._lock:
            self.containers.pop(name, None)
        logger.info("容器已删除：%s", name)
        return {"container_name": name, "status": "removed"}

    def list_containers(self) -> list[dict]:
        with self._lock:
            names = sorted(self.containers.keys())
        result = []
        for name in names:
            info = dict(self.containers.get(name, {}))
            info["status"] = self._docker_status(name)
            result.append(info)
        return result

    def get_container(self, name: str) -> dict:
        with self._lock:
            if name not in self.containers:
                raise HTTPException(status_code=404, detail=f"容器 {name} 不存在")
            info = dict(self.containers[name])
        info["status"] = self._docker_status(name)
        return info


registry = ContainerRegistry(DEFAULT_WORKERS_DIR)

app = FastAPI(title="Openclaw Container Manager", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/start")
def start_container(req: StartRequest) -> dict:
    """启动评测容器（`openclaw_config_path` 相对路径解析到当前工作目录）。"""
    return registry.create_container(
        req.worker_path, req.openclaw_config_path, req.name, req.skills_path, req.preset_path
    )


@app.post("/stop")
def stop_container(req: StopRequest) -> dict:
    return registry.stop_container(req.name)


@app.get("/containers")
def list_containers() -> list[dict]:
    return registry.list_containers()


@app.get("/containers/{name}")
def get_container(name: str) -> dict:
    return registry.get_container(name)


@app.delete("/containers/{name}")
def delete_container(name: str) -> dict:
    return registry.remove_container(name)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="ClawBench 容器管理服务")
    parser.add_argument("--port", type=int, default=10800)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--workers-dir", default=DEFAULT_WORKERS_DIR)
    parser.add_argument(
        "--log-dir", default=None,
        help="容器管理日志目录（默认仅控制台，不落盘）",
    )
    args = parser.parse_args()
    setup_logging(Path(args.log_dir) if args.log_dir else None)
    registry.workers_dir = Path(args.workers_dir)
    registry.workers_dir.mkdir(parents=True, exist_ok=True)
    logger.info("容器管理服务启动：host=%s port=%d workers_dir=%s", args.host, args.port, registry.workers_dir)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

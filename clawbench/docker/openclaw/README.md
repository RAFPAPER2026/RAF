# OpenClaw sandbox image for ClawBench

The evaluation harness starts one isolated Docker container per task. The container
runs `openclaw gateway`; the harness sends the task prompt over the container's
OpenAI-compatible HTTP endpoint (`POST /v1/chat/completions`, mapped port 18789) and
collects `sessions.json` and `workspace/` afterwards.

## Image tags

| Tag | Base image | Notes |
|---|---|---|
| `openclaw:base.4.2` | `ghcr.io/openclaw/openclaw:2026.4.2` | default `IMAGE_NAME` of the harness |
| `openclaw:base.6.34` | `ghcr.io/openclaw/openclaw:2026.6.34` | extended-stable channel |

Select the image with `OPENCLAW_IMAGE`; the default is `openclaw:base.4.2`.

## Build

```bash
# from the repository root
docker build --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.4.2 \
  -t openclaw:base.4.2 clawbench/docker/openclaw
docker build --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.6.34 \
  -t openclaw:base.6.34 clawbench/docker/openclaw
```

If the Docker daemon cannot reach the registry directly, pull the base image on a
host with network access and `docker load` the resulting archive before building.

## Runtime token

The harness passes the same shared token to the container and to its gateway client:

```bash
export OPENCLAW_GATEWAY_TOKEN=<shared-token>
```

The token is never baked into the image. The container manager injects it with
`docker run -e OPENCLAW_GATEWAY_TOKEN=...`; the gateway configuration references the
environment variable (`--gateway-token-ref-env`).

## Model configuration

The image embeds a placeholder provider so that the gateway can start. For a real
evaluation, mount a task-set-level `openclaw.json` that points at your model endpoint:

1. Copy the template: `cp clawbench/openclaw.example.json clawbench/tasks/openclaw.json`.
2. Edit `models.providers` and `agents.defaults.model.primary`.
3. Start the evaluation from the `clawbench/` directory so the runner finds
   `tasks/openclaw.json` and mounts it into every container.

`tasks/openclaw.json` is git-ignored because it usually contains an API key. A
per-task override can be declared in a task's `config.json` with the optional
top-level `openclaw_config_path` key.

You can also bake a provider into the image at build time:

```bash
docker build \
  --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.4.2 \
  --build-arg OPENCLAW_BASE_URL=http://<host>:<port>/v1 \
  --build-arg OPENCLAW_API_KEY=<key> \
  --build-arg OPENCLAW_MODEL_ID=<model-id> \
  -t openclaw:base.4.2 clawbench/docker/openclaw
```

## Network and proxy

The container manager optionally forwards `OPENCLAW_PROXY` (for example
`http://host.docker.internal:3128`) into the container as `http_proxy`/`https_proxy`.
Use it only when the agent under test needs external network access.

## Image contract expected by the harness

| Requirement | Implementation |
|---|---|
| Runs as root, state under `/root/.openclaw` | `USER root`, `HOME=/root` |
| Gateway token from `OPENCLAW_GATEWAY_TOKEN` | `--gateway-token-ref-env` at build time; `-e` at runtime |
| Gateway reachable through the mapped port | `--gateway-bind lan`, container port 18789 |
| OpenAI-compatible chat endpoint | `gateway.http.endpoints.chatCompletions.enabled=true` |
| Configuration overridable at runtime | `-v {config}:/root/.openclaw/openclaw.json` |
| Session transcripts readable by the harness | `-v {worker}/.openclaw_agents:/root/.openclaw/agents` |

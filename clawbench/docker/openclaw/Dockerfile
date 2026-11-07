# OpenClaw sandbox image for the ClawBench evaluation harness.
#
# Built on the public OpenClaw image (ghcr.io/openclaw/openclaw) and customized for
# the harness contract:
#   - runs as root; configuration/state lives in /root/.openclaw
#     (the harness mounts -v {config}:/root/.openclaw/openclaw.json)
#   - the gateway token is supplied at runtime via the OPENCLAW_GATEWAY_TOKEN env var
#     (the harness passes it with `docker run -e`; never bake a token into the image)
#   - gateway.bind=lan (0.0.0.0) so the mapped port works through Docker networking
#   - the OpenAI-compatible HTTP API is enabled: POST /v1/chat/completions
#     (used by the harness gateway client)
#   - a placeholder model provider is embedded; mount your own openclaw.json at runtime
#
# Build (tag aligned with the harness default IMAGE_NAME):
#   docker build --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.4.2 \
#     -t openclaw:base.4.2 .
# Build the newer extended-stable channel:
#   docker build --build-arg OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.6.34 \
#     -t openclaw:base.6.34 .
# Select the image at runtime with the OPENCLAW_IMAGE environment variable
# (src/container_manager.py; default openclaw:base.4.2).

ARG OPENCLAW_BASE=ghcr.io/openclaw/openclaw:2026.4.2
FROM ${OPENCLAW_BASE}

# ---- harness contract: root user and configuration under /root ----
USER root
ENV HOME=/root

# ---- placeholder model provider ----
# For a real run, either pass build args for any OpenAI-compatible endpoint:
#   docker build --build-arg OPENCLAW_BASE_URL=http://<host>:<port>/v1 \
#     --build-arg OPENCLAW_API_KEY=<key> --build-arg OPENCLAW_MODEL_ID=<model> ...
# or mount your own openclaw.json at runtime (recommended, see README.md).
ARG OPENCLAW_BASE_URL=https://placeholder.invalid/v1
ARG OPENCLAW_API_KEY=fill-your-own-key
ARG OPENCLAW_MODEL_ID=placeholder-model

# ---- non-interactive onboarding: generate a complete baseline configuration ----
RUN openclaw onboard --non-interactive --accept-risk --mode local \
    --auth-choice custom-api-key --secret-input-mode plaintext \
    --custom-api-key "$OPENCLAW_API_KEY" \
    --custom-base-url "$OPENCLAW_BASE_URL" \
    --custom-model-id "$OPENCLAW_MODEL_ID" \
    --custom-compatibility openai \
    --gateway-auth token --gateway-token-ref-env OPENCLAW_GATEWAY_TOKEN \
    --gateway-bind lan \
    --tailscale off \
    --skip-health --skip-channels --skip-skills --skip-search --skip-ui \
    --no-install-daemon

# ---- harness contract: enable the OpenAI-compatible HTTP endpoint ----
RUN openclaw config set gateway.http.endpoints.chatCompletions.enabled true --strict-json

# The harness starts containers with `bash -l -c "openclaw gateway"`.
CMD ["openclaw", "gateway"]

# 1. Base image with Python 3.12 Debian slim
FROM python:3.12-slim-bookworm

# 2. Install essential system dependencies.
#    - samba-common-bin: provides 'testparm' binary for config validation
#    - procps: provides 'ps', 'kill', etc. for process inspection
#    - curl + ca-certificates: for health checks and HTTPS
RUN apt-get update && apt-get install -y --no-install-recommends \
    samba-common-bin \
    procps \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 3. Install Astral uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /uvx /bin/

# 4. Set working directory and environment variables
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    UV_LINK_MODE=copy

# 5. Install project dependencies using uv
COPY pyproject.toml uv.lock README.md /app/
RUN uv sync --frozen --no-dev --no-install-project

# 6. Copy application source code
COPY src/ /app/src/
RUN uv sync --frozen --no-dev

# 7. Expose WebUI port and define startup command
EXPOSE 8080
CMD ["python", "-m", "src.main"]

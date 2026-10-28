# syntax=docker/dockerfile:1

# ============================================================
# Stage 1: builder — install Python dependencies into a virtual environment.
# uv is only used in this stage and is not included in the final image.
# ============================================================
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=0 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# 1. Install dependencies only (cached while pyproject.toml and uv.lock are unchanged)
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# 2. Install the project itself
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ============================================================
# Stage 2: samba — extract testparm and its runtime libraries.
# ============================================================
FROM python:3.12-slim-bookworm AS samba

RUN apt-get update \
    && apt-get install -y --no-install-recommends samba-common-bin \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/collect-testparm.sh /tmp/collect-testparm.sh
RUN OUT=/out sh /tmp/collect-testparm.sh

# ============================================================
# Stage 3: runtime — the minimal final image.
# ============================================================
FROM python:3.12-slim-bookworm AS runtime

# 1. Copy testparm and its libraries from the samba stage, then update the linker cache
COPY --from=samba /out/ /
RUN ldconfig \
    && mkdir -p /var/lib/samba /var/cache/samba /run/samba

# 2. User and group management needs smbpasswd/pdbedit plus useradd/groupadd
RUN apt-get update \
    && apt-get install -y --no-install-recommends samba-common-bin passwd \
    && rm -rf /var/lib/apt/lists/*

# 3. Copy the builder virtual environment and application code (without uv or cache)
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY src/ ./src/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

EXPOSE 8080
CMD ["python", "-m", "src.main"]

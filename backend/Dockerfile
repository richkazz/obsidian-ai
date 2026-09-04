# =========================
# Build stage
# =========================
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

# IMPORTANT:
# Create the venv inside the Docker builder.
# Never reuse a Codespaces/local .venv.
RUN rm -rf /app/.venv \
    && uv venv /app/.venv --python python3.12 \
    && uv sync --frozen --no-cache

# Verify the environment before copying it
RUN /app/.venv/bin/python --version \
    && /app/.venv/bin/python -m uvicorn --version \
    && readlink -f /app/.venv/bin/python


# =========================
# Runtime stage
# =========================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    sox \
    libsox-fmt-all \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY . .

EXPOSE 8001

HEALTHCHECK --interval=30s \
    --timeout=10s \
    --start-period=10s \
    --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
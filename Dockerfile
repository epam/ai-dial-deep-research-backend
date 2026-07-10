FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /opt/app

# Install dependencies first to leverage Docker layer caching
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-install-project

# Copy source and install the project itself as a wheel (--no-editable), so the
# runtime stage only needs the venv — not the source tree.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/app

RUN adduser --uid 1001 --disabled-password --gecos "" appuser

# Root-owned on purpose: the app must not be able to modify its own code.
# World-readable is enough; bytecode is precompiled, so nothing writes here.
COPY --from=builder /opt/app/.venv ./.venv
ENV PATH="/opt/app/.venv/bin:$PATH"

# Temporary, until channel configs are fetched from DIAL file storage at runtime:
# bake the committed example config and default to it, so a bare deployment starts.
# Real deployments override CHANNEL_CONFIG_PATH (e.g. to a mounted config).
COPY data/configs/example.yaml ./data/configs/example.yaml
ENV CHANNEL_CONFIG_PATH=data/configs/example.yaml

USER appuser

EXPOSE 5000

CMD ["python", "-m", "dial_deep_research"]

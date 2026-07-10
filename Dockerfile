FROM python:3.13-slim AS builder

RUN pip install poetry==2.3.2

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1

WORKDIR /opt/app

# Install runtime dependencies first (into .venv) to leverage Docker layer caching.
# --no-root skips the project itself, so this layer only rebuilds when the lock changes.
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=poetry.lock,target=poetry.lock \
    poetry install --only main --no-root

# Copy source, build the project wheel, and install it into the venv (--no-deps: deps are
# already present). Installing the built wheel — not an editable install — means the runtime
# stage only needs the venv, not the source tree.
COPY pyproject.toml poetry.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    poetry build -f wheel && \
    .venv/bin/pip install --no-deps dist/*.whl

FROM python:3.13-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/app

RUN adduser --uid 1001 --disabled-password --gecos "" appuser

# Root-owned on purpose: the app must not be able to modify its own code.
# World-readable is enough; bytecode is precompiled, so nothing writes here.
COPY --from=builder /opt/app/.venv ./.venv
ENV PATH="/opt/app/.venv/bin:$PATH"

USER appuser

EXPOSE 5000

CMD ["python", "-m", "dial_deep_research"]

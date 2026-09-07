FROM python:3.13-alpine AS builder

RUN pip install poetry==2.3.2

# NO_PIP: the runtime installs nothing, so .venv is built without pip. Besides being dead
# weight, pip carries its own vendored dependencies, and recent versions list them in a
# CycloneDX SBOM (pip/_vendor/bom.cdx.json) that Trivy reads — an advisory against any of
# them then fails the image scan, for code the app never imports.
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_VIRTUALENVS_OPTIONS_NO_PIP=1

WORKDIR /opt/app

# Install runtime dependencies first (into .venv) to leverage Docker layer caching.
# --no-root skips the project itself, so this layer only rebuilds when the lock changes.
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=poetry.lock,target=poetry.lock \
    poetry install --only main --no-root

# Copy source, build the project wheel, and install it into the venv (--no-deps: deps are
# already present). Installing the built wheel — not an editable install — means the runtime
# stage only needs the venv, not the source tree. The venv has no pip, so the install runs
# through the base image's pip at /usr/local, with --python pointing it at the venv.
COPY pyproject.toml poetry.lock README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    poetry build -f wheel && \
    pip --python .venv/bin/python install --no-deps dist/*.whl

FROM python:3.13-alpine AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/app

# The base image ships packages that Alpine has already published a fix for, because Alpine
# patches its packages more often than the image is rebuilt. Trivy fails the build on any
# vulnerability that has a fix available, so install the patched versions here.
RUN apk --no-cache upgrade

# Remove the base image's pip for the same reason .venv is built without it: the runtime
# installs nothing, and pip's SBOM of its vendored dependencies makes Trivy report advisories
# against code the app never imports.
RUN python -m pip uninstall -y pip

# BusyBox adduser: -D = no password, -g = gecos.
RUN adduser -u 1001 -D -g "" appuser

# Root-owned on purpose: the app must not be able to modify its own code.
# World-readable is enough; bytecode is precompiled, so nothing writes here.
COPY --from=builder /opt/app/.venv ./.venv
ENV PATH="/opt/app/.venv/bin:$PATH"

USER appuser

EXPOSE 5000

CMD ["python", "-m", "dial_deep_research"]

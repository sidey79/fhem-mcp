# syntax=docker/dockerfile:1.26

FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip build && python -m build --wheel --outdir /dist

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# renovate: datasource=pypi depName=mcp-proxy versioning=pep440
ENV MCP_PROXY_VERSION=0.12.0

WORKDIR /app

COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl "mcp-proxy==${MCP_PROXY_VERSION}" && rm -f /tmp/*.whl

RUN useradd --create-home --uid 10001 appuser
USER appuser

ENTRYPOINT ["fhem-mcp"]
CMD ["--help"]

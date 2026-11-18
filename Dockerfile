# Build dependencies from the existing uv lock.
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM python:3.12-slim-bookworm AS builder

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml uv.lock ./

RUN uv sync \
    --locked \
    --no-dev \
    --no-install-project \
    --no-cache

# Ship the application, model and runtime dependencies.
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    REMBG_MODEL_PATH=/app/models/isnet-general-use.onnx \
    RECAP_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-dejavu-core \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

COPY app.py ./
COPY src/ ./src/

COPY data/api_crawl_infor_new.json \
     data/category_labels.yaml \
     ./data/

COPY background/ ./background/

COPY models/isnet-general-use.onnx \
     models/SHA256SUMS \
     ./models/

# COPY preserves host modes; make static assets readable by the runtime user.
RUN sha256sum -c models/SHA256SUMS \
    && chmod -R a+rX /app/data /app/background /app/models \
    && mkdir /app/output \
    && chown app:app /app/output

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s \
    --timeout=5s \
    --start-period=120s \
    --retries=3 \
    CMD ["python", "-c", \
         "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).close()"]

CMD ["python", "app.py"]

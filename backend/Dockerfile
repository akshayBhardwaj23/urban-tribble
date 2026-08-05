# Prophet needs a C++ toolchain to build, which the runtime image should not carry.
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=app:app . .

# UPLOAD_DIR is scratch space when STORAGE_BACKEND=s3; durable data belongs in the bucket.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UPLOAD_DIR=/data/uploads \
    APP_ENV=production \
    LOG_JSON=true

RUN mkdir -p /data/uploads && chown -R app:app /data
USER app

EXPOSE 8000

RUN chmod +x /app/entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8000/ready || exit 1

# Single worker: upload jobs live in an in-process pool. Scale horizontally
# only after moving uploads to a durable queue.
CMD ["./entrypoint.sh"]

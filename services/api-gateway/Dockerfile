FROM python:3.11-slim AS builder
WORKDIR /app

# Build-time env: disable .pyc files and pip cache in the build layer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Runtime stage ───────────────────────────────────────────────────────────
FROM python:3.11-slim

# PYTHONUNBUFFERED=1: ensures stdout/stderr logs are flushed immediately
# (critical for CloudWatch/structured logging — buffered output means missing logs)
# PYTHONDONTWRITEBYTECODE=1: no .pyc files in the container (smaller image, fewer inodes)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# curl: required for Docker healthcheck probe
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app.py .
RUN chown -R appuser:appuser /app

# Non-root user: reduces container breakout attack surface
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

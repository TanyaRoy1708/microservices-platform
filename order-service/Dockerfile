FROM python:3.11-slim

# Security: run as non-root + install curl for healthchecks in a single layer
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 5002
CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "2", "app:app"]
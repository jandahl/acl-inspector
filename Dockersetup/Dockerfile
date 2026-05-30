# Use a slim Python image for a smaller footprint
FROM python:3.11-slim-bookworm

WORKDIR /app

# Non-root user for runtime isolation
RUN groupadd -r -g 1000 appuser && useradd -r -u 1000 -g appuser -d /app appuser

# Copy application code (see .dockerignore at repo root for exclusions)
COPY . /app

# Ensure the cache directory exists and is owned by the runtime user.
# No pip installs needed: core web UI uses stdlib only (pyproject.toml dependencies=[]).
RUN mkdir -p /app/cache && chown -R appuser:appuser /app/cache

USER appuser

EXPOSE 8083

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8083/healthz', timeout=3)"

CMD ["python", "aclinspector.py", "web", "--port", "8083", "--addr", "0.0.0.0"]

# Use a slim Python image for a smaller footprint
FROM python:3.11-slim-bookworm

# Build-time metadata; inject at CI build time with --build-arg.
# Defaults are sensible for local builds.
ARG VERSION="0.1.0"
ARG VCS_REF="unknown"
ARG BUILD_DATE="unknown"

LABEL org.opencontainers.image.title="acl-inspector" \
      org.opencontainers.image.description="Firewall ACL analysis tool for Cisco ASA and FortiGate configurations" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/jandahl/acl-inspector" \
      org.opencontainers.image.licenses="MPL-2.0" \
      org.opencontainers.image.vendor="Jan Gronemann"

WORKDIR /app

# Non-root user for runtime isolation
RUN groupadd -r -g 1000 appuser && useradd -r -u 1000 -g appuser -d /app appuser

# Copy application code (see .dockerignore at repo root for exclusions)
COPY . /app

# Pre-compile bytecode so appuser (who cannot write to root-owned __pycache__
# dirs) never hits a PermissionError at runtime.
# Also ensure the cache dir is writable and home writes go to /tmp.
RUN python -m compileall -q /app && \
    mkdir -p /app/cache && chown -R appuser:appuser /app/cache

# Redirect home-dir writes (e.g. library caches) to world-writable /tmp so
# the container works correctly when run with an arbitrary host uid/gid.
ENV HOME=/tmp

USER appuser

EXPOSE 8083

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8083/healthz', timeout=3)"

CMD ["python", "aclinspector.py", "web", "--port", "8083", "--addr", "0.0.0.0"]

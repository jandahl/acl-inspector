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

# Non-root user for runtime isolation. No home dir set here; HOME=/tmp below
# redirects runtime writes to world-writable /tmp.
RUN groupadd -r -g 1000 appuser && useradd -r -u 1000 -g appuser appuser

# Install the parsing engine (ciscoconfparse2) and its hash-pinned transitive
# closure before copying app code, so this layer caches independently of source
# changes. ciscoconfparse2 is a core dependency (the single parsing engine).
COPY requirements-external.lock /app/requirements-external.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements-external.lock

# Copy application code (see .dockerignore at repo root for exclusions)
COPY . /app

# Pre-compile bytecode so appuser (who cannot write to root-owned __pycache__
# dirs) never hits a PermissionError at runtime.
# Also ensure the cache dir is writable and home writes go to /tmp.
RUN python -m compileall -q /app && \
    find /app -name __pycache__ -exec chown -R appuser:appuser {} + && \
    mkdir -p /app/cache && \
    # group 0 + 775: OpenShift/K8s arbitrary-UID pattern (random UID, GID 0)
    chown -R appuser:0 /app/cache && chmod 775 /app/cache

# Redirect home-dir writes (e.g. library caches) to world-writable /tmp so
# the container works correctly when run with an arbitrary host uid/gid.
# PYTHONDONTWRITEBYTECODE: bytecode was pre-compiled above; suppress runtime
# write attempts (which would fail on the read-only rootfs).
# PYTHONUNBUFFERED: flush stdout/stderr immediately so `docker logs` is current.
ENV HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8083

# Use 127.0.0.1 rather than localhost to avoid IPv6 loopback (::1) resolution
# on dual-stack hosts where the app binds IPv4 only. The inner timeout=3 gives
# Python a clean exit window; the outer --timeout=5s is the hard Docker kill.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8083/healthz', timeout=3)"

CMD ["python", "aclinspector.py", "web", "--port", "8083", "--addr", "0.0.0.0"]

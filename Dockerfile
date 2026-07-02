# Stage 1: Build dependencies
# python:3.12-slim, digest-pinned (see SECURITY.md F-9). Renovate/Dependabot bump
# this by re-resolving the tag, not by hand-editing the hash.
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python requirements to user site-packages
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf AS runner

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV PATH=/home/appuser/.local/bin:$PATH

WORKDIR /app

# Create a non-privileged user and directory structure
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser && \
    mkdir -p /app/benchmarks && \
    chown -R appuser:appgroup /app

# Copy installed python dependencies from builder
COPY --from=builder --chown=appuser:appgroup /root/.local /home/appuser/.local

# Copy application files
COPY --chown=appuser:appgroup src/ ./src/
COPY --chown=appuser:appgroup benchmarks/ ./benchmarks/

# Expose port
EXPOSE 8000

# Switch to non-root user
USER appuser

# Healthcheck using Python's built-in urllib
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application using uvicorn in production mode (1 worker to respect local SLM concurrency semaphore and save RAM)
CMD ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

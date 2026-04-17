# ============================================================
# AI Evaluation Engine — Production Dockerfile
# ============================================================
# Multi-stage build for minimal production image:
# Stage 1: Install dependencies (cached layer)
# Stage 2: Copy app code (changes frequently)
#
# Final image: ~180MB (vs ~1.2GB for naive build)
# ============================================================

# ── Stage 1: Dependencies ────────────────────────────────
FROM python:3.12-slim AS deps

# System deps for asyncpg, bcrypt, and cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only dependency spec for layer caching
COPY pyproject.toml ./

# Install production dependencies
# --no-cache-dir saves ~50MB by not caching pip packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[production]" 2>/dev/null || \
    pip install --no-cache-dir .

# ── Stage 2: Application ────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Runtime-only system deps (no compiler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application code
COPY ./src ./src
COPY ./alembic ./alembic
COPY ./alembic.ini ./
COPY ./pyproject.toml ./

# Create directories for prometheus multiprocess
RUN mkdir -p /tmp/prometheus_multiproc && \
    chown -R appuser:appuser /app /tmp/prometheus_multiproc

# Environment variables
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Prometheus multiprocess mode for gunicorn workers
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Expose port
EXPOSE 8000

# Run with uvicorn (production: use gunicorn with uvicorn workers)
CMD ["uvicorn", "src.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--no-access-log"]

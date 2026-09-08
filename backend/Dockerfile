# ── Stage 1: Build dependencies ──────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .

# Install PyTorch CPU-only first (skip ~1.5GB of CUDA deps)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --timeout=300 --retries=3 \
    torch --extra-index-url https://download.pytorch.org/whl/cpu

# Install remaining deps (sentence-transformers will reuse the CPU torch)
RUN --mount=type=cache,target=/root/.cache/pip \
    PYTHONPATH=/install/lib/python3.12/site-packages \
    pip install --prefix=/install --timeout=300 --retries=3 -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# System deps for PyMuPDF and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Create non-root user and data dirs
RUN adduser --disabled-password --no-create-home appuser \
    && mkdir -p /data/uploads /data/faiss /data/models \
    && chown -R appuser:appuser /data /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

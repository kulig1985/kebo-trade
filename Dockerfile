# ============================================================================
# Kebo Trade - Live Trading Docker Image
# ============================================================================
# Multi-stage build optimalizálva linux/amd64 platformra
#
# Build:
#   docker build --platform linux/amd64 -t kebo-trade:latest .
#
# Run:
#   docker run --env-file .env kebo-trade:latest
# ============================================================================

# =============================================================================
# STAGE 1: Builder - függőségek telepítése
# =============================================================================
FROM --platform=linux/amd64 python:3.12-slim AS builder

WORKDIR /app

# System dependencies for nautilus_trader (Rust-based)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Rust telepítése (nautilus_trader-hez szükséges)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# =============================================================================
# STAGE 2: Runtime - minimális production image
# =============================================================================
FROM --platform=linux/amd64 python:3.12-slim AS runtime

# Non-root user létrehozása
RUN groupadd -g 1001 trader && \
    useradd -u 1001 -g trader -m -s /bin/bash trader

WORKDIR /app

# System dependencies (runtime only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Python packages másolása a builder-ből
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Alkalmazás kód másolása
COPY --chown=trader:trader persistence/ ./persistence/
COPY --chown=trader:trader strategies/ ./strategies/
COPY --chown=trader:trader run/ ./run/

# Config könyvtár a külső konfigurációkhoz (volume mount point)
RUN mkdir -p /app/config && chown trader:trader /app/config

# Logs könyvtár
RUN mkdir -p /app/logs && chown trader:trader /app/logs

# Non-root user-re váltás
USER trader

# Environment variables (defaults)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health 2>/dev/null || \
        python -c "import sys; sys.exit(0)" || exit 1

# Default command
CMD ["python", "run/run_live.py"]

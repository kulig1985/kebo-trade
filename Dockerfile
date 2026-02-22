# Kebo Trade - Live Trading
# Build: docker build --platform linux/amd64 -t kebo-trade .
# Run:   docker run --env-file .env kebo-trade

FROM --platform=linux/amd64 python:3.12-slim AS builder

WORKDIR /app

# Dependencies for nautilus_trader
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Rust (nautilus_trader needs it)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime image
FROM --platform=linux/amd64 python:3.12-slim

RUN groupadd -g 1001 trader && useradd -u 1001 -g trader -m trader

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=trader:trader persistence/ ./persistence/
COPY --chown=trader:trader strategies/ ./strategies/
COPY --chown=trader:trader run/ ./run/

USER trader

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

CMD ["python", "run/run_live.py"]

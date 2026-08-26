# ==============================================================================
# Stage 1: Build Dependencies
# ==============================================================================
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install build tools if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install packages to /install directory
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ==============================================================================
# Stage 2: Final Minimal Runtime Image
# ==============================================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Jakarta \
    PYTHONPATH=/app

# Install minimal runtime system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy pre-installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source files
COPY config.py main.py dashboard.py dashboard_assets.py mt5_safe.py entrypoint.sh ./
COPY src/ ./src/
COPY tele_bot/ ./tele_bot/

# Ensure data directory exists and sanitize entrypoint line endings
RUN mkdir -p /app/data && dos2unix /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Expose API & Dashboard server port
EXPOSE 8765

# Run entrypoint script (starts API server in background + trading bot in foreground)
CMD ["/app/entrypoint.sh"]

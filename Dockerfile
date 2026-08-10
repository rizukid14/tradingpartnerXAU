FROM python:3.12-slim

# Set timezone and unbuffered stdout
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Jakarta

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Ensure data directory exists and make entrypoint script executable
RUN mkdir -p /app/data && chmod +x /app/entrypoint.sh

# Expose API & Dashboard server port
EXPOSE 8765

# Run entrypoint script (starts API server in background + trading bot in foreground)
CMD ["/app/entrypoint.sh"]

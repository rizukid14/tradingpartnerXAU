FROM python:3.12-slim

# Set timezone and unbuffered stdout
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Jakarta \
    PYTHONPATH=/app

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

# Run Telegram AI Agent
CMD ["python", "tele_bot/telegram_ai_agent.py"]

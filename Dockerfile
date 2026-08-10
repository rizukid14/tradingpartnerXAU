FROM python:3.11-slim

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

# Ensure data directory exists
RUN mkdir -p /app/data

# Run main trading bot loop
CMD ["python", "main.py"]

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Jakarta \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY crypto_bot/controller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "crypto_bot/controller/main.py"]

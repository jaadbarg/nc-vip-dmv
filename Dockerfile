# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg \
    libnss3 libxss1 libasound2 libatk-bridge2.0-0 libatk1.0-0 \
    libcups2 libdrm2 libxkbcommon0 libdbus-1-3 libxcomposite1 libxrandr2 \
    libgbm1 libxdamage1 libgtk-3-0 libpango-1.0-0 libpangocairo-1.0-0 \
    ca-certificates fonts-liberation libxshmfence1 xvfb && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt && \
    python -m playwright install --with-deps chromium

COPY . .

# Default env
ENV NCVIP_CONFIG=/app/config.yaml \
    NCVIP_CHECKER=playwright \
    NCVIP_NO_NOTIFY=true \
    PORT=8000

EXPOSE 8000

# Use $PORT if provided by platform, otherwise default to 8000
CMD ["sh", "-c", "uvicorn nc_vip_dmv.web.server:app --host 0.0.0.0 --port ${PORT:-8000}"]

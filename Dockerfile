# Multimodal Studio — core app (CPU). For GPU image generation use Dockerfile.gpu.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    RELOAD=0 \
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers

WORKDIR /app

# FFmpeg for video merge; curl for healthchecks; libs Playwright needs on Debian.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install "loguru>=0.7.2" \
    && pip install -r requirements.txt \
    && python -c "import loguru, fastapi"

COPY app/ app/
COPY frontend/ frontend/
COPY run.py ./

RUN playwright install chromium \
    && mkdir -p /app/.playwright-browsers \
    && touch /app/.playwright-browsers/.chromium-installed

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -f "http://127.0.0.1:${PORT}/api/capabilities" || exit 1

ENTRYPOINT ["/entrypoint.sh"]

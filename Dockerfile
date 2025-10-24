FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# System deps for OCR/PDF and scientific libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libgl1 \
    libglib2.0-0 \
    curl \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first to leverage caching
COPY requirements.txt ./
RUN pip install --upgrade pip wheel && \
    pip install -r requirements.txt

# Copy application code
COPY app ./app
COPY MailbirdSettings.yml ./MailbirdSettings.yml
# Do not bake local .env into the image; Railway injects env at runtime

# Healthcheck (optional; Railway also has HTTP healthcheck)
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s CMD curl -fsS http://localhost:${PORT}/health || exit 1

# Run the API server
CMD ["sh", "-lc", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

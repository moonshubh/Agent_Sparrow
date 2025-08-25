# Multi-stage build for optimized Railway deployment
FROM python:3.10.14-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install requirements first (for better caching)
COPY requirements.txt .
# Use pip cache and install in parallel where possible
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir --prefer-binary -r requirements.txt

# Production stage
FROM python:3.10.14-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libgomp1 \
    curl \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default port (Railway will override with PORT env var)
ENV PORT=8000

# Use the PORT environment variable provided by Railway
EXPOSE ${PORT}

# Health check (using curl which is more reliable in containers)
# Increased start-period to 3 minutes to allow for model loading and service initialization
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
  CMD curl -f http://localhost:${PORT}/health || exit 1

# Start the application with detailed logging for Railway debugging
CMD ["sh", "-c", "echo 'Starting MB-Sparrow on port ${PORT}...' && echo 'Initializing services, this may take 1-2 minutes...' && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --log-level info"]
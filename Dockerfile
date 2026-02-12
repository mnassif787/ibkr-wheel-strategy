FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy project files
COPY . .

# Create directories with proper permissions
RUN mkdir -p staticfiles media data

# Create a non-root user first
RUN useradd -m -u 1000 django && \
    chown -R django:django /app

# Switch to django user for collectstatic
USER django

# Collect static files as django user
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run migrations and start gunicorn (Railway-compatible)
CMD python manage.py migrate && \
    python manage.py collectstatic --noinput && \
    gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 300 --access-logfile - --error-logfile - config.wsgi:application

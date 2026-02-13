#!/bin/sh
set -e

# Use Railway's PORT or default to 8000
PORT=${PORT:-8000}

echo "Starting on port $PORT..."

# Run migrations
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput

# Start gunicorn
exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 300 --access-logfile - --error-logfile - config.wsgi:application

#!/bin/bash
set -e

echo "================================================"
echo "Starting IBKR Wheel Strategy on Railway"
echo "================================================"

# Get PORT from Railway (defaults to 8080)
export PORT=${PORT:-8080}

# Update nginx to listen on Railway's port
sed -i "s/listen 8080/listen $PORT/g" /etc/nginx/sites-available/default

# Run Django migrations
echo "Running database migrations..."
cd /app
python3 manage.py migrate --noinput

# Create superuser if needed (only in development)
if [ "$DEBUG" = "True" ]; then
    echo "Creating superuser (if needed)..."
    python3 manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'admin@example.com', 'admin')" || true
fi

echo "================================================"
echo "Starting all services with Supervisor..."
echo "Django: http://0.0.0.0:$PORT"
echo "================================================"

# Debug: Check if IBC is installed
echo "Checking IB Gateway installation..."
if [ -d "/opt/ibgateway" ]; then
    echo "✓ IB Gateway directory exists"
    ls -la /opt/ibgateway/ | head -10
else
    echo "✗ IB Gateway directory NOT found"
fi

if [ -d "/opt/ibc" ]; then
    echo "✓ IBC directory exists"
    ls -la /opt/ibc/
else
    echo "✗ IBC directory NOT found"
fi

if [ -f "/opt/ibc/scripts/ibcstart.sh" ]; then
    echo "✓ IBC start script exists"
else
    echo "✗ IBC start script NOT found"
fi

# Start supervisord (manages all services)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf

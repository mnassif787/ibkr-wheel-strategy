#!/bin/bash
# Deployment script for Docker

echo "🚀 Starting IBKR Wheel Strategy Platform Deployment..."

# Stop existing containers
echo "📦 Stopping existing containers..."
docker-compose down

# Build new images
echo "🔨 Building Docker images..."
docker-compose build --no-cache

# Start services
echo "▶️  Starting services..."
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service status
echo "📊 Service Status:"
docker-compose ps

# Show logs
echo ""
echo "📝 Recent logs:"
docker-compose logs --tail=20

echo ""
echo "✅ Deployment complete!"
echo "🌐 Access your platform at: http://localhost:8000"
echo "🔍 IB Gateway VNC at: vnc://localhost:5900 (password: ibkrvnc)"
echo ""
echo "📋 Useful commands:"
echo "  View logs: docker-compose logs -f"
echo "  Restart: docker-compose restart"
echo "  Stop: docker-compose down"
echo "  Shell access: docker-compose exec web bash"

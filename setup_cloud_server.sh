#!/bin/bash
# ============================================================
#  IBKR Wheel Strategy - Oracle Cloud Free Tier Setup Script
#  Run this on your Oracle Cloud VM (Ubuntu/Oracle Linux)
# ============================================================

set -e

echo "============================================"
echo " IBKR Wheel Strategy - Cloud Server Setup"
echo "============================================"
echo ""

# Update system
echo "[1/6] Updating system packages..."
sudo apt-get update -y && sudo apt-get upgrade -y

# Install Docker
echo "[2/6] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    echo "  -> Docker installed. You may need to log out and back in for group changes."
else
    echo "  -> Docker already installed."
fi

# Install Docker Compose
echo "[3/6] Installing Docker Compose..."
if ! command -v docker compose &> /dev/null; then
    sudo apt-get install -y docker-compose-plugin
else
    echo "  -> Docker Compose already installed."
fi

# Open firewall ports
echo "[4/6] Configuring firewall..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 5900 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

# Clone or update repository
echo "[5/6] Setting up project..."
if [ -d "ibkr-wheel-django" ]; then
    echo "  -> Project folder exists, pulling latest..."
    cd ibkr-wheel-django
    git pull
else
    echo "  -> Enter your GitHub repo URL (or press Enter to skip if files are already here):"
    read -r REPO_URL
    if [ -n "$REPO_URL" ]; then
        git clone "$REPO_URL" ibkr-wheel-django
        cd ibkr-wheel-django
    fi
fi

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "[!] Creating .env file - PLEASE EDIT WITH YOUR CREDENTIALS"
    cat > .env << 'ENVFILE'
# Django Settings
SECRET_KEY=CHANGE-ME-use-a-random-string-here
DEBUG=False
ALLOWED_HOSTS=*

# IBKR Credentials (REQUIRED!)
IBKR_USERNAME=your-ibkr-username
IBKR_PASSWORD=your-ibkr-password
IBKR_TRADING_MODE=paper

# Docker networking
IBKR_HOST=ib-gateway
IBKR_PORT=4002
IBKR_CLIENT_ID=1

# VNC
VNC_PASSWORD=ibkrvnc

# Site
SITE_NAME=IBKR Wheel Strategy
SITE_URL=http://YOUR_SERVER_IP:8000
ENVFILE
    echo ""
    echo "  !! IMPORTANT: Edit .env with your IBKR credentials:"
    echo "     nano .env"
    echo ""
fi

# Start Docker
echo "[6/6] Starting Docker containers..."
sudo docker compose up -d --build

echo ""
echo "============================================"
echo " SETUP COMPLETE!"
echo "============================================"
echo ""
echo " Waiting for containers to start..."
sleep 15
sudo docker compose ps
echo ""
echo " ACCESS YOUR PLATFORM:"
echo " ──────────────────────────────────────"
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")
echo "   Web Dashboard:  http://${PUBLIC_IP}:8000"
echo "   VNC (Gateway):  vnc://${PUBLIC_IP}:5900"
echo ""
echo " USEFUL COMMANDS:"
echo "   View logs:      sudo docker compose logs -f"
echo "   Restart:        sudo docker compose restart"
echo "   Stop:           sudo docker compose down"
echo "   Update:         git pull && sudo docker compose up -d --build"
echo ""
echo " SECURITY TIP: Set up a free Cloudflare tunnel"
echo "   for HTTPS without opening ports."
echo "============================================"

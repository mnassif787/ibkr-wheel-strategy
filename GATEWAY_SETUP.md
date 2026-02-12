# IB Gateway Docker Integration Guide

This guide explains how to use the integrated IB Gateway Docker container in your IBKR Wheel Strategy platform.

## Overview

The platform now includes a fully integrated IB Gateway running as a Docker container, eliminating the need to manually start and manage the Gateway application.

## Features

✅ **Automatic Startup**: IB Gateway starts automatically with `docker-compose up`  
✅ **No Manual Configuration**: Gateway is pre-configured for API access  
✅ **VNC Access**: View the Gateway UI remotely via VNC on port 5900  
✅ **Network Isolation**: Secure containerized environment  
✅ **Health Monitoring**: Built-in health checks and connection status  
✅ **Web Control Panel**: Manage connections directly from the Django interface  

## Quick Setup

### 1. Configure Environment Variables

Update your `.env` file with your IBKR credentials:

```bash
# IB Gateway Docker Configuration
IBKR_USERNAME=your-ibkr-username
IBKR_PASSWORD=your-ibkr-password
IBKR_TRADING_MODE=paper  # or 'live' for live trading
VNC_PASSWORD=ibkrvnc     # Password for VNC access

# IBKR Connection Settings (for container networking)
IBKR_HOST=ib-gateway
IBKR_PORT=4002  # 4002 for paper, 4001 for live
```

### 2. Start the Services

```bash
docker-compose up -d
```

This will start both:
- Your Django web application (port 8000)
- IB Gateway container (ports 4001, 4002, 5900)

### 3. Access the Gateway Control Panel

Open your browser and navigate to:
- **Web Interface**: http://localhost:8000/ibkr/gateway/
- **Dashboard Link**: Click "🔌 Gateway" in the navigation menu

### 4. Connect to IB Gateway

From the Gateway Control Panel:
1. Click the **"Connect"** button
2. Wait for connection confirmation
3. Monitor the connection status (auto-refreshes every 10 seconds)

## VNC Access (Optional)

To view the actual IB Gateway UI:

1. Install a VNC client (TigerVNC, RealVNC, etc.)
2. Connect to: `localhost:5900`
3. Enter the VNC password (default: `ibkrvnc`)
4. You'll see the IB Gateway interface

## Port Configuration

| Service | Port | Purpose |
|---------|------|---------|
| Web App | 8000 | Django application |
| IB Gateway Live | 4001 | Live trading API connection |
| IB Gateway Paper | 4002 | Paper trading API connection |
| VNC Server | 5900 | Remote desktop access to Gateway |

## Trading Modes

### Paper Trading (Default)
```bash
IBKR_TRADING_MODE=paper
IBKR_PORT=4002
```

### Live Trading
```bash
IBKR_TRADING_MODE=live
IBKR_PORT=4001
```

**⚠️ Warning**: Always test with paper trading before switching to live trading!

## Container Management

### View Logs
```bash
# Gateway logs
docker-compose logs ib-gateway

# Web app logs
docker-compose logs web

# Follow logs in real-time
docker-compose logs -f
```

### Restart Gateway
```bash
docker-compose restart ib-gateway
```

### Stop All Services
```bash
docker-compose down
```

### Full Cleanup
```bash
docker-compose down -v  # Removes volumes too
```

## Troubleshooting

### Connection Failed

**Problem**: "Failed to connect to IB Gateway"

**Solutions**:
1. Verify the Gateway container is running:
   ```bash
   docker-compose ps
   ```

2. Check Gateway health:
   ```bash
   docker-compose logs ib-gateway
   ```

3. Verify credentials in `.env` file

4. Ensure correct port (4002 for paper, 4001 for live)

### Container Won't Start

**Problem**: Gateway container exits immediately

**Solutions**:
1. Check if credentials are correct
2. Verify your IBKR account is set up for API access
3. Review container logs for specific errors:
   ```bash
   docker-compose logs ib-gateway
   ```

### VNC Connection Issues

**Problem**: Can't connect via VNC

**Solutions**:
1. Verify port 5900 is not blocked by firewall
2. Check VNC password matches your `.env` configuration
3. Ensure Gateway container is running

### Network Errors

**Problem**: Django can't reach Gateway

**Solutions**:
1. Verify both containers are on the same network:
   ```bash
   docker network ls
   docker network inspect ibkr-wheel-django_ibkr-network
   ```

2. Check `IBKR_HOST` is set to `ib-gateway` (container name) not `127.0.0.1`

## Architecture

```
┌─────────────────────────────────────────────┐
│              Docker Host                     │
│                                              │
│  ┌────────────────┐    ┌─────────────────┐ │
│  │  Django Web    │───▶│  IB Gateway     │ │
│  │  Container     │    │  Container      │ │
│  │  Port: 8000    │    │  Ports:         │ │
│  └────────────────┘    │  - 4001 (Live)  │ │
│          │              │  - 4002 (Paper) │ │
│          │              │  - 5900 (VNC)   │ │
│          │              └─────────────────┘ │
│          │                       │          │
│          ▼                       ▼          │
│    ibkr-network (Docker Bridge)            │
└─────────────────────────────────────────────┘
           │                       │
           ▼                       ▼
    Your Browser              IBKR Servers
```

## Security Considerations

1. **Never commit `.env` file**: Contains sensitive credentials
2. **Use strong VNC password**: Change from default
3. **Network isolation**: Containers communicate via private Docker network
4. **API read-only mode**: Consider enabling in Gateway settings for safety
5. **Paper trading first**: Always test thoroughly before live trading

## Advanced Configuration

### Custom Gateway Image

If you need a specific version or custom configuration:

```yaml
ib-gateway:
  image: ghcr.io/unusualalpha/ib-gateway-docker:1012  # Specific version
  # ... rest of configuration
```

### Resource Limits

Add resource constraints to prevent excessive usage:

```yaml
ib-gateway:
  # ... existing config
  deploy:
    resources:
      limits:
        cpus: '1.0'
        memory: 2G
      reservations:
        cpus: '0.5'
        memory: 1G
```

### Persistent Sessions

To keep Gateway sessions across container restarts:

```yaml
ib-gateway:
  # ... existing config
  volumes:
    - ib-gateway-data:/root/Jts
```

And add to volumes section:
```yaml
volumes:
  ib-gateway-data:
```

## Support Resources

- **IB Gateway Docker**: https://github.com/UnusualAlpha/ib-gateway-docker
- **ib_insync Documentation**: https://ib-insync.readthedocs.io/
- **Interactive Brokers API**: https://www.interactivebrokers.com/en/trading/ib-api.php

## Next Steps

1. ✅ Configure your `.env` file with IBKR credentials
2. ✅ Start services with `docker-compose up -d`
3. ✅ Access Gateway Control Panel
4. ✅ Click "Connect" to establish connection
5. ✅ Start trading with the Wheel Strategy!

---

**Need Help?** Check the troubleshooting section above or review the container logs for detailed error messages.

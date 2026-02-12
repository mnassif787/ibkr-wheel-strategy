# IBKR Wheel Strategy Platform - Docker Deployment

## Quick Start

### 1. Prerequisites
- Docker Desktop installed and running
- `.env` file configured with your IBKR credentials

### 2. Deploy Locally

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### 3. Access the Platform
- **Web Dashboard**: http://localhost:8000
- **IB Gateway VNC**: vnc://localhost:5900 (password: `ibkrvnc`)
- **Admin Panel**: http://localhost:8000/admin

## Remote Deployment Options

### Option 1: Deploy to Cloud (Recommended)

#### AWS EC2 / DigitalOcean / Linode
```bash
# 1. SSH into your server
ssh user@your-server-ip

# 2. Clone repository
git clone <your-repo-url>
cd ibkr-wheel-django

# 3. Configure environment
cp .env.example .env
nano .env  # Add your credentials

# 4. Deploy
docker-compose up -d
```

#### Configure Firewall
```bash
# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp  # Django app
sudo ufw enable
```

### Option 2: Deploy with Nginx Reverse Proxy

Create `nginx.conf`:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static/ {
        alias /app/staticfiles/;
    }
}
```

### Option 3: Deploy with HTTPS (Let's Encrypt)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo certbot renew --dry-run
```

## Environment Variables

Required in `.env`:
```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=your-domain.com,your-ip
CSRF_ORIGINS=https://your-domain.com

# IBKR
IBKR_USERNAME=your-username
IBKR_PASSWORD=your-password
IBKR_TRADING_MODE=paper
IBKR_HOST=ib-gateway
IBKR_PORT=4002

# VNC
VNC_PASSWORD=your-vnc-password
```

## Docker Commands

### Management
```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart specific service
docker-compose restart web

# View logs
docker-compose logs -f web
docker-compose logs -f ib-gateway

# Execute command in container
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

### Maintenance
```bash
# Backup database
docker-compose exec web python manage.py dumpdata > backup.json

# Restore database
docker-compose exec -T web python manage.py loaddata < backup.json

# Update code and rebuild
git pull
docker-compose build
docker-compose up -d
```

## Scaling

### Increase Workers
Edit `docker-compose.yml`:
```yaml
command: >
  sh -c "gunicorn --bind 0.0.0.0:8000 --workers 8 config.wsgi:application"
```

### Add Load Balancer
Use nginx to distribute traffic across multiple Django instances.

## Monitoring

### Health Checks
```bash
# Check web service
curl http://localhost:8000/

# Check IB Gateway connection
docker-compose logs ib-gateway | grep "connected"
```

### Resource Usage
```bash
# Container stats
docker stats

# Disk usage
docker system df
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs web

# Check if ports are available
netstat -tulpn | grep :8000
```

### Database locked
```bash
# Restart with fresh database
docker-compose down -v
docker-compose up -d
```

### IB Gateway connection issues
```bash
# Check Gateway logs
docker-compose logs ib-gateway

# Restart Gateway
docker-compose restart ib-gateway
```

## Security Recommendations

1. **Change default passwords** in `.env`
2. **Enable firewall** on server
3. **Use HTTPS** in production
4. **Regular backups** of database
5. **Keep Docker images updated**
6. **Monitor logs** for suspicious activity

## Cost Estimation

### Cloud Hosting (Monthly)
- **DigitalOcean Basic Droplet**: $6/month (1GB RAM)
- **AWS EC2 t3.micro**: ~$10/month
- **Linode Nanode**: $5/month

### Recommended Specs
- **Minimum**: 1GB RAM, 1 CPU, 25GB SSD
- **Recommended**: 2GB RAM, 2 CPU, 50GB SSD
- **Production**: 4GB RAM, 2 CPU, 80GB SSD

## Support

For issues:
1. Check logs: `docker-compose logs -f`
2. Verify `.env` configuration
3. Ensure Docker is running
4. Check firewall rules

# Deploy to Render.com (FREE)

## Quick Deploy Steps

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/ibkr-wheel-django.git
git push -u origin main
```

### 2. Deploy on Render
1. Go to [render.com](https://render.com) and sign up (free)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Render will auto-detect `render.yaml`
5. Add environment variables:
   - `ALLOWED_HOSTS`: your-app-name.onrender.com
   - `IBKR_USERNAME`: your-username
   - `IBKR_PASSWORD`: your-password
6. Click **"Create Web Service"**

### 3. Access Online
Your app will be live at: `https://your-app-name.onrender.com`

## ⚠️ Important Note: IB Gateway

**Problem**: Render.com (and most free hosting) only supports HTTP/HTTPS ports, not IB Gateway's custom ports.

**Solution**: Hybrid setup:
- **Web App**: Hosted on Render (free, online access)
- **IB Gateway**: Runs on your local PC
- **Connection**: Web app connects to your local Gateway via ngrok tunnel

### Hybrid Setup:

1. **Start IB Gateway locally:**
```bash
docker-compose up ib-gateway
```

2. **Expose Gateway with ngrok:**
```bash
ngrok tcp 7496
```
Copy the forwarded address: `tcp://0.tcp.ngrok.io:12345`

3. **Configure Render environment:**
```
IBKR_HOST=0.tcp.ngrok.io
IBKR_PORT=12345
```

4. **Deploy to Render** - Your web interface is now online, connecting to your local Gateway!

## Free Tier Limits
- 750 hours/month (enough for full-time use)
- Sleeps after 15 min of inactivity (first request takes ~30s to wake)
- 512 MB RAM
- No credit card required!

## Alternative: Keep Everything Local
If you want both web + Gateway together, use:
- **Railway.app**: $5 free credit/month
- **Fly.io**: Free tier with limited hours
- **DigitalOcean**: $6/month (most reliable)

# Deploy Using Ngrok (100% FREE - No Cloud Needed)

## What is Ngrok?
Exposes your local machine to the internet with a public URL - perfect for personal use!

## Quick Setup

### 1. Install Ngrok
1. Go to [ngrok.com](https://ngrok.com) and sign up (free)
2. Download ngrok for Windows
3. Extract to a folder
4. Get your auth token from dashboard

### 2. Configure Ngrok
```powershell
# Authenticate
.\ngrok config add-authtoken YOUR_AUTH_TOKEN
```

### 3. Start Your Platform Locally
```powershell
# Start everything
docker-compose up -d

# Or without Docker
python manage.py runserver
```

### 4. Expose to Internet
```powershell
# Expose port 8000
.\ngrok http 8000
```

You'll get a public URL like:
```
https://abc123.ngrok.io → http://localhost:8000
```

### 5. Access from Anywhere!
Share the ngrok URL - accessible from any device worldwide!

## Free Tier Limits
✅ Unlimited usage
✅ HTTPS included
✅ 1 concurrent tunnel
⚠️ URL changes each restart (upgrade to $8/mo for static domain)
⚠️ Your PC must stay on

## Keep Tunnel Running
Create `start_ngrok.bat`:
```batch
@echo off
echo Starting IBKR Platform...
cd /d "%~dp0"
docker-compose up -d
echo.
echo Starting ngrok tunnel...
ngrok http 8000
```

Double-click to start everything!

## Advantages:
✅ 100% FREE forever
✅ No cloud hosting needed
✅ Full control over data
✅ IB Gateway works perfectly
✅ No monthly costs

## Disadvantages:
⚠️ Your PC must be on to access
⚠️ URL changes on restart (unless paid plan)
⚠️ Dependent on your internet connection

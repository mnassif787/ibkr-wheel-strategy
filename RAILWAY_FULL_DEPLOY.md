# Railway Deployment Guide - Full Setup (Web + IB Gateway)

This guide will help you deploy both the Django web app AND IB Gateway to Railway.

## Prerequisites

- GitHub account
- Railway account (sign up at https://railway.app with GitHub)
- Your IBKR paper trading credentials

## Step 1: Push Code to GitHub

```powershell
# Navigate to your project
cd "c:\Nassif\AI\Wheel Strategy\Wheel Strategy\ibkr-wheel-django"

# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Deploy to Railway"

# Create a new repository on GitHub, then add it:
git remote add origin https://github.com/YOUR_USERNAME/ibkr-wheel-django.git

# Push to GitHub
git branch -M main
git push -u origin main
```

## Step 2: Deploy Web App to Railway

1. Go to **https://railway.app**
2. Click **"Login"** → Sign in with GitHub
3. Click **"New Project"**
4. Click **"Deploy from GitHub repo"**
5. Select your `ibkr-wheel-django` repository
6. Railway will auto-detect your `Dockerfile` and start building

## Step 3: Add Environment Variables for Web App

Click on your service → **"Variables"** tab → Add these:

```env
SECRET_KEY=your-random-secret-key-min-50-chars-12345678901234567890
DEBUG=False
ALLOWED_HOSTS=*.railway.app,*.up.railway.app
CSRF_TRUSTED_ORIGINS=https://*.railway.app,https://*.up.railway.app

# Basic Auth (password protection)
BASIC_AUTH_USER=admin
BASIC_AUTH_PASS=wheel2026

# Telegram
TELEGRAM_BOT_TOKEN=8359531192:AAHPW4Kw4lmtwVZHsKClYtUPlB7KEgTTOBI
TELEGRAM_CHAT_ID=352793143

# IBKR Connection (will connect to IB Gateway service)
IBKR_HOST=ib-gateway.railway.internal
IBKR_PORT=8888
IBKR_CLIENT_ID=1
IBKR_PAPER_TRADING=True
IBKR_TRADING_MODE=paper
```

## Step 4: Deploy IB Gateway as a Second Service

Railway supports multi-container deployments. Add IB Gateway:

1. In your Railway project, click **"+ New"**
2. Select **"Docker Image"**
3. Enter image: `ghcr.io/extrange/ibkr:stable`
4. Click **"Deploy"**

### Configure IB Gateway Service:

Go to the IB Gateway service → **"Variables"** tab:

```env
IBC_TradingMode=paper
GATEWAY_OR_TWS=gateway
TWOFA_TIMEOUT_ACTION=restart
IBC_AcceptIncomingConnectionAction=accept
IBC_ReadOnlyApi=no
IBC_ExistingSessionDetectedAction=primary
```

### Expose Ports:

Still in IB Gateway service:
1. Go to **"Settings"** → **"Networking"**
2. Click **"Add Public Port"**
3. Add port `6080` (for VNC web access to log in)
4. Add port `8888` (for API communication)

## Step 5: Connect the Services

We need the web app to talk to IB Gateway:

### Option A: Using Railway Private Networking (Recommended)

Railway provides internal DNS. Update your web app's `IBKR_HOST` variable:

```env
IBKR_HOST=<ib-gateway-service-name>.railway.internal
```

The service name can be found in the IB Gateway service settings.

### Option B: Using Public URL

After exposing port 8888, Railway gives you a public URL. Use that in the web app's `IBKR_HOST`.

## Step 6: Log into IB Gateway

1. Find the public URL for port `6080` of your IB Gateway service (e.g., `https://ib-gateway-production.up.railway.app:6080`)
2. Open it in your browser
3. Log in with your IBKR paper trading credentials
4. Complete 2FA if prompted

## Step 7: Generate Domain for Web App

1. Go to your web service → **"Settings"** → **"Public Networking"**
2. Click **"Generate Domain"**
3. You'll get a URL like: `https://ibkr-wheel-django-production.up.railway.app`

## Step 8: Access Your Platform

Open the Railway URL in any browser (phone, laptop, etc.).

You'll be prompted for:
- **Username:** `admin`
- **Password:** `wheel2026`

## Important Notes

### Cost Estimate

Railway gives you **$5 free credit per month**. Here's approximate usage:

- **Web App:** ~$3-4/month (running 24/7)
- **IB Gateway:** ~$2-3/month (running 24/7)

**Total:** Roughly fits in the $5 free tier for light use. If you exceed it, you'll need to add a payment method.

### Keeping IB Gateway Logged In

IB Gateway may disconnect after inactivity or require re-login for 2FA. You'll need to:
- Log in via the VNC URL (port 6080) when needed
- Set up auto-restart if connection drops

### Persistence

Railway containers restart occasionally. Your SQLite database will persist as long as you use Railway volumes (which are automatic for the web service).

## Troubleshooting

### Web app can't connect to IB Gateway

- Check that both services are running
- Verify `IBKR_HOST` points to the correct internal/external address
- Check IB Gateway logs for connection rejections

### IB Gateway disconnects

- Log in via VNC (port 6080) to check status
- Verify your IBKR credentials are correct
- Check if 2FA is required

### Database resets on redeploy

- Railway should preserve the database in volumes
- For production, consider using Railway's PostgreSQL add-on instead of SQLite

## Alternative: Keep IB Gateway Local + Web on Railway

If Railway's IB Gateway setup is problematic:

1. Deploy ONLY the web app to Railway
2. Keep IB Gateway running on your PC (using Docker)
3. Expose your local IB Gateway using ngrok: `ngrok tcp 8888`
4. Set Railway's `IBKR_HOST` and `IBKR_PORT` to the ngrok address

This hybrid approach is simpler and more reliable.

---

**Questions?** Check Railway docs: https://docs.railway.app

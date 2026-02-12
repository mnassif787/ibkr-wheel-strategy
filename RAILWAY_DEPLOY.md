# Deploy to Railway.app (FREE $5 credit/month)

## Quick Deploy

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Trading platform"
git push
```

### 2. Deploy on Railway
1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub (free $5 credit/month)
3. Click **"New Project"** → **"Deploy from GitHub repo"**
4. Select your repository
5. Railway auto-detects Docker and deploys!

### 3. Add Environment Variables
In Railway dashboard:
```
DJANGO_SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=your-app.railway.app
IBKR_USERNAME=your-username
IBKR_PASSWORD=your-password
IBKR_TRADING_MODE=paper
IBKR_HOST=ib-gateway
IBKR_PORT=4002
```

### 4. Generate Domain
- Railway provides free subdomain: `your-app.railway.app`
- Supports both web + IB Gateway in one container

### Advantages:
✅ Full Docker support (both Django + IB Gateway)
✅ All ports supported (7496, 4001, 4002, 5900)
✅ $5 free credit = ~500 hours/month
✅ No sleep/wake delays
✅ Better performance than Render free tier

## Cost: $0 with $5 monthly credit (plenty for personal use)

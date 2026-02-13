# Railway Deployment Checklist

## Pre-Deployment Configuration

### 1. Railway Environment Variables
Set these in Railway Dashboard → Your Project → Variables:

**Required:**
- `SECRET_KEY` - Generate a new secret key (use `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- `DEBUG=False` - Must be False for production
- `ALLOWED_HOSTS=.railway.app,.up.railway.app` - Django will automatically add these for non-DEBUG

**Optional:**
- `DATABASE_URL` - Only if using PostgreSQL (Railway auto-provides this)
- Email settings if you want alert notifications

### 2. Files Created for Railway Deployment

**Docker Configuration:**
- `Dockerfile.railway` - Multi-service container (Django + IB Gateway + VNC)
- `railway.json` - Railway build configuration

**Service Configuration:**
- `railway/supervisord.conf` - Process manager for 6 services
- `railway/nginx.conf` - Reverse proxy (Django + VNC)
- `railway/ibc-config.ini` - IB Gateway configuration (manual login)
- `railway/start-ibgateway.sh` - IB Gateway startup script
- `railway/start-all.sh` - Main entrypoint script

**Expected Directory Structure in Container:**
```
/app/                          # Django application
/opt/ibgateway/               # IB Gateway installation
    VERSION.txt               # Detected version (e.g., 10.43)
    10.43/                    # Version-specific folder
        jars/                 # Gateway JAR files
        data/                 # Gateway data
        ibgateway.vmoptions   # JVM options
/opt/ibc/                     # IBC (Interactive Brokers Controller)
    scripts/                  # IBC scripts
    config.ini                # IBC configuration
    start-ibgateway.sh        # Startup wrapper
/opt/noVNC/                   # Web-based VNC client
```

### 3. Service Architecture

**Supervisor manages 6 services (in priority order):**
1. **Xvfb** (priority 100) - Virtual X11 display on :1
2. **x11vnc** (priority 200) - VNC server on port 5900
3. **noVNC** (priority 300) - Web VNC client on port 6080
4. **ibgateway** (priority 400) - IB Gateway with IBC, waits 30s before marking as running
5. **django** (priority 500) - Gunicorn on port 8000
6. **nginx** (priority 600) - Reverse proxy on Railway's PORT (dynamic)

**Port Mapping:**
- Railway PORT (dynamic, usually 8080) → nginx
  - nginx → Django (port 8000) for `/`
  - nginx → noVNC (port 6080) for `/vnc/`
  - IB Gateway API on port 4001 (internal only, not exposed)

### 4. Deployment Flow

1. **Push to GitHub** → Railway auto-detects changes
2. **Build Phase** (~5 minutes):
   - Uses `Dockerfile.railway`
   - Downloads IB Gateway (~1GB)
   - Detects version and restructures files
   - Verifies jars folder exists
3. **Deploy Phase**:
   - Runs `start-all.sh`
   - Updates nginx PORT
   - Runs Django migrations
   - Starts supervisord
4. **Startup Sequence**:
   - Xvfb starts (virtual display)
   - x11vnc connects to display
   - noVNC provides web interface
   - IB Gateway starts (shows login screen in VNC)
   - Django connects to IB Gateway API (after manual login)
   - Nginx routes traffic

### 5. Verification Steps

**After Deployment:**
1. Check Railway logs for:
   ```
   ✓ IB Gateway installation verified
   Contents of jars folder: [list of JARs]
   ```

2. Verify all services running:
   ```
   INFO success: xvfb entered RUNNING state
   INFO success: x11vnc entered RUNNING state
   INFO success: novnc entered RUNNING state
   INFO success: ibgateway entered RUNNING state
   INFO success: django entered RUNNING state
   INFO success: nginx entered RUNNING state
   ```

3. Access Django: `https://your-app.railway.app/`
   - Should load without DisallowedHost error

4. Access VNC: `https://your-app.railway.app/vnc/`
   - Click "Connect"
   - Should see IB Gateway login window

### 6. Manual Login to IBKR

1. Go to `/vnc/` endpoint
2. Click "Connect" in noVNC interface
3. You'll see IB Gateway window
4. Enter your IBKR credentials:
   - Username
   - Password
   - Select "Paper Trading" account
5. Complete 2FA if prompted (5-minute timeout)
6. Gateway will show "Connected" status
7. Django app can now communicate with IB Gateway API

### 7. Common Issues & Solutions

**Issue: "can't find jars folder"**
- Cause: Directory structure mismatch
- Solution: Already fixed - creates `/opt/ibgateway/10.43/jars/`

**Issue: "ibgateway entered FATAL state"**
- Check logs for specific error
- Verify Java is installed: `java -version`
- Verify VERSION.txt exists and has correct version

**Issue: VNC shows black screen**
- Xvfb might have failed - check logs
- DISPLAY variable might be missing - check supervisord.conf

**Issue: Django can't connect to IB Gateway**
- Make sure you've logged in manually via VNC first
- Check IBKR_PORT is set to 4001 (Gateway port, not TWS 7497)
- Verify Gateway shows "Connected" status in VNC

**Issue: DisallowedHost error**
- Set DEBUG=False in Railway
- Or add your specific domain to ALLOWED_HOSTS

### 8. Production Considerations

**Security:**
- ✅ SECRET_KEY is environment variable
- ✅ DEBUG=False in production
- ✅ ALLOWED_HOSTS properly configured
- ⚠️ VNC has no password (nopw flag) - only accessible via your Railway domain
- ⚠️ Consider adding HTTP basic auth to `/vnc/` endpoint

**Performance:**
- Gunicorn runs 2 workers (adjust for Railway plan)
- 300s timeout for long-running requests
- Static files served by WhiteNoise (compressed)

**Monitoring:**
- All logs go to stdout/stderr (visible in Railway dashboard)
- Health check on port 8080 every 30s
- Supervisor auto-restarts failed services

**Persistence:**
- SQLite database in `/app/db.sqlite3` (ephemeral, resets on deploy)
- Consider adding Railway PostgreSQL for persistent data
- IB Gateway settings stored in container (manual login each redeploy)

### 9. Future Improvements

- [ ] Add PostgreSQL database for persistence
- [ ] Add HTTP basic auth for VNC endpoint
- [ ] Auto-create superuser on first deploy
- [ ] Add session persistence for IB Gateway (auto-relogin)
- [ ] Set up email alerts
- [ ] Add monitoring/alerting service
- [ ] Configure CSRF/CORS for API access
- [ ] Add backup/restore scripts

### 10. Maintenance

**Updating IB Gateway version:**
- Railway will auto-detect new version from desktop file
- No code changes needed unless API changes

**Redeploying:**
- Push to GitHub triggers automatic rebuild
- All services restart (will need to re-login to IBKR via VNC)

**Viewing Logs:**
- Railway dashboard → Deployments → View Logs
- Look for service-specific output (each service prints to stdout/stderr)

**Scaling:**
- Current setup: Single container with all services
- For horizontal scaling: Split into separate services (Django, IB Gateway)
- For now: Vertical scaling only (upgrade Railway plan)

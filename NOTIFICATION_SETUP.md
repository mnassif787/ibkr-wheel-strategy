# Setting up Notifications

## Telegram Setup (Recommended - Free & Reliable)

### 1. Create Your Telegram Bot
1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow prompts to name your bot (e.g., "My Trading Alerts Bot")
4. **Copy the token** you receive (looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Get Your Chat ID
1. Search for `@userinfobot` on Telegram
2. Start a chat with it
3. It will send you your **Chat ID** (looks like: `123456789`)

### 3. Configure Your Bot
1. Open `.env` file
2. Add your credentials:
```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

3. **Start a conversation with your bot**:
   - Find your bot in Telegram search
   - Click **START** or send `/start`
   - This allows the bot to send you messages

### 4. Test It
```bash
python manage.py shell
```
```python
from apps.ibkr.services.alert_service import AlertService
AlertService.send_telegram_message(
    '123456789',  # Your chat ID
    '🎯 Test alert from your trading bot!'
)
```

---

## Browser Push Notifications Setup

### 1. Generate VAPID Keys (One-time setup)
```bash
pip install py-vapid
vapid --gen
```

This generates two keys:
- **Public Key** (share with frontend)
- **Private Key** (keep secret)

### 2. Add to `.env`
```env
VAPID_PUBLIC_KEY=your-public-key-here
VAPID_PRIVATE_KEY=your-private-key-here
VAPID_SUBJECT=mailto:your-email@example.com
```

### 3. Install Required Package
```bash
pip install pywebpush
```

### 4. Browser Permission
When you visit the site, it will ask for notification permission. Click **Allow**.

---

## Alert Checking (Background Task)

### Option 1: Django Management Command (Simple)
Run every 5 minutes to check alerts:
```bash
python manage.py check_alerts
```

### Option 2: Windows Task Scheduler (Automated)
1. Open Task Scheduler
2. Create Task:
   - Trigger: Every 5 minutes
   - Action: Start program
   - Program: `C:\Nassif\AI\Wheel Strategy\Wheel Strategy\ibkr-wheel-django\venv\Scripts\python.exe`
   - Arguments: `manage.py check_alerts`
   - Start in: `C:\Nassif\AI\Wheel Strategy\Wheel Strategy\ibkr-wheel-django`

### Option 3: Django-Q (Advanced)
```bash
pip install django-q
```

Add to `settings.py`:
```python
INSTALLED_APPS += ['django_q']

Q_CLUSTER = {
    'name': 'DjangORM',
    'workers': 2,
    'timeout': 60,
    'retry': 120,
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',
}
```

Run scheduler:
```bash
python manage.py qcluster
```

---

## How Alerts Work

### 1. Set Alert
- Click **"50% Alert"** button on your position
- Or click **"Set Alert"** for custom price targets

### 2. Alert Stored
- Saved in database with your Telegram ID and/or browser subscription

### 3. Background Check (Every 5 mins)
- System checks current prices vs alert targets
- If target reached → triggers notification

### 4. You Get Notified
- 📱 **Telegram**: Instant message with details
- 🔔 **Browser**: Push notification (if browser open)

---

## Notification Examples

### 50% Profit Alert
```
🎯 50% Profit Target Reached!

SOFI $20.00 PUT
Entry: $0.3737/share
Current: $0.1868/share

💰 Profit: $18.69

Consider closing this position to lock in profits!
```

### Stock Price Alert
```
🔔 Price Alert Triggered!

SOFI reached $19.00
Alert was set for when price goes below $19.00
```

### Expiration Warning
```
⏰ Expiration Warning!

SOFI $20.00 PUT expires in 2 days (Feb 13)

Current price: $20.86
Assignment risk: LOW
```

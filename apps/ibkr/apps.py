import threading
import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class IbkrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ibkr'

    def ready(self):
        """Start the auto-trade background scheduler when Django boots."""
        import os
        # Only run in the main process (not the reloader child)
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_SETTINGS_MODULE'):
            pass  # dev-server reloader guard handled below
        # Avoid double-start in Django's autoreloader (which forks twice)
        if os.environ.get('RUN_MAIN', 'false') != 'true' and 'runserver' in os.sys.argv:
            return
        _start_auto_trade_scheduler()


def _start_auto_trade_scheduler():
    """Daemon thread: runs auto-trade once ~90s after startup, then every weekday at 09:35 ET."""
    import time
    from datetime import datetime

    def _loop():
        # Initial delay — give Django time to finish starting up
        time.sleep(90)
        logger.info('🤖 Auto-trade scheduler started')

        while True:
            try:
                _maybe_run_cycle()
            except Exception as e:
                logger.error(f'Auto-trade scheduler error: {e}')
            # Sleep 10 minutes between checks
            time.sleep(600)

    t = threading.Thread(target=_loop, name='auto-trade-scheduler', daemon=True)
    t.start()


def _maybe_run_cycle():
    """
    Run auto-trade cycle if:
      - It's a weekday
      - Current ET time is between 09:35 and 15:30
      - Auto-trade is enabled
      - It hasn't run yet today
    """
    from datetime import date, datetime
    import django

    try:
        from apps.ibkr.models import AutoTradeConfig
        config = AutoTradeConfig.get_config()
    except Exception:
        return  # DB not ready yet

    if not config.enabled:
        return

    # Market hours check (ET)
    try:
        import pytz
        et = pytz.timezone('America/New_York')
        now_et = datetime.now(et)
    except Exception:
        from datetime import timezone, timedelta
        now_et = datetime.now(timezone(timedelta(hours=-5)))

    if now_et.weekday() >= 5:  # Weekend
        return
    hour, minute = now_et.hour, now_et.minute
    if not (9 * 60 + 35 <= hour * 60 + minute <= 15 * 60 + 30):
        return

    # Don't run more than once per day
    today = date.today()
    if config.last_run and config.last_run.date() == today:
        return

    logger.info(f'⏰ Scheduler triggering auto-trade cycle at {now_et.strftime("%H:%M ET")}')
    from apps.ibkr.services.auto_trade_engine import run_auto_trade_cycle
    run_auto_trade_cycle(dry_run=False)

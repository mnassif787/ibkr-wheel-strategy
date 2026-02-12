"""
Alert Service - Check alerts and send notifications via Browser Push and Telegram
"""
import os
import requests
from django.utils import timezone
from ..models import Alert
import logging

logger = logging.getLogger(__name__)


class AlertService:
    """Manage alerts and notifications"""
    
    @staticmethod
    def check_all_alerts():
        """Check all active alerts and trigger notifications"""
        active_alerts = Alert.objects.filter(status='ACTIVE')
        triggered_count = 0
        
        for alert in active_alerts:
            try:
                alert.last_checked = timezone.now()
                alert.save(update_fields=['last_checked'])
                
                if alert.check_trigger():
                    alert.trigger()
                    triggered_count += 1
                    logger.info(f"Alert triggered: {alert}")
            except Exception as e:
                logger.error(f"Error checking alert {alert.id}: {e}")
        
        return triggered_count
    
    @staticmethod
    def send_telegram_message(chat_id, message):
        """Send message via Telegram bot"""
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        
        if not bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not configured")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Telegram message sent to {chat_id}")
                return True
            else:
                logger.error(f"Telegram API error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    @staticmethod
    def send_browser_push(subscription_info, message):
        """Send browser push notification using Web Push"""
        # Browser push requires web-push library
        # Will be implemented in the next step with proper setup
        logger.info(f"Browser push notification: {message}")
        return True
    
    @staticmethod
    def create_50_percent_alert(position, telegram_chat_id=None, push_subscription=None):
        """Create a 50% profit alert for a position"""
        from decimal import Decimal
        
        # Convert to Decimal for consistent math
        entry_premium = Decimal(str(position.entry_premium))
        target_premium = entry_premium * Decimal('0.5')
        
        message = (
            f"🎯 50% Profit Target Reached!\n\n"
            f"<b>{position.stock.ticker}</b> ${position.strike} {position.option_type}\n"
            f"Entry: ${float(entry_premium):.4f}/share\n"
            f"Current: ${float(target_premium):.4f}/share\n\n"
            f"💰 Profit: ${float((entry_premium - target_premium) * position.contracts * 100):.2f}\n\n"
            f"Consider closing this position to lock in profits!"
        )
        
        notification_method = 'BOTH'
        if telegram_chat_id and not push_subscription:
            notification_method = 'TELEGRAM'
        elif push_subscription and not telegram_chat_id:
            notification_method = 'BROWSER'
        
        alert = Alert.objects.create(
            alert_type='50_PERCENT_PROFIT',
            position=position,
            target_premium=target_premium,
            notification_method=notification_method,
            telegram_chat_id=telegram_chat_id or '',
            push_subscription=push_subscription,
            message=message,
            status='ACTIVE'
        )
        
        return alert
    
    @staticmethod
    def create_stock_price_alert(stock, target_price, trigger_above, telegram_chat_id=None, push_subscription=None):
        """Create a stock price alert"""
        direction = "above" if trigger_above else "below"
        message = (
            f"🔔 Price Alert Triggered!\n\n"
            f"<b>{stock.ticker}</b> reached ${target_price:.2f}\n"
            f"Alert was set for when price goes {direction} ${target_price:.2f}"
        )
        
        notification_method = 'BOTH'
        if telegram_chat_id and not push_subscription:
            notification_method = 'TELEGRAM'
        elif push_subscription and not telegram_chat_id:
            notification_method = 'BROWSER'
        
        alert = Alert.objects.create(
            alert_type='STOCK_PRICE',
            stock=stock,
            target_stock_price=target_price,
            trigger_above=trigger_above,
            notification_method=notification_method,
            telegram_chat_id=telegram_chat_id or '',
            push_subscription=push_subscription,
            message=message,
            status='ACTIVE'
        )
        
        return alert

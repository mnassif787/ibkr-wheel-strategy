"""
Management command to check all active alerts and trigger notifications
Run this periodically (every 5-15 minutes) via cron or Task Scheduler
"""
from django.core.management.base import BaseCommand
from apps.ibkr.services.alert_service import AlertService


class Command(BaseCommand):
    help = 'Check all active alerts and send notifications'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔔 Checking alerts...'))
        
        try:
            triggered_count = AlertService.check_all_alerts()
            
            if triggered_count > 0:
                self.stdout.write(self.style.SUCCESS(f'✅ {triggered_count} alert(s) triggered'))
            else:
                self.stdout.write('✓ No alerts triggered')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))

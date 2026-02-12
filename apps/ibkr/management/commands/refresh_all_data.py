"""
Management command to refresh all data (stocks, indicators, and options)
This is a convenience command that runs all necessary refresh commands in sequence.
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from django.core.cache import cache
import time


class Command(BaseCommand):
    help = 'Refresh all data: stocks, technical indicators, and options'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            help='Refresh specific ticker only',
        )
        parser.add_argument(
            '--skip-options',
            action='store_true',
            help='Skip options refresh (faster)',
        )
    
    def update_progress(self, step, total_steps, message, detail="", percentage=0):
        """Update progress in cache for real-time UI updates"""
        cache.set('refresh_progress', {
            'step': step,
            'total_steps': total_steps,
            'message': message,
            'detail': detail,
            'percentage': percentage,
            'timestamp': timezone.now().isoformat()
        }, timeout=3600)
    
    def handle(self, *args, **options):
        ticker = options.get('ticker')
        skip_options = options.get('skip_options', False)
        
        total_steps = 2 if skip_options else 3
        start_time = time.time()
        
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("🔄 IBKR Wheel Platform - Complete Data Refresh"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"⏰ Started: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("")
        
        # Step 1: Refresh stock data
        self.update_progress(1, total_steps, "Refreshing stock data...", 
                           "Fetching latest prices and market data", 15)
        self.stdout.write(self.style.WARNING("📊 [1/{}] Refreshing stock data...".format(total_steps)))
        self.stdout.write("-" * 60)
        try:
            self.update_progress(1, total_steps, "Fetching stock prices...", 
                               "Connecting to data source", 20)
            if ticker:
                call_command('refresh_stocks', ticker=ticker)
            else:
                call_command('refresh_stocks')
            self.stdout.write(self.style.SUCCESS("✓ Stock data refreshed"))
            self.update_progress(1, total_steps, "Stock data refreshed", "✓ Completed", 35)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error refreshing stocks: {e}"))
            self.update_progress(1, total_steps, "Error refreshing stocks", str(e), 0)
            cache.set('refresh_status', 'error', timeout=300)
            cache.set('refresh_error', str(e), timeout=300)
            return
        
        self.stdout.write("")
        
        # Step 2: Calculate technical indicators
        self.update_progress(2, total_steps, "Calculating technical indicators...",
                           "Computing RSI, EMA, Bollinger Bands, etc.", 40)
        self.stdout.write(self.style.WARNING("📈 [2/{}] Calculating technical indicators...".format(total_steps)))
        self.stdout.write("-" * 60)
        try:
            self.update_progress(2, total_steps, "Computing technical indicators...",
                               "Analyzing price patterns and trends", 50)
            if ticker:
                call_command('calculate_indicators', ticker=ticker)
            else:
                call_command('calculate_indicators')
            self.stdout.write(self.style.SUCCESS("✓ Technical indicators calculated"))
            self.update_progress(2, total_steps, "Technical indicators calculated", "✓ Completed", 70)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error calculating indicators: {e}"))
            self.update_progress(2, total_steps, "Error calculating indicators", str(e), 33)
            cache.set('refresh_status', 'error', timeout=300)
            cache.set('refresh_error', str(e), timeout=300)
            return
        
        self.stdout.write("")
        
        # Step 3: Sync options data (unless skipped)
        if not skip_options:
            self.update_progress(3, total_steps, "Syncing options data...",
                               "Fetching option chains (this may take a few minutes)", 75)
            self.stdout.write(self.style.WARNING("💼 [3/{}] Syncing options data...".format(total_steps)))
            self.stdout.write("-" * 60)
            try:
                self.update_progress(3, total_steps, "Downloading option chains...",
                                   "This is the longest step, please wait", 80)
                if ticker:
                    call_command('sync_yfinance_options', ticker=ticker)
                else:
                    call_command('sync_yfinance_options')
                self.stdout.write(self.style.SUCCESS("✓ Options data synced"))
                self.update_progress(3, total_steps, "Options data synced", "✓ Completed", 100)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ Error syncing options: {e}"))
                self.update_progress(3, total_steps, "Error syncing options", str(e), 66)
        else:
            self.stdout.write(self.style.WARNING("⏭️  [3/3] Skipping options refresh"))
            self.update_progress(2, 2, "Skipping options refresh", "✓ Completed", 100)
        
        # Summary
        elapsed_time = time.time() - start_time
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("✅ Data Refresh Complete!"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"⏱️  Total time: {elapsed_time:.2f} seconds")
        self.stdout.write(f"⏰ Finished: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("💡 Your data is now fresh and up-to-date!"))
        self.stdout.write("")

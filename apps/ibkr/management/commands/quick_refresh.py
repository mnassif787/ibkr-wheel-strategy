"""
Quick refresh command - only updates stale data for speed
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Q
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from apps.ibkr.models import Stock, StockIndicator
from apps.ibkr.services.stock_data_fetcher import StockDataFetcher
from apps.ibkr.services.technical_analysis import TechnicalAnalysisService
import time


class Command(BaseCommand):
    help = 'Quick refresh - only updates stale data (faster than full refresh)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--max-age',
            type=int,
            default=10,
            help='Maximum age in minutes before data is considered stale (default: 10)',
        )
        parser.add_argument(
            '--max-workers',
            type=int,
            default=5,
            help='Number of parallel workers (default: 5)',
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
    
    def refresh_single_stock(self, ticker):
        """Refresh a single stock and its indicators"""
        try:
            # Fetch stock data
            stock_data = StockDataFetcher.fetch_stock_data(ticker)
            
            if stock_data:
                # Update stock
                stock, created = Stock.objects.update_or_create(
                    ticker=ticker,
                    defaults={
                        'name': stock_data.get('name', ''),
                        'last_price': stock_data.get('last_price'),
                        'volume': stock_data.get('volume'),
                        'market_cap': stock_data.get('market_cap'),
                        'pe_ratio': stock_data.get('pe_ratio'),
                        'dividend_yield': stock_data.get('dividend_yield'),
                        'week_52_high': stock_data.get('week_52_high'),
                        'week_52_low': stock_data.get('week_52_low'),
                        'avg_volume': stock_data.get('avg_volume'),
                        'last_updated': timezone.now(),
                    }
                )
                
                # Calculate indicators
                indicators_data = TechnicalAnalysisService.calculate_all_indicators(ticker)
                
                if indicators_data:
                    StockIndicator.objects.update_or_create(
                        stock=stock,
                        defaults={
                            'rsi': indicators_data.get('rsi'),
                            'rsi_signal': indicators_data.get('rsi_signal', 'neutral'),
                            'ema_20': indicators_data.get('ema_20'),
                            'ema_50': indicators_data.get('ema_50'),
                            'bb_upper': indicators_data.get('bb_upper'),
                            'bb_middle': indicators_data.get('bb_middle'),
                            'bb_lower': indicators_data.get('bb_lower'),
                            'support_level': indicators_data.get('support_level'),
                            'resistance_level': indicators_data.get('resistance_level'),
                            'last_updated': timezone.now(),
                        }
                    )
                
                return {'success': True, 'ticker': ticker}
            else:
                return {'success': False, 'ticker': ticker, 'error': 'No data returned'}
                
        except Exception as e:
            return {'success': False, 'ticker': ticker, 'error': str(e)}
    
    def handle(self, *args, **options):
        max_age_minutes = options.get('max_age')
        max_workers = options.get('max_workers')
        
        start_time = time.time()
        cutoff_time = timezone.now() - timedelta(minutes=max_age_minutes)
        
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("⚡ IBKR Wheel - Quick Refresh"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"⏰ Started: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"📊 Refreshing data older than {max_age_minutes} minutes")
        self.stdout.write("")
        
        # Find stale stocks
        self.update_progress(1, 2, "Finding stale data...", "Checking last update times", 10)
        
        stale_stocks = Stock.objects.filter(
            Q(last_updated__isnull=True) | Q(last_updated__lt=cutoff_time)
        ).values_list('ticker', flat=True)
        
        stale_stocks_list = list(stale_stocks)
        
        if not stale_stocks_list:
            self.stdout.write(self.style.SUCCESS("✓ All data is fresh! No refresh needed."))
            self.update_progress(2, 2, "All data is fresh", "✓ No updates required", 100)
            cache.set('refresh_status', 'completed', timeout=300)
            return
        
        total_stocks = len(stale_stocks_list)
        self.stdout.write(f"🔄 Found {total_stocks} stocks with stale data")
        self.stdout.write("-" * 60)
        
        # Refresh stocks in parallel
        self.update_progress(1, 2, f"Refreshing {total_stocks} stocks...", 
                           f"Processing with {max_workers} parallel workers", 20)
        
        success_count = 0
        error_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_ticker = {
                executor.submit(self.refresh_single_stock, ticker): ticker 
                for ticker in stale_stocks_list
            }
            
            # Process completed tasks
            for i, future in enumerate(as_completed(future_to_ticker)):
                result = future.result()
                
                if result['success']:
                    success_count += 1
                    self.stdout.write(f"  ✓ {result['ticker']}")
                else:
                    error_count += 1
                    self.stdout.write(self.style.WARNING(
                        f"  ✗ {result['ticker']}: {result.get('error', 'Unknown error')}"
                    ))
                
                # Update progress
                progress = 20 + int((i + 1) / total_stocks * 75)
                self.update_progress(1, 2, f"Refreshing stocks... ({i+1}/{total_stocks})",
                                   f"✓ {success_count} success, ✗ {error_count} errors", 
                                   progress)
        
        elapsed_time = time.time() - start_time
        
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("✅ Quick Refresh Complete!"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"✓ Successfully refreshed: {success_count}")
        if error_count > 0:
            self.stdout.write(self.style.WARNING(f"✗ Errors: {error_count}"))
        self.stdout.write(f"⏱️  Time taken: {elapsed_time:.2f} seconds")
        self.stdout.write("")
        
        self.update_progress(2, 2, "Quick refresh complete", 
                           f"✓ {success_count} stocks updated in {elapsed_time:.1f}s", 100)
        
        cache.set('refresh_status', 'completed', timeout=300)

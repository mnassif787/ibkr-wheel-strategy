"""
Management command to calculate technical indicators for ALL stocks in database
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.ibkr.models import Stock, StockIndicator
from apps.ibkr.services.technical_analysis import TechnicalAnalysisService


class Command(BaseCommand):
    help = 'Calculate technical indicators (RSI, EMA, Bollinger Bands, Support/Resistance) for all stocks in database'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            help='Calculate indicators for a specific ticker'
        )
    
    def handle(self, *args, **options):
        ticker_arg = options.get('ticker')
        
        if ticker_arg:
            # Calculate for specific ticker
            tickers = [ticker_arg.upper()]
            self.stdout.write(f"📊 Calculating indicators for {ticker_arg.upper()}...")
        else:
            # Calculate for ALL stocks in database
            stocks = Stock.objects.all()
            if not stocks.exists():
                self.stdout.write(self.style.WARNING("⚠️  No stocks in database. Run 'discover_stocks' first."))
                return
            
            tickers = [stock.ticker for stock in stocks]
            self.stdout.write(f"📊 Calculating indicators for {len(tickers)} stocks in database...")
        
        success_count = 0
        error_count = 0
        
        for ticker in tickers:
            try:
                # Check if stock exists
                try:
                    stock = Stock.objects.get(ticker=ticker)
                except Stock.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"  ⚠️  {ticker} not found in database. Skipping."))
                    error_count += 1
                    continue
                
                self.stdout.write(f"\n  Processing {ticker}...")
                
                # Calculate all indicators
                indicators_data = TechnicalAnalysisService.calculate_all_indicators(ticker)
                
                if not indicators_data:
                    self.stdout.write(self.style.ERROR(f"    ❌ Failed to calculate indicators"))
                    error_count += 1
                    continue
                
                # Update or create StockIndicator record
                indicator, created = StockIndicator.objects.update_or_create(
                    stock=stock,
                    defaults={
                        **indicators_data,
                        'last_calculated': timezone.now()
                    }
                )
                
                action = "Created" if created else "Updated"
                self.stdout.write(self.style.SUCCESS(f"    ✅ {action} indicators"))
                
                # Display key metrics
                if indicators_data.get('rsi'):
                    self.stdout.write(f"       RSI: {float(indicators_data['rsi']):.2f} ({indicators_data.get('rsi_signal', 'N/A')})")
                
                if indicators_data.get('ema_50') and indicators_data.get('ema_200'):
                    self.stdout.write(f"       EMA 50: ${float(indicators_data['ema_50']):.2f}")
                    self.stdout.write(f"       EMA 200: ${float(indicators_data['ema_200']):.2f}")
                    self.stdout.write(f"       Trend: {indicators_data.get('ema_trend', 'N/A')}")
                
                if indicators_data.get('support_level_1'):
                    self.stdout.write(f"       Support: ${float(indicators_data['support_level_1']):.2f}")
                
                if indicators_data.get('resistance_level_1'):
                    self.stdout.write(f"       Resistance: ${float(indicators_data['resistance_level_1']):.2f}")
                
                success_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    ❌ Error processing {ticker}: {str(e)}"))
                error_count += 1
                continue
        
        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS(f"✅ Successfully processed: {success_count}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"❌ Errors: {error_count}"))
        self.stdout.write("=" * 50)

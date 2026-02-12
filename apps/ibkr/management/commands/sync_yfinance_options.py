"""
Management command to sync options data from Yahoo Finance
This provides a free alternative to IBKR market data subscriptions
"""

from django.core.management.base import BaseCommand
from apps.ibkr.models import Stock, Option
from apps.ibkr.services.yfinance_options import YFinanceOptionsService
from datetime import datetime, timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Sync options data from Yahoo Finance for all watchlist stocks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            help='Sync options for specific ticker only',
        )
        parser.add_argument(
            '--expiries',
            type=int,
            default=4,
            help='Number of expiration dates to fetch (default: 4)',
        )

    def handle(self, *args, **options):
        ticker_filter = options.get('ticker')
        max_expiries = options.get('expiries', 4)
        
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("📊 Syncing Options from Yahoo Finance"))
        self.stdout.write("=" * 60)
        
        # Get stocks to process
        if ticker_filter:
            stocks = Stock.objects.filter(ticker=ticker_filter.upper())
            if not stocks.exists():
                self.stdout.write(self.style.ERROR(f"❌ Stock {ticker_filter} not found"))
                return
        else:
            stocks = Stock.objects.all()
        
        if not stocks.exists():
            self.stdout.write(self.style.WARNING("⚠️  No stocks found. Add stocks first."))
            return
        
        self.stdout.write(f"\n🔄 Processing {stocks.count()} stock(s)...\n")
        
        success_count = 0
        error_count = 0
        total_options = 0
        
        for stock in stocks:
            self.stdout.write(f"  📈 {stock.ticker}...")
            
            try:
                # Fetch options data from YFinance
                options_data = YFinanceOptionsService.get_options_chain(
                    stock.ticker,
                    max_expiries=max_expiries
                )
                
                self.stdout.write(f"    📥 Fetched {len(options_data)} options from Yahoo Finance")
                
                if not options_data:
                    self.stdout.write(self.style.WARNING(f"    ⚠️  No options data available"))
                    error_count += 1
                    continue
                
                # Delete existing options for this stock
                deleted_count = Option.objects.filter(stock=stock).delete()[0]
                
                # Create new options
                created_count = 0
                error_details = []
                for opt_data in options_data:
                    try:
                        # Calculate DTE (just for delta estimation, dte is a property in the model)
                        dte = (opt_data['expiry_date'] - timezone.now().date()).days
                        
                        # Estimate delta
                        delta = YFinanceOptionsService.estimate_delta(
                            opt_data['option_type'],
                            opt_data['strike'],
                            float(stock.last_price) if stock.last_price else 0,
                            dte,
                            opt_data.get('implied_volatility')
                        )
                        
                        # Create option (don't set mid_price or dte, they're calculated properties)
                        Option.objects.create(
                            stock=stock,
                            option_type=opt_data['option_type'],
                            strike=opt_data['strike'],
                            expiry_date=opt_data['expiry_date'],
                            bid=opt_data['bid'],
                            ask=opt_data['ask'],
                            last=opt_data.get('last_price'),  # Field is 'last', not 'last_price'
                            volume=opt_data['volume'],
                            open_interest=opt_data['open_interest'],
                            implied_volatility=opt_data.get('implied_volatility'),
                            delta=delta
                        )
                        created_count += 1
                        
                    except Exception as e:
                        if len(error_details) < 3:  # Only show first 3 errors
                            error_details.append(str(e))
                        continue
                
                total_options += created_count
                self.stdout.write(self.style.SUCCESS(
                    f"    ✅ Created {created_count} options (deleted {deleted_count} old)"
                ))
                if error_details:
                    self.stdout.write(self.style.ERROR(f"    ⚠️  Errors creating options: {error_details[0]}"))
                success_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    ❌ Error: {str(e)}"))
                error_count += 1
        
        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(f"✅ Successfully processed: {success_count} stocks"))
        self.stdout.write(self.style.SUCCESS(f"📊 Total options created: {total_options}"))
        if error_count > 0:
            self.stdout.write(self.style.WARNING(f"⚠️  Errors: {error_count}"))
        self.stdout.write("=" * 60)
        
        self.stdout.write(self.style.SUCCESS("\n✨ Yahoo Finance options sync complete!"))
        self.stdout.write(self.style.WARNING("\n💡 Note: Delta values are estimated. For accurate Greeks, use IBKR with market data subscription."))

"""
Management command to refresh stock data for all tickers in watchlist
"""
from django.core.management.base import BaseCommand
from apps.ibkr.models import Stock, Watchlist
from apps.ibkr.services.stock_data_fetcher import StockDataFetcher


class Command(BaseCommand):
    help = 'Refresh stock data for all tickers in watchlist using Yahoo Finance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            help='Refresh specific ticker only',
        )

    def handle(self, *args, **options):
        ticker = options.get('ticker')
        
        if ticker:
            # Refresh specific ticker
            tickers = [ticker.upper()]
            self.stdout.write(f"Refreshing data for {ticker.upper()}...")
        else:
            # Refresh all watchlist tickers
            tickers = list(Watchlist.objects.values_list('ticker', flat=True))
            self.stdout.write(f"Refreshing data for {len(tickers)} tickers from watchlist...")
        
        if not tickers:
            self.stdout.write(self.style.WARNING('No tickers found in watchlist'))
            return
        
        success_count = 0
        error_count = 0
        
        for ticker_symbol in tickers:
            try:
                self.stdout.write(f"  Fetching {ticker_symbol}...", ending=' ')
                
                # Fetch data
                stock_data = StockDataFetcher.fetch_stock_data(ticker_symbol)
                
                if stock_data:
                    # Update or create Stock entry
                    stock, created = Stock.objects.update_or_create(
                        ticker=ticker_symbol,
                        defaults={
                            'name': stock_data.get('name', ''),
                            'last_price': stock_data.get('last_price'),
                            'market_cap': stock_data.get('market_cap'),
                            'beta': stock_data.get('beta'),
                            'roe': stock_data.get('roe'),
                            'free_cash_flow': stock_data.get('free_cash_flow'),
                            'sector': stock_data.get('sector', ''),
                            'industry': stock_data.get('industry', ''),
                            'pe_ratio': stock_data.get('pe_ratio'),
                            'forward_pe': stock_data.get('forward_pe'),
                            'dividend_yield': stock_data.get('dividend_yield'),
                            'fifty_two_week_high': stock_data.get('fifty_two_week_high'),
                            'fifty_two_week_low': stock_data.get('fifty_two_week_low'),
                            'avg_volume': stock_data.get('avg_volume'),
                            'last_updated': stock_data.get('last_updated'),
                        }
                    )
                    
                    action = "Created" if created else "Updated"
                    self.stdout.write(self.style.SUCCESS(f"✓ {action}"))
                    self.stdout.write(f"    Name: {stock_data.get('name', 'N/A')}")
                    self.stdout.write(f"    Price: ${stock_data.get('last_price', 0):.2f}")
                    self.stdout.write(f"    Sector: {stock_data.get('sector', 'N/A')}")
                    success_count += 1
                else:
                    self.stdout.write(self.style.ERROR('✗ Failed to fetch data'))
                    error_count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Error: {e}'))
                error_count += 1
        
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"Successfully refreshed: {success_count}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"Failed: {error_count}"))
        self.stdout.write("="*50)

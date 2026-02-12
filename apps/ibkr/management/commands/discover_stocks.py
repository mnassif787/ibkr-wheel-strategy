"""
Management command to discover and add stocks from market indices (S&P 500, Dow, etc.)
"""
from django.core.management.base import BaseCommand
from apps.ibkr.models import Stock, Watchlist
import yfinance as yf


class Command(BaseCommand):
    help = 'Discover and add stocks from major market indices for wheel strategy screening'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--preset',
            type=str,
            default='popular',
            choices=['popular', 'sp500', 'dow', 'tech', 'all'],
            help='Preset list of stocks to add: popular (default 50 common wheel stocks), sp500, dow, tech, or all'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of stocks to add (default: 50)'
        )
    
    def handle(self, *args, **options):
        preset = options.get('preset')
        limit = options.get('limit')
        
        self.stdout.write(f"🔍 Discovering stocks from '{preset}' preset (limit: {limit})...")
        
        # Define preset stock lists for wheel strategy
        presets = {
            'popular': [
                # High volume wheel strategy favorites
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META',
                'AMD', 'INTC', 'NFLX', 'DIS', 'BAC', 'JPM', 'WFC', 'C',
                'F', 'GM', 'AAL', 'UAL', 'CCL', 'PLTR', 'SOFI', 'RIVN',
                'NIO', 'LCID', 'SNAP', 'UBER', 'LYFT', 'ABNB', 'COIN',
                'SQ', 'PYPL', 'V', 'MA', 'T', 'VZ', 'CMCSA', 'PFE',
                'JNJ', 'UNH', 'CVS', 'WBA', 'XOM', 'CVX', 'SLB', 'MRO',
                'KO', 'PEP', 'WMT', 'TGT', 'COST', 'HD', 'LOW', 'NKE',
                # ETFs great for wheel strategy
                'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'TLT', 'GLD', 'SLV',
                'XLF', 'XLE', 'XLK', 'XLV', 'XLU', 'XLP', 'XLI', 'SCHD'
            ],
            'tech': [
                'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'TSLA', 'NVDA', 'META',
                'AMD', 'INTC', 'QCOM', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'CSCO',
                'IBM', 'NOW', 'SNOW', 'DDOG', 'CRWD', 'ZS', 'NET', 'S',
                'SHOP', 'SQ', 'PYPL', 'V', 'MA', 'COIN', 'HOOD', 'SOFI'
            ],
            'dow': [
                'AAPL', 'MSFT', 'UNH', 'GS', 'HD', 'CAT', 'AMGN', 'MCD',
                'V', 'BA', 'TRV', 'AXP', 'HON', 'IBM', 'JPM', 'CVX',
                'JNJ', 'PG', 'WMT', 'DIS', 'MMM', 'NKE', 'KO', 'MRK',
                'CSCO', 'VZ', 'INTC', 'DOW', 'WBA', 'CRM'
            ],
            'sp500': [
                # Top 50 S&P 500 by market cap
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK.B',
                'LLY', 'V', 'UNH', 'XOM', 'JPM', 'MA', 'JNJ', 'WMT',
                'PG', 'AVGO', 'HD', 'ORCL', 'CVX', 'MRK', 'COST', 'ABBV',
                'KO', 'CRM', 'ADBE', 'PEP', 'BAC', 'NFLX', 'TMO', 'CSCO',
                'ACN', 'LIN', 'MCD', 'AMD', 'QCOM', 'DHR', 'ABT', 'WFC',
                'DIS', 'VZ', 'CMCSA', 'TXN', 'INTC', 'PM', 'NEE', 'INTU',
                'UPS', 'RTX'
            ]
        }
        
        # Get stock list
        if preset == 'all':
            tickers = list(set(presets['popular'] + presets['tech'] + presets['dow'] + presets['sp500']))
        else:
            tickers = presets.get(preset, presets['popular'])
        
        # Apply limit
        tickers = tickers[:limit]
        
        self.stdout.write(f"\n📋 Processing {len(tickers)} tickers...")
        
        added_count = 0
        skipped_count = 0
        error_count = 0
        
        for ticker in tickers:
            try:
                # Check if already exists
                if Stock.objects.filter(ticker=ticker).exists():
                    self.stdout.write(self.style.WARNING(f"  ⏭️  {ticker} - Already exists"))
                    skipped_count += 1
                    continue
                
                # Fetch stock data from yfinance
                self.stdout.write(f"  📥 {ticker} - Fetching data...")
                stock_info = yf.Ticker(ticker)
                info = stock_info.info
                
                # Get current price
                current_price = info.get('currentPrice') or info.get('regularMarketPrice')
                if not current_price:
                    self.stdout.write(self.style.WARNING(f"  ⚠️  {ticker} - No price data, skipping"))
                    error_count += 1
                    continue
                
                # Create stock
                stock = Stock.objects.create(
                    ticker=ticker,
                    name=info.get('longName', ticker),
                    last_price=current_price,
                    market_cap=info.get('marketCap'),
                    beta=info.get('beta'),
                    dividend_yield=info.get('dividendYield'),
                    sector=info.get('sector', 'Unknown'),
                    industry=info.get('industry', 'Unknown')
                )
                
                self.stdout.write(self.style.SUCCESS(f"  ✅ {ticker} - Added (${current_price:.2f})"))
                added_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ {ticker} - Error: {str(e)}"))
                error_count += 1
                continue
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS(f"✅ Added: {added_count} stocks"))
        self.stdout.write(self.style.WARNING(f"⏭️  Skipped: {skipped_count} stocks (already exist)"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"❌ Errors: {error_count} stocks"))
        self.stdout.write("="*60)
        
        if added_count > 0:
            self.stdout.write("\n💡 Next steps:")
            self.stdout.write("   1. Run: python manage.py calculate_indicators")
            self.stdout.write("   2. Run: python manage.py sync_yfinance_options")
            self.stdout.write("   3. Refresh the stocks page to see new stocks with scores!")

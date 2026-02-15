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
            choices=['popular', 'sp500', 'dow', 'tech', 'all', 'market'],
            help='Preset list of stocks to add: popular (100 common wheel stocks), sp500 (top 100 S&P 500), dow, tech, market (comprehensive), or all'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of stocks to add (default: no limit for most presets)'
        )
    
    def handle(self, *args, **options):
        preset = options.get('preset')
        limit = options.get('limit')
        
        self.stdout.write(f"🔍 Discovering stocks from '{preset}' preset (limit: {limit})...")
        
        # Define preset stock lists for wheel strategy
        presets = {
            'popular': [
                # High volume wheel strategy favorites (100 most popular)
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META',
                'AMD', 'INTC', 'NFLX', 'DIS', 'BAC', 'JPM', 'WFC', 'C',
                'F', 'GM', 'AAL', 'UAL', 'CCL', 'PLTR', 'SOFI', 'RIVN',
                'NIO', 'LCID', 'SNAP', 'UBER', 'LYFT', 'ABNB', 'COIN',
                'SQ', 'PYPL', 'V', 'MA', 'T', 'VZ', 'CMCSA', 'PFE',
                'JNJ', 'UNH', 'CVS', 'WBA', 'XOM', 'CVX', 'SLB', 'MRO',
                'KO', 'PEP', 'WMT', 'TGT', 'COST', 'HD', 'LOW', 'NKE',
                'BABA', 'JD', 'PDD', 'MARA', 'RIOT', 'MSTR', 'HOOD',
                'DKNG', 'PENN', 'MGM', 'LVS', 'WYNN', 'CZR', 'AMC',
                'BB', 'NOK', 'SIRI', 'VALE', 'X', 'CLF', 'STLD', 'FCX',
                'GOLD', 'NEM', 'AUY', 'SBUX', 'MCD', 'YUM', 'CMG', 'QSR',
                'DAL', 'LUV', 'JBLU', 'ALK', 'RCL', 'NCLH', 'WYNN', 'PTON',
                'ZM', 'SNOW', 'CRWD', 'NET', 'DDOG', 'MDB', 'VEEV', 'OKTA',
                # ETFs great for wheel strategy
                'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'TLT', 'GLD', 'SLV',
                'XLF', 'XLE', 'XLK', 'XLV', 'XLU', 'XLP', 'XLI', 'SCHD'
            ],
            'tech': [
                'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'TSLA', 'NVDA', 'META',
                'AMD', 'INTC', 'QCOM', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'CSCO',
                'IBM', 'NOW', 'SNOW', 'DDOG', 'CRWD', 'ZS', 'NET', 'S',
                'SHOP', 'SQ', 'PYPL', 'V', 'MA', 'COIN', 'HOOD', 'SOFI',
                'UBER', 'LYFT', 'DASH', 'ABNB', 'ZM', 'TEAM', 'DOCU', 'TWLO',
                'ROKU', 'SNAP', 'PINS', 'SPOT', 'RBLX', 'U', 'PLTR', 'CPNG'
            ],
            'dow': [
                'AAPL', 'MSFT', 'UNH', 'GS', 'HD', 'CAT', 'AMGN', 'MCD',
                'V', 'BA', 'TRV', 'AXP', 'HON', 'IBM', 'JPM', 'CVX',
                'JNJ', 'PG', 'WMT', 'DIS', 'MMM', 'NKE', 'KO', 'MRK',
                'CSCO', 'VZ', 'INTC', 'DOW', 'WBA', 'CRM'
            ],
            'sp500': [
                # Top 100 S&P 500 by market cap for comprehensive wheel strategy screening
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK.B',
                'LLY', 'V', 'UNH', 'XOM', 'JPM', 'MA', 'JNJ', 'WMT',
                'PG', 'AVGO', 'HD', 'ORCL', 'CVX', 'MRK', 'COST', 'ABBV',
                'KO', 'CRM', 'ADBE', 'PEP', 'BAC', 'NFLX', 'TMO', 'CSCO',
                'ACN', 'LIN', 'MCD', 'AMD', 'QCOM', 'DHR', 'ABT', 'WFC',
                'DIS', 'VZ', 'CMCSA', 'TXN', 'INTC', 'PM', 'NEE', 'INTU',
                'UPS', 'RTX', 'HON', 'AMGN', 'SPGI', 'LOW', 'UNP', 'T',
                'CAT', 'GS', 'SBUX', 'BKNG', 'BLK', 'AXP', 'DE', 'ELV',
                'MS', 'MDT', 'LMT', 'PLD', 'TJX', 'ADP', 'SYK', 'GILD',
                'CVS', 'REGN', 'VRTX', 'ADI', 'MMC', 'CI', 'MDLZ', 'SO',
                'CB', 'ISRG', 'ZTS', 'SCHW', 'CME', 'DUK', 'C', 'PGR',
                'MO', 'EOG', 'ITW', 'NOC', 'BDX', 'BSX', 'SLB', 'MMM',
                'USB', 'HCA', 'CL', 'PNC', 'GE'
            ],
            'market': [
                # Comprehensive market coverage: 300+ stocks across all sectors for wheel strategy
                # Mega Cap Tech
                'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA',
                # Large Cap Tech
                'ORCL', 'CRM', 'ADBE', 'AVGO', 'CSCO', 'ACN', 'IBM', 'INTC', 'AMD', 'QCOM', 'TXN',
                # Mid Cap Tech
                'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS', 'MDB', 'NOW', 'TEAM', 'WDAY', 'SHOP',
                # Small Cap Tech
                'PLTR', 'RIVN', 'LCID', 'NIO', 'SOFI', 'HOOD', 'COIN', 'MARA', 'RIOT', 'MSTR',
                # Financials
                'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'BLK', 'AXP', 'SCHW', 'USB', 'PNC', 'TFC', 'COF',
                # Healthcare
                'UNH', 'JNJ', 'LLY', 'ABBV', 'MRK', 'PFE', 'TMO', 'ABT', 'DHR', 'CVS', 'AMGN', 'GILD', 'REGN', 'VRTX',
                # Consumer 
                'WMT', 'COST', 'HD', 'LOW', 'TGT', 'NKE', 'SBUX', 'MCD', 'DIS', 'CMCSA', 'NFLX',
                # Energy
                'XOM', 'CVX', 'SLB', 'COP', 'EOG', 'MRO', 'HAL', 'OXY', 'PSX', 'VLO', 'MPC',
                # Industrials
                'CAT', 'BA', 'HON', 'UNP', 'RTX', 'LMT', 'DE', 'GE', 'MMM', 'EMR', 'ETN',
                # Auto
                'F', 'GM', 'TSLA', 'RIVN', 'LCID', 'NIO', 'XPEV', 'LI',
                # Airlines & Travel
                'AAL', 'UAL', 'DAL', 'LUV', 'JBLU', 'ALK', 'CCL', 'RCL', 'NCLH', 'MAR', 'HLT',
                # Retail & E-commerce
                'AMZN', 'WMT', 'HD', 'COST', 'TGT', 'LOW', 'TJX', 'ROST', 'ETSY', 'W', 'CHWY',
                # Payments & Fintech
                'V', 'MA', 'PYPL', 'SQ', 'COIN', 'SOFI', 'HOOD', 'AFRM', 'NU', 'MELI',
                # Social Media & Entertainment
                'META', 'SNAP', 'PINS', 'RBLX', 'U', 'DKNG', 'PENN', 'MGM', 'LVS', 'WYNN', 'CZR',
                # Streaming & Media
                'NFLX', 'DIS', 'PARA', 'WBD', 'SPOT', 'ROKU',
                # Cloud & SaaS
                'CRM', 'NOW', 'SNOW', 'WDAY', 'TEAM', 'ZM', 'DOCU', 'TWLO', 'OKTA', 'DDOG',
                # Cybersecurity
                'CRWD', 'ZS', 'PANW', 'FTNT', 'CYBR', 'S', 'TENB', 'QLYS',
                # Semiconductors
                'NVDA', 'AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'ADI', 'MRVL', 'MU', 'AMAT', 'LRCX', 'KLAC',
                # Pharma & Biotech
                'PFE', 'MRNA', 'BNTX', 'JNJ', 'LLY', 'ABBV', 'GILD', 'BIIB', 'VRTX', 'REGN', 'AMGN',
                # Real Estate & REITs
                'PLD', 'AMT', 'CCI', 'EQIX', 'PSA', 'O', 'VICI', 'SPG', 'AVB', 'EQR',
                # Materials & Mining
                'FCX', 'NEM', 'GOLD', 'AUY', 'VALE', 'X', 'CLF', 'STLD', 'NUE',
                # Telecom
                'T', 'VZ', 'TMUS', 'CMCSA', 'CHTR',
                # Defense
                'LMT', 'RTX', 'NOC', 'GD', 'BA', 'HII', 'LHX',
                # Chinese ADRs
                'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI', 'BILI', 'IQ',
                # Crypto-related
                'COIN', 'MARA', 'RIOT', 'MSTR', 'SI', 'HUT', 'BTBT',
                # ETFs for wheel strategy
                'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EFA', 'TLT', 'GLD', 'SLV', 'USO',
                'XLF', 'XLE', 'XLK', 'XLV', 'XLU', 'XLP', 'XLI', 'XLY', 'XLB', 'XLRE',
                'SMH', 'XBI', 'XRT', 'XHB', 'SCHD', 'VYM', 'JEPI', 'JEPQ'
            ]
        }
        
        # Get stock list
        if preset == 'all':
            tickers = list(set(presets['popular'] + presets['tech'] + presets['dow'] + presets['sp500'] + presets['market']))
        else:
            tickers = presets.get(preset, presets['popular'])
        
        # Apply limit if specified
        if limit:
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
            self.stdout.write("   3. Refresh the hub page to see new stocks with scores!")
            self.stdout.write("\n📊 Pro tip: Use '--preset market' to load 300+ comprehensive market stocks")
            self.stdout.write("   Example: python manage.py discover_stocks --preset market")

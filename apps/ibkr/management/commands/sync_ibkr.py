"""
Django management command to sync data from IBKR
Usage: python manage.py sync_ibkr
"""
from django.core.management.base import BaseCommand
from apps.ibkr.services.market_data import MarketDataService
from apps.ibkr.models import Watchlist
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync stock and options data from Interactive Brokers'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--signals',
            action='store_true',
            help='Also generate trading signals after sync',
        )
        parser.add_argument(
            '--ticker',
            type=str,
            help='Sync specific ticker only',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('🚀 IBKR Data Sync Started'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        # Check if watchlist has items
        watchlist_count = Watchlist.objects.count()
        
        if watchlist_count == 0:
            self.stdout.write(self.style.WARNING('\n⚠️  Watchlist is empty!'))
            self.stdout.write(self.style.WARNING('Add tickers via Dashboard or Admin panel first.'))
            self.stdout.write(self.style.WARNING('\nExample: Add AAPL, MSFT, TSLA to watchlist\n'))
            return
        
        self.stdout.write(f'\n📋 Watchlist: {watchlist_count} ticker(s)')
        
        # List watchlist items
        tickers = list(Watchlist.objects.values_list('ticker', flat=True))
        self.stdout.write(f'📊 Tickers: {", ".join(tickers)}\n')
        
        # Initialize service
        service = MarketDataService()
        
        try:
            # Sync stock data
            self.stdout.write(self.style.SUCCESS('🔄 Fetching data from IBKR...'))
            self.stdout.write(self.style.WARNING('⏳ This may take a minute...\n'))
            
            service.sync_watchlist_stocks()
            
            self.stdout.write(self.style.SUCCESS('\n✅ Stock data synced successfully!'))
            
            # Generate signals if requested
            if options['signals']:
                self.stdout.write(self.style.SUCCESS('\n🎯 Generating trading signals...\n'))
                service.generate_signals()
                self.stdout.write(self.style.SUCCESS('\n✅ Signals generated!'))
            
            self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
            self.stdout.write(self.style.SUCCESS('✨ Sync Complete!'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write('\nNext steps:')
            self.stdout.write('  • Visit Dashboard: http://127.0.0.1:8000/ibkr/')
            self.stdout.write('  • View Signals: http://127.0.0.1:8000/ibkr/signals/')
            self.stdout.write('  • Check Admin: http://127.0.0.1:8000/admin/\n')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error during sync: {str(e)}'))
            self.stdout.write(self.style.ERROR('\nTroubleshooting:'))
            self.stdout.write('  1. Make sure TWS or IB Gateway is running')
            self.stdout.write('  2. Check API settings in TWS (File → Global Configuration → API)')
            self.stdout.write('  3. Verify IBKR connection settings in .env file')
            self.stdout.write(f'     IBKR_HOST=127.0.0.1')
            self.stdout.write(f'     IBKR_PORT=7497 (or 7496 for paper trading)\n')
            raise

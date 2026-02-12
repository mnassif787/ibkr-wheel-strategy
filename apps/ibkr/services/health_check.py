"""
Health Check Service - Tests all data sources and indicators on platform startup
Verifies IBKR connection, yfinance, database, and technical indicators
"""
import logging
from typing import Dict
from django.conf import settings
from django.db import connection
from django.utils import timezone
from datetime import timedelta
import yfinance as yf

logger = logging.getLogger(__name__)


class HealthCheckService:
    """Comprehensive health check for all platform components"""
    
    def __init__(self):
        self.results = {
            'overall_status': 'healthy',
            'checks': [],
            'timestamp': timezone.now(),
        }
    
    def run_all_checks(self) -> Dict:
        """Run all health checks and return results"""
        logger.info("🔍 Starting platform health checks...")
        
        # Run all checks
        self.check_database()
        self.check_ibkr_connection()
        self.check_yfinance()
        self.check_technical_indicators()
        self.check_options_data()
        self.check_data_freshness()
        
        # Determine overall status
        failed_checks = [c for c in self.results['checks'] if c['status'] == 'failed']
        warning_checks = [c for c in self.results['checks'] if c['status'] == 'warning']
        
        if failed_checks:
            self.results['overall_status'] = 'critical'
        elif warning_checks:
            self.results['overall_status'] = 'warning'
        else:
            self.results['overall_status'] = 'healthy'
        
        self._log_results()
        return self.results
    
    def check_database(self):
        """Check database connectivity"""
        check = {
            'name': 'Database Connection',
            'status': 'passed',
            'message': '',
            'solution': '',
            'icon': '🗄️'
        }
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            
            from apps.ibkr.models import Stock, Option, Signal, Watchlist, StockIndicator
            
            stock_count = Stock.objects.count()
            option_count = Option.objects.count()
            watchlist_count = Watchlist.objects.count()
            indicator_count = StockIndicator.objects.count()
            
            check['message'] = f'Connected. Stocks: {stock_count}, Options: {option_count}, Watchlist: {watchlist_count}, Indicators: {indicator_count}'
            
            if stock_count == 0:
                check['status'] = 'warning'
                check['message'] += ' | No stocks in database'
                check['solution'] = 'Run: python manage.py discover_stocks or add stocks to watchlist'
            
            logger.info(f"✅ Database check passed - {check['message']}")
            
        except Exception as e:
            check['status'] = 'failed'
            check['message'] = f'Database error: {str(e)}'
            check['solution'] = 'Check database configuration in settings.py or run: python manage.py migrate'
            logger.error(f"❌ Database check failed: {str(e)}")
        
        self.results['checks'].append(check)
    
    def check_ibkr_connection(self):
        """Check IBKR TWS/Gateway connection"""
        check = {
            'name': 'IBKR Connection',
            'status': 'passed',
            'message': '',
            'solution': '',
            'icon': '🔌'
        }
        
        try:
            from apps.ibkr.services.ibkr_client import IBKRClient
            
            client = IBKRClient()
            
            # Try to connect/reconnect if not already connected
            if client.ensure_connected():
                check['message'] = f'Connected to {settings.IBKR_HOST}:{settings.IBKR_PORT} (Client ID: {client.client_id})'
                logger.info(f"✅ IBKR check passed - {check['message']}")
                check['status'] = 'passed'
            else:
                check['status'] = 'warning'
                check['message'] = f'Cannot connect to {settings.IBKR_HOST}:{settings.IBKR_PORT} - Using YFinance instead'
                check['solution'] = 'Start TWS/IB Gateway on the correct port. Paper trading: 7496, Live: 7497'
                logger.warning(f"⚠️ IBKR not connected")
        except Exception as e:
            check['status'] = 'warning'
            check['message'] = f'Cannot connect to IBKR: {str(e)[:80]}'
            check['solution'] = 'Ensure TWS/IB Gateway is running. Check IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID in settings.'
            logger.warning(f"⚠️ IBKR connection error: {str(e)}")
        
        self.results['checks'].append(check)
    
    def check_yfinance(self):
        """Check Yahoo Finance data access"""
        check = {
            'name': 'Yahoo Finance (yfinance)',
            'status': 'passed',
            'message': '',
            'solution': '',
            'icon': '📈'
        }
        
        try:
            test_ticker = yf.Ticker('AAPL')
            info = test_ticker.info
            
            if info and info.get('currentPrice'):
                check['message'] = f'Connected. Test query successful (AAPL: ${info.get("currentPrice")})'
                logger.info(f"✅ YFinance check passed")
            else:
                hist = test_ticker.history(period='1d')
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
                    check['message'] = f'Connected. Historical data accessible (AAPL: ${price:.2f})'
                    logger.info(f"✅ YFinance check passed (historical data)")
                else:
                    check['status'] = 'warning'
                    check['message'] = 'Connected but no data returned'
                    check['solution'] = 'Check internet connection or try again later. Yahoo Finance may be rate limiting.'
                    logger.warning(f"⚠️ YFinance check warning - no data")
                    
        except Exception as e:
            check['status'] = 'failed'
            check['message'] = f'YFinance error: {str(e)}'
            check['solution'] = 'Check internet connection. If issue persists, run: pip install --upgrade yfinance'
            logger.error(f"❌ YFinance check failed: {str(e)}")
        
        self.results['checks'].append(check)
    
    def check_technical_indicators(self):
        """Check technical indicator calculations"""
        check = {
            'name': 'Technical Indicators (RSI, EMA, BB, S/R)',
            'status': 'passed',
            'message': '',
            'solution': '',
            'icon': '📊'
        }
        
        try:
            from apps.ibkr.services.technical_analysis import TechnicalAnalysisService
            
            test_ticker = 'AAPL'
            df = TechnicalAnalysisService.fetch_historical_data(test_ticker, period='3mo')
            
            if df is None or df.empty:
                check['status'] = 'warning'
                check['message'] = 'Cannot fetch historical data for indicator calculation'
                check['solution'] = 'Check internet connection and YFinance availability'
                logger.warning(f"⚠️ Technical indicators check warning - no historical data")
            else:
                indicators_tested = []
                
                try:
                    rsi, rsi_signal = TechnicalAnalysisService.calculate_rsi(df)
                    if rsi is not None and isinstance(rsi, (int, float)):
                        indicators_tested.append(f'RSI: {float(rsi):.1f}')
                except Exception as e:
                    logger.warning(f"RSI calculation error: {str(e)}")
                
                try:
                    ema_result = TechnicalAnalysisService.calculate_ema(df)
                    if ema_result and isinstance(ema_result, dict):
                        ema_50 = ema_result.get('ema_50')
                        if ema_50 is not None and isinstance(ema_50, (int, float)):
                            indicators_tested.append(f'EMA-50: {float(ema_50):.2f}')
                except Exception as e:
                    logger.warning(f"EMA calculation error: {str(e)}")
                
                try:
                    bb_result = TechnicalAnalysisService.calculate_bollinger_bands(df)
                    if bb_result and isinstance(bb_result, dict):
                        bb_upper = bb_result.get('bb_upper')
                        bb_lower = bb_result.get('bb_lower')
                        if bb_upper is not None and isinstance(bb_upper, (int, float)) and bb_lower is not None and isinstance(bb_lower, (int, float)):
                            indicators_tested.append(f'BB: {float(bb_lower):.2f}-{float(bb_upper):.2f}')
                except Exception as e:
                    logger.warning(f"Bollinger Bands calculation error: {str(e)}")
                
                try:
                    # Check if method exists - it's called detect_support_resistance
                    if hasattr(TechnicalAnalysisService, 'detect_support_resistance'):
                        sr_result = TechnicalAnalysisService.detect_support_resistance(df)
                        if sr_result and isinstance(sr_result, dict):
                            support_levels = sr_result.get('support_levels', [])
                            resistance_levels = sr_result.get('resistance_levels', [])
                            
                            # Find first non-None support and resistance
                            support = next((s for s in support_levels if s is not None), None)
                            resistance = next((r for r in resistance_levels if r is not None), None)
                            
                            if support and resistance:
                                indicators_tested.append(f'S/R: {float(support):.2f}/{float(resistance):.2f}')
                            elif support:
                                indicators_tested.append(f'Support: {float(support):.2f}')
                            elif resistance:
                                indicators_tested.append(f'Resistance: {float(resistance):.2f}')
                            else:
                                # S/R detection working but no levels found (still counts as working)
                                indicators_tested.append('S/R: detected')
                except Exception as e:
                    logger.warning(f"Support/Resistance calculation error: {str(e)}")
                
                if len(indicators_tested) >= 4:
                    check['message'] = f'All 4 indicator types working. Sample: {indicators_tested[0]}, {indicators_tested[1]}'
                    logger.info(f"✅ Technical indicators check passed")
                elif len(indicators_tested) >= 3:
                    check['status'] = 'passed'
                    check['message'] = f'{len(indicators_tested)}/4 indicators working: {", ".join(indicators_tested)}'
                    logger.info(f"✅ Technical indicators mostly working ({len(indicators_tested)}/4)")
                elif len(indicators_tested) >= 2:
                    check['status'] = 'warning'
                    check['message'] = f'{len(indicators_tested)}/4 indicators working: {", ".join(indicators_tested)}'
                    check['solution'] = 'Core functionality works. Some indicators optional.'
                    logger.warning(f"⚠️ Some technical indicators failed")
                elif len(indicators_tested) > 0:
                    check['status'] = 'warning'
                    check['message'] = f'Only {len(indicators_tested)}/4 indicators working: {", ".join(indicators_tested)}'
                    check['solution'] = 'Check TechnicalAnalysisService implementation for errors'
                    logger.warning(f"⚠️ Most technical indicators failed")
                else:
                    check['status'] = 'failed'
                    check['message'] = 'No indicators working'
                    check['solution'] = 'Check pandas/numpy installation: pip install pandas numpy'
                    logger.error(f"❌ All technical indicators failed")
                
        except ImportError as e:
            check['status'] = 'failed'
            check['message'] = f'Missing dependencies: {str(e)}'
            check['solution'] = 'Run: pip install pandas numpy yfinance'
            logger.error(f"❌ Technical indicators check failed - missing dependencies")
        except Exception as e:
            check['status'] = 'warning'
            check['message'] = f'Indicator check error: {str(e)[:150]}'
            check['solution'] = 'Check TechnicalAnalysisService implementation or internet connection'
            logger.error(f"❌ Technical indicators check failed: {str(e)}")
        
        self.results['checks'].append(check)
    
    def check_options_data(self):
        """Check options data fetching capability"""
        check = {
            'name': 'Options Data (YFinance)',
            'status': 'passed',
            'message': '',
            'solution': '',
            'icon': '📋'
        }
        
        try:
            from apps.ibkr.services.yfinance_options import YFinanceOptionsService
            
            test_ticker = 'AAPL'
            options = YFinanceOptionsService.get_options_chain(test_ticker, max_expiries=1)
            
            if options and len(options) > 0:
                check['message'] = f'Options data accessible. Test query returned {len(options)} contracts for {test_ticker}'
                logger.info(f"✅ Options data check passed")
            else:
                check['status'] = 'warning'
                check['message'] = 'No options data returned for test ticker'
                check['solution'] = 'Check internet connection and yfinance library. Some stocks may not have options.'
                logger.warning(f"⚠️ Options data check warning - no data returned")
                
        except Exception as e:
            check['status'] = 'failed'
            check['message'] = f'Options data error: {str(e)}'
            check['solution'] = 'Check YFinanceOptionsService implementation and yfinance installation'
            logger.error(f"❌ Options data check failed: {str(e)}")
        
        self.results['checks'].append(check)
    
    def check_data_freshness(self):
        """Check if existing data is fresh"""
        check = {
            'name': 'Data Freshness',
            'status': 'passed',
            'message': '',
            'solution': '',
            'icon': '⏰'
        }
        
        try:
            from apps.ibkr.models import Stock, Option, StockIndicator
            
            now = timezone.now()
            stale_threshold = timedelta(hours=24)
            recent_threshold = timedelta(hours=4)  # Very fresh data
            
            stocks = Stock.objects.all()
            if stocks.exists():
                stale_stocks = stocks.filter(last_updated__lt=now - stale_threshold).count()
                recent_stocks = stocks.filter(last_updated__gte=now - recent_threshold).count()
                total_stocks = stocks.count()
                
                indicators = StockIndicator.objects.all()
                # StockIndicator uses 'last_calculated' not 'last_updated'
                try:
                    stale_indicators = indicators.filter(last_calculated__lt=now - stale_threshold).count()
                except:
                    stale_indicators = 0
                total_indicators = indicators.count()
                
                options = Option.objects.all()
                stale_options = options.filter(last_updated__lt=now - stale_threshold).count()
                total_options = options.count()
                
                # Calculate staleness percentage
                total_items = total_stocks + total_indicators + total_options
                stale_count = stale_stocks + stale_indicators + stale_options
                
                if total_items == 0:
                    check['status'] = 'warning'
                    check['message'] = 'No data in database yet'
                    check['solution'] = 'Run: python manage.py discover_stocks && python manage.py calculate_indicators'
                elif stale_count == 0:
                    check['message'] = f'✨ All data fresh! Stocks: {total_stocks}, Indicators: {total_indicators}, Options: {total_options}'
                    if recent_stocks > 0:
                        check['message'] += f' ({recent_stocks} stocks updated in last 4h)'
                    logger.info(f"✅ Data freshness check passed")
                elif stale_count / total_items < 0.3:  # Less than 30% stale is OK
                    check['status'] = 'warning'
                    stale_items = []
                    if stale_stocks > 0:
                        stale_items.append(f'{stale_stocks}/{total_stocks} stocks')
                    if stale_indicators > 0:
                        stale_items.append(f'{stale_indicators}/{total_indicators} indicators')
                    if stale_options > 0:
                        stale_items.append(f'{stale_options}/{total_options} options')
                    check['message'] = f'Some stale data (>24h): {", ".join(stale_items)}. Recent: {recent_stocks} stocks'
                    check['solution'] = 'Click the Refresh button in navbar (⚡ Quick mode recommended)'
                    check['command'] = 'python manage.py quick_refresh'
                    logger.warning(f"⚠️ Some data is stale but acceptable")
                else:
                    check['status'] = 'warning'
                    stale_items = []
                    if stale_stocks > 0:
                        stale_items.append(f'{stale_stocks}/{total_stocks} stocks')
                    if stale_indicators > 0:
                        stale_items.append(f'{stale_indicators}/{total_indicators} indicators')
                    if stale_options > 0:
                        stale_items.append(f'{stale_options}/{total_options} options')
                    check['message'] = f'Most data stale (>24h): {", ".join(stale_items)}'
                    check['solution'] = 'Click the Refresh button in navbar or run: python manage.py quick_refresh'
                    check['command'] = 'python manage.py refresh_all_data'
                    logger.warning(f"⚠️ Data freshness warning - {check['message']}")
            else:
                check['status'] = 'warning'
                check['message'] = 'No stock data in database yet'
                check['solution'] = 'Start by running: python manage.py discover_stocks'
                logger.warning(f"⚠️ No stock data in database")
                
        except Exception as e:
            check['status'] = 'warning'
            check['message'] = f'Cannot check data freshness: {str(e)[:100]}'
            check['solution'] = 'Database might be empty or models need migration'
            logger.warning(f"⚠️ Data freshness check warning: {str(e)}")
        
        self.results['checks'].append(check)
    
    def get_quick_status(self) -> Dict:
        """Get simplified status for navbar display"""
        if not self.results['checks']:
            self.run_all_checks()
        
        return {
            'status': self.results['overall_status'],
            'icon': self._get_status_icon(self.results['overall_status']),
            'message': self._get_status_message(self.results['overall_status']),
            'failed_count': len([c for c in self.results['checks'] if c['status'] == 'failed']),
            'warning_count': len([c for c in self.results['checks'] if c['status'] == 'warning']),
            'passed_count': len([c for c in self.results['checks'] if c['status'] == 'passed']),
            'total_count': len(self.results['checks']),
        }
    
    def _get_status_icon(self, status: str) -> str:
        """Get icon for status"""
        icons = {
            'healthy': '✅',
            'warning': '⚠️',
            'critical': '❌'
        }
        return icons.get(status, '❓')
    
    def _get_status_message(self, status: str) -> str:
        """Get message for status"""
        messages = {
            'healthy': 'All systems operational',
            'warning': 'Some issues detected',
            'critical': 'Critical issues detected'
        }
        return messages.get(status, 'Unknown status')
    
    def _log_results(self):
        """Log summary of all checks"""
        logger.info("=" * 60)
        logger.info(f"🏥 HEALTH CHECK SUMMARY - {self.results['overall_status'].upper()}")
        logger.info("=" * 60)
        
        for check in self.results['checks']:
            status_icon = '✅' if check['status'] == 'passed' else ('⚠️' if check['status'] == 'warning' else '❌')
            logger.info(f"{status_icon} {check['icon']} {check['name']}: {check['message']}")
            if check['solution']:
                logger.info(f"   💡 Solution: {check['solution']}")
        
        logger.info("=" * 60)


# Global instance with TTL
_health_check_instance = None
_health_check_last_run = 0
_HEALTH_CHECK_TTL = 30  # Re-run checks every 30 seconds


def get_health_check_service():
    """Get or create health check service singleton with TTL"""
    global _health_check_instance, _health_check_last_run
    import time
    now = time.time()
    if _health_check_instance is None or (now - _health_check_last_run) > _HEALTH_CHECK_TTL:
        _health_check_instance = HealthCheckService()
        _health_check_instance.run_all_checks()
        _health_check_last_run = now
    return _health_check_instance


def refresh_health_check():
    """Force refresh of health check"""
    global _health_check_instance, _health_check_last_run
    import time
    _health_check_instance = HealthCheckService()
    _health_check_last_run = time.time()
    return _health_check_instance.run_all_checks()

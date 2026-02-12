"""
Stock Data Fetcher - Fetch comprehensive stock data using yfinance
"""
import yfinance as yf
import logging
from datetime import datetime
from django.utils import timezone

logger = logging.getLogger(__name__)


class StockDataFetcher:
    """Fetch stock data from Yahoo Finance"""
    
    @staticmethod
    def fetch_stock_data(ticker):
        """
        Fetch comprehensive stock data for a ticker
        
        Args:
            ticker: Stock symbol (e.g., 'AAPL')
        
        Returns:
            dict with stock data or None if failed
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Get current price
            history = stock.history(period='1d')
            current_price = history['Close'].iloc[-1] if not history.empty else None
            
            # Extract relevant data
            data = {
                'ticker': ticker.upper(),
                'name': info.get('longName', info.get('shortName', '')),
                'last_price': current_price or info.get('currentPrice') or info.get('regularMarketPrice'),
                'market_cap': info.get('marketCap'),
                'beta': info.get('beta'),
                'roe': info.get('returnOnEquity'),
                'free_cash_flow': info.get('freeCashflow'),
                'sector': info.get('sector', ''),
                'industry': info.get('industry', ''),
                'last_updated': timezone.now(),
                
                # Additional useful data
                'pe_ratio': info.get('trailingPE'),
                'forward_pe': info.get('forwardPE'),
                'dividend_yield': info.get('dividendYield'),
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
                'avg_volume': info.get('averageVolume'),
                'description': info.get('longBusinessSummary', ''),
                'website': info.get('website', ''),
                'employees': info.get('fullTimeEmployees'),
            }
            
            logger.info(f"✅ Fetched data for {ticker}: {data['name']}")
            return data
            
        except Exception as e:
            logger.error(f"❌ Error fetching data for {ticker}: {e}")
            return None
    
    @staticmethod
    def fetch_multiple_stocks(tickers):
        """
        Fetch data for multiple stocks
        
        Args:
            tickers: List of stock symbols
        
        Returns:
            dict mapping ticker to stock data
        """
        results = {}
        for ticker in tickers:
            data = StockDataFetcher.fetch_stock_data(ticker)
            if data:
                results[ticker.upper()] = data
        return results

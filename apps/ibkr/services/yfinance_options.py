"""
YFinance Options Data Service
Fetches options data from Yahoo Finance as fallback when IBKR data is unavailable
"""

import yfinance as yf
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone


class YFinanceOptionsService:
    """Service to fetch options data from Yahoo Finance"""
    
    @staticmethod
    def get_options_chain(ticker, max_expiries=4):
        """
        Fetch options chain from Yahoo Finance
        
        Args:
            ticker: Stock ticker symbol
            max_expiries: Maximum number of expiration dates to fetch (default 4)
            
        Returns:
            List of option contracts with pricing data
        """
        try:
            stock = yf.Ticker(ticker)
            
            # Get available expiration dates
            try:
                expirations = stock.options[:max_expiries]  # Limit to first N expiries
            except Exception:
                print(f"  ⚠️  No options available for {ticker}")
                return []
            
            if not expirations:
                print(f"  ⚠️  No options expiration dates for {ticker}")
                return []
            
            options_data = []
            
            for expiry in expirations:
                try:
                    # Get options chain for this expiration
                    opt_chain = stock.option_chain(expiry)
                    
                    # Process calls
                    calls = opt_chain.calls
                    for _, row in calls.iterrows():
                        try:
                            option = {
                                'ticker': ticker,
                                'option_type': 'CALL',
                                'strike': float(row.get('strike', 0)),
                                'expiry_date': datetime.strptime(expiry, '%Y-%m-%d').date(),
                                'bid': float(row.get('bid', 0)) if row.get('bid', 0) > 0 else None,
                                'ask': float(row.get('ask', 0)) if row.get('ask', 0) > 0 else None,
                                'last_price': float(row.get('lastPrice', 0)) if row.get('lastPrice', 0) > 0 else None,
                                'volume': int(row.get('volume', 0)) if row.get('volume', 0) else 0,
                                'open_interest': int(row.get('openInterest', 0)) if row.get('openInterest', 0) else 0,
                                'implied_volatility': float(row.get('impliedVolatility', 0)) if row.get('impliedVolatility', 0) > 0 else None,
                            }
                            
                            # Calculate mid price if bid/ask available
                            if option['bid'] and option['ask']:
                                option['mid_price'] = (option['bid'] + option['ask']) / 2
                            elif option['last_price']:
                                option['mid_price'] = option['last_price']
                            else:
                                option['mid_price'] = None
                            
                            # YFinance doesn't provide delta directly, estimate it
                            # For calls: rough approximation based on moneyness
                            option['delta'] = None  # Will be calculated if needed
                            
                            options_data.append(option)
                        except Exception as e:
                            continue  # Skip malformed rows
                    
                    # Process puts
                    puts = opt_chain.puts
                    for _, row in puts.iterrows():
                        try:
                            option = {
                                'ticker': ticker,
                                'option_type': 'PUT',
                                'strike': float(row.get('strike', 0)),
                                'expiry_date': datetime.strptime(expiry, '%Y-%m-%d').date(),
                                'bid': float(row.get('bid', 0)) if row.get('bid', 0) > 0 else None,
                                'ask': float(row.get('ask', 0)) if row.get('ask', 0) > 0 else None,
                                'last_price': float(row.get('lastPrice', 0)) if row.get('lastPrice', 0) > 0 else None,
                                'volume': int(row.get('volume', 0)) if row.get('volume', 0) else 0,
                                'open_interest': int(row.get('openInterest', 0)) if row.get('openInterest', 0) else 0,
                                'implied_volatility': float(row.get('impliedVolatility', 0)) if row.get('impliedVolatility', 0) > 0 else None,
                            }
                            
                            # Calculate mid price
                            if option['bid'] and option['ask']:
                                option['mid_price'] = (option['bid'] + option['ask']) / 2
                            elif option['last_price']:
                                option['mid_price'] = option['last_price']
                            else:
                                option['mid_price'] = None
                            
                            option['delta'] = None  # Will be calculated if needed
                            
                            options_data.append(option)
                        except Exception as e:
                            continue
                    
                except Exception as e:
                    print(f"  ⚠️  Error fetching {expiry}: {str(e)}")
                    continue
            
            return options_data
            
        except Exception as e:
            print(f"  ❌ Error fetching options for {ticker}: {str(e)}")
            return []
    
    @staticmethod
    def estimate_delta(option_type, strike, stock_price, dte, iv=None):
        """
        Rough delta estimation using simple moneyness approach
        More accurate with IV, but works without it
        
        Args:
            option_type: 'CALL' or 'PUT'
            strike: Strike price
            stock_price: Current stock price
            dte: Days to expiration
            iv: Implied volatility (optional)
        
        Returns:
            Estimated delta as float
        """
        if not stock_price or stock_price <= 0 or not strike:
            return 0.0
        
        # Calculate moneyness (percentage distance from strike)
        moneyness = (stock_price - strike) / stock_price
        
        # Simple delta estimation based on moneyness
        if option_type == 'CALL':
            if moneyness >= 0.1:  # 10% ITM
                delta = 0.8
            elif moneyness >= 0.05:  # 5% ITM
                delta = 0.6
            elif moneyness >= 0:  # ATM
                delta = 0.5
            elif moneyness >= -0.05:  # 5% OTM
                delta = 0.35
            elif moneyness >= -0.10:  # 10% OTM
                delta = 0.25
            else:  # Deep OTM
                delta = 0.15
        else:  # PUT
            if moneyness <= -0.1:  # 10% ITM
                delta = -0.8
            elif moneyness <= -0.05:  # 5% ITM
                delta = -0.6
            elif moneyness <= 0:  # ATM
                delta = -0.5
            elif moneyness <= 0.05:  # 5% OTM
                delta = -0.35
            elif moneyness <= 0.10:  # 10% OTM
                delta = -0.25
            else:  # Deep OTM
                delta = -0.15
        
        # Adjust for time decay (options lose delta as they approach expiration)
        if dte and dte < 7:
            time_factor = dte / 7
            delta = delta * (0.7 + 0.3 * time_factor)
        
        return round(delta, 4)

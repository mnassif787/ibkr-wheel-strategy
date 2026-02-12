"""
Technical Analysis Service for Wheel Strategy
Calculates RSI, EMA, Bollinger Bands, and detects support/resistance levels
Uses pure pandas/numpy - no external TA libraries needed
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal
import yfinance as yf
from typing import Dict, List, Optional, Tuple


class TechnicalAnalysisService:
    """Service for calculating technical indicators"""
    
    @staticmethod
    def fetch_historical_data(ticker: str, period: str = '6mo') -> Optional[pd.DataFrame]:
        """
        Fetch historical price data from Yahoo Finance
        
        Args:
            ticker: Stock ticker symbol
            period: Time period ('6mo', '1y', etc.)
            
        Returns:
            DataFrame with OHLCV data or None if error
        """
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            
            if df.empty:
                print(f"  ⚠️  No historical data for {ticker}")
                return None
            
            return df
        except Exception as e:
            print(f"  ❌ Error fetching historical data for {ticker}: {str(e)}")
            return None
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> Tuple[Optional[float], str]:
        """
        Calculate Relative Strength Index (14-period) using pure pandas
        
        Args:
            df: DataFrame with 'Close' prices
            period: RSI period (default 14)
            
        Returns:
            Tuple of (RSI value, signal: 'OVERSOLD'/'NEUTRAL'/'OVERBOUGHT')
        """
        try:
            # Calculate price changes
            delta = df['Close'].diff()
            
            # Separate gains and losses
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            # Calculate RS and RSI
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            current_rsi = rsi.iloc[-1]
            
            if pd.isna(current_rsi):
                return None, 'NEUTRAL'
            
            # Determine signal
            if current_rsi < 30:
                signal = 'OVERSOLD'
            elif current_rsi > 70:
                signal = 'OVERBOUGHT'
            else:
                signal = 'NEUTRAL'
            
            return float(current_rsi), signal
        except Exception as e:
            print(f"  ❌ RSI calculation error: {str(e)}")
            return None, 'NEUTRAL'
    
    @staticmethod
    def calculate_ema(df: pd.DataFrame, periods: List[int] = [50, 200]) -> Dict[str, Optional[float]]:
        """
        Calculate Exponential Moving Averages using pure pandas
        
        Args:
            df: DataFrame with 'Close' prices
            periods: List of EMA periods to calculate
            
        Returns:
            Dict with EMA values and trend signal
        """
        try:
            result = {}
            
            for period in periods:
                ema = df['Close'].ewm(span=period, adjust=False).mean()
                current_ema = ema.iloc[-1]
                result[f'ema_{period}'] = float(current_ema) if not pd.isna(current_ema) else None
            
            # Determine trend (50 EMA vs 200 EMA)
            if result.get('ema_50') and result.get('ema_200'):
                if result['ema_50'] > result['ema_200']:
                    result['ema_trend'] = 'BULLISH'
                elif result['ema_50'] < result['ema_200']:
                    result['ema_trend'] = 'BEARISH'
                else:
                    result['ema_trend'] = 'NEUTRAL'
            else:
                result['ema_trend'] = 'NEUTRAL'
            
            return result
        except Exception as e:
            print(f"  ❌ EMA calculation error: {str(e)}")
            return {'ema_50': None, 'ema_200': None, 'ema_trend': 'NEUTRAL'}
    
    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> Dict[str, Optional[float]]:
        """
        Calculate Bollinger Bands (20-period, 2 standard deviations) using pure pandas
        
        Args:
            df: DataFrame with 'Close' prices
            period: BB period (default 20)
            std: Standard deviations (default 2.0)
            
        Returns:
            Dict with upper, middle, lower bands and price position
        """
        try:
            # Calculate middle band (SMA)
            sma = df['Close'].rolling(window=period).mean()
            
            # Calculate standard deviation
            rolling_std = df['Close'].rolling(window=period).std()
            
            # Calculate upper and lower bands
            upper_band = sma + (rolling_std * std)
            lower_band = sma - (rolling_std * std)
            
            current_price = df['Close'].iloc[-1]
            bb_upper = upper_band.iloc[-1]
            bb_middle = sma.iloc[-1]
            bb_lower = lower_band.iloc[-1]
            
            # Determine price position
            if pd.isna(bb_upper) or pd.isna(bb_lower):
                position = ''
            elif current_price > bb_upper:
                position = 'Above Upper (Overbought)'
            elif current_price < bb_lower:
                position = 'Below Lower (Oversold)'
            elif current_price > bb_middle:
                position = 'Upper Half'
            else:
                position = 'Lower Half'
            
            return {
                'bb_upper': float(bb_upper) if not pd.isna(bb_upper) else None,
                'bb_middle': float(bb_middle) if not pd.isna(bb_middle) else None,
                'bb_lower': float(bb_lower) if not pd.isna(bb_lower) else None,
                'bb_position': position
            }
        except Exception as e:
            print(f"  ❌ Bollinger Bands calculation error: {str(e)}")
            return {
                'bb_upper': None,
                'bb_middle': None,
                'bb_lower': None,
                'bb_position': ''
            }
    
    @staticmethod
    def detect_support_resistance(df: pd.DataFrame, num_levels: int = 3) -> Dict[str, List[Optional[float]]]:
        """
        Detect support and resistance levels using local extrema
        
        Args:
            df: DataFrame with OHLCV data
            num_levels: Number of support/resistance levels to detect
            
        Returns:
            Dict with support and resistance levels
        """
        try:
            closes = df['Close'].values
            highs = df['High'].values
            lows = df['Low'].values
            
            # Find local minima (support) and maxima (resistance)
            support_levels = []
            resistance_levels = []
            
            # Use a rolling window to find local extrema
            window = 10  # Look for extrema in 10-day windows
            
            for i in range(window, len(closes) - window):
                # Check if it's a local minimum (support)
                if lows[i] == min(lows[i-window:i+window+1]):
                    support_levels.append(lows[i])
                
                # Check if it's a local maximum (resistance)
                if highs[i] == max(highs[i-window:i+window+1]):
                    resistance_levels.append(highs[i])
            
            # Cluster similar levels (within 2% of each other)
            def cluster_levels(levels, tolerance=0.02):
                if not levels:
                    return []
                
                levels = sorted(levels)
                clustered = []
                current_cluster = [levels[0]]
                
                for level in levels[1:]:
                    if abs(level - current_cluster[-1]) / current_cluster[-1] <= tolerance:
                        current_cluster.append(level)
                    else:
                        # Take median of cluster
                        clustered.append(np.median(current_cluster))
                        current_cluster = [level]
                
                # Add last cluster
                if current_cluster:
                    clustered.append(np.median(current_cluster))
                
                return clustered
            
            # Cluster and get strongest levels
            support_levels = cluster_levels(support_levels)
            resistance_levels = cluster_levels(resistance_levels)
            
            # Sort by proximity to current price and importance
            current_price = closes[-1]
            
            # For supports: prefer levels below current price
            supports_below = [s for s in support_levels if s < current_price]
            supports_below = sorted(supports_below, reverse=True)[:num_levels]
            
            # For resistance: prefer levels above current price
            resistance_above = [r for r in resistance_levels if r > current_price]
            resistance_above = sorted(resistance_above)[:num_levels]
            
            # Pad with None if not enough levels found
            while len(supports_below) < num_levels:
                supports_below.append(None)
            while len(resistance_above) < num_levels:
                resistance_above.append(None)
            
            return {
                'support_levels': [float(s) if s is not None else None for s in supports_below[:num_levels]],
                'resistance_levels': [float(r) if r is not None else None for r in resistance_above[:num_levels]]
            }
        except Exception as e:
            print(f"  ❌ Support/Resistance detection error: {str(e)}")
            return {
                'support_levels': [None] * num_levels,
                'resistance_levels': [None] * num_levels
            }
    
    @classmethod
    def calculate_all_indicators(cls, ticker: str) -> Optional[Dict]:
        """
        Calculate all technical indicators for a stock
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dict with all indicator values or None if error
        """
        try:
            # Fetch historical data
            df = cls.fetch_historical_data(ticker, period='6mo')
            if df is None or df.empty:
                return None
            
            # Calculate all indicators
            rsi_value, rsi_signal = cls.calculate_rsi(df)
            ema_data = cls.calculate_ema(df, periods=[50, 200])
            bb_data = cls.calculate_bollinger_bands(df)
            sr_data = cls.detect_support_resistance(df, num_levels=3)
            
            # Convert price history to JSON format (last 180 days)
            price_history = []
            for index, row in df.tail(180).iterrows():
                price_history.append({
                    'date': index.strftime('%Y-%m-%d'),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume'])
                })
            
            # Compile results
            result = {
                # RSI
                'rsi': Decimal(str(rsi_value)) if rsi_value else None,
                'rsi_signal': rsi_signal,
                
                # EMAs
                'ema_50': Decimal(str(ema_data['ema_50'])) if ema_data.get('ema_50') else None,
                'ema_200': Decimal(str(ema_data['ema_200'])) if ema_data.get('ema_200') else None,
                'ema_trend': ema_data.get('ema_trend', 'NEUTRAL'),
                
                # Bollinger Bands
                'bb_upper': Decimal(str(bb_data['bb_upper'])) if bb_data.get('bb_upper') else None,
                'bb_middle': Decimal(str(bb_data['bb_middle'])) if bb_data.get('bb_middle') else None,
                'bb_lower': Decimal(str(bb_data['bb_lower'])) if bb_data.get('bb_lower') else None,
                'bb_position': bb_data.get('bb_position', ''),
                
                # Support & Resistance
                'support_level_1': Decimal(str(sr_data['support_levels'][0])) if sr_data['support_levels'][0] else None,
                'support_level_2': Decimal(str(sr_data['support_levels'][1])) if sr_data['support_levels'][1] else None,
                'support_level_3': Decimal(str(sr_data['support_levels'][2])) if sr_data['support_levels'][2] else None,
                'resistance_level_1': Decimal(str(sr_data['resistance_levels'][0])) if sr_data['resistance_levels'][0] else None,
                'resistance_level_2': Decimal(str(sr_data['resistance_levels'][1])) if sr_data['resistance_levels'][1] else None,
                'resistance_level_3': Decimal(str(sr_data['resistance_levels'][2])) if sr_data['resistance_levels'][2] else None,
                
                # Price history
                'price_history': price_history
            }
            
            return result
        except Exception as e:
            print(f"  ❌ Error calculating indicators for {ticker}: {str(e)}")
            return None

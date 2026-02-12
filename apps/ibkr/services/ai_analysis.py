"""
AI-powered analysis and recommendations for wheel strategy
"""
from decimal import Decimal
from apps.ibkr.models import Stock, StockIndicator


class AIAnalyzer:
    """Provides AI-driven analysis and recommendations"""
    
    @staticmethod
    def get_stock_recommendation(stock):
        """
        Generate AI recommendation for a stock based on technical indicators
        Returns: dict with recommendation, confidence, reasoning, action
        """
        try:
            indicator = stock.indicators
        except StockIndicator.DoesNotExist:
            return {
                'recommendation': 'Calculate Indicators',
                'confidence': 0,
                'reasoning': 'Technical indicators need to be calculated first.',
                'action': 'neutral',
                'signals': []
            }
        
        signals = []
        bullish_score = 0
        bearish_score = 0
        
        # RSI Analysis (30 points)
        if indicator.rsi:
            if indicator.rsi < 30:
                signals.append('✅ RSI Oversold - Strong buy signal')
                bullish_score += 30
            elif indicator.rsi < 40:
                signals.append('✅ RSI Low - Bullish opportunity')
                bullish_score += 20
            elif indicator.rsi > 70:
                signals.append('⚠️ RSI Overbought - Caution advised')
                bearish_score += 30
            elif indicator.rsi > 60:
                signals.append('⚠️ RSI Elevated - Consider selling')
                bearish_score += 20
            else:
                signals.append('➖ RSI Neutral - Wait for better entry')
        
        # EMA Trend Analysis (25 points)
        if indicator.ema_trend == 'BULLISH':
            signals.append('✅ Bullish Trend - EMA 50 > EMA 200')
            bullish_score += 25
        elif indicator.ema_trend == 'BEARISH':
            signals.append('⚠️ Bearish Trend - EMA 50 < EMA 200')
            bearish_score += 25
        
        # Support/Resistance Analysis (25 points)
        if indicator.near_support:
            signals.append('✅ Near Support - Good entry point')
            bullish_score += 25
        elif indicator.near_resistance:
            signals.append('⚠️ Near Resistance - Consider taking profits')
            bearish_score += 25
        
        # Bollinger Bands Analysis (20 points)
        if indicator.bb_position == 'BELOW_LOWER':
            signals.append('✅ Below Lower Band - Oversold condition')
            bullish_score += 20
        elif indicator.bb_position == 'ABOVE_UPPER':
            signals.append('⚠️ Above Upper Band - Overbought condition')
            bearish_score += 20
        
        # Calculate final recommendation
        total_score = bullish_score - bearish_score
        confidence = min(abs(total_score), 100)
        
        if total_score > 50:
            recommendation = 'Strong Buy'
            action = 'buy'
            reasoning = f'Multiple bullish signals detected. Score: +{total_score}. Excellent opportunity for cash-secured puts.'
        elif total_score > 20:
            recommendation = 'Buy'
            action = 'buy'
            reasoning = f'Bullish indicators present. Score: +{total_score}. Good entry for wheel strategy.'
        elif total_score < -50:
            recommendation = 'Strong Sell / Avoid'
            action = 'sell'
            reasoning = f'Multiple bearish signals detected. Score: {total_score}. Not recommended for new positions.'
        elif total_score < -20:
            recommendation = 'Caution'
            action = 'sell'
            reasoning = f'Bearish indicators present. Score: {total_score}. Consider covered calls if assigned.'
        else:
            recommendation = 'Hold / Neutral'
            action = 'neutral'
            reasoning = f'Mixed signals. Score: {total_score}. Wait for clearer opportunity.'
        
        return {
            'recommendation': recommendation,
            'confidence': confidence,
            'reasoning': reasoning,
            'action': action,
            'signals': signals,
            'bullish_score': bullish_score,
            'bearish_score': bearish_score
        }
    
    @staticmethod
    def get_wheel_strategy_analysis(stock):
        """
        Specific analysis for wheel strategy suitability
        Returns: dict with strategy recommendation
        """
        analysis = AIAnalyzer.get_stock_recommendation(stock)
        
        wheel_signals = []
        wheel_score = 0
        
        # Check fundamentals
        if stock.dividend_yield and stock.dividend_yield > 2:
            wheel_signals.append('✅ Pays dividend - Extra income potential')
            wheel_score += 15
        
        if stock.beta and 0.8 <= stock.beta <= 1.2:
            wheel_signals.append('✅ Moderate volatility - Stable premiums')
            wheel_score += 15
        
        if stock.avg_volume and stock.avg_volume > 1000000:
            wheel_signals.append('✅ High liquidity - Easy entry/exit')
            wheel_score += 15
        
        if stock.market_cap and stock.market_cap > 10000000000:  # >$10B
            wheel_signals.append('✅ Large cap - Lower risk')
            wheel_score += 10
        
        # Check technical for wheel strategy
        try:
            indicator = stock.indicators
            
            if indicator.rsi and indicator.rsi < 40:
                wheel_signals.append('✅ RSI favorable - Good put selling opportunity')
                wheel_score += 20
            
            if indicator.ema_trend == 'BULLISH':
                wheel_signals.append('✅ Uptrend - Lower assignment risk')
                wheel_score += 15
            
            if indicator.near_support:
                wheel_signals.append('✅ Near support - Protected downside')
                wheel_score += 10
        except:
            pass
        
        # Determine wheel strategy rating
        if wheel_score >= 70:
            strategy_rating = 'Excellent for Wheel'
            strategy_color = 'green'
        elif wheel_score >= 50:
            strategy_rating = 'Good for Wheel'
            strategy_color = 'blue'
        elif wheel_score >= 30:
            strategy_rating = 'Fair for Wheel'
            strategy_color = 'yellow'
        else:
            strategy_rating = 'Not Ideal for Wheel'
            strategy_color = 'red'
        
        return {
            **analysis,
            'wheel_signals': wheel_signals,
            'wheel_score': wheel_score,
            'strategy_rating': strategy_rating,
            'strategy_color': strategy_color
        }

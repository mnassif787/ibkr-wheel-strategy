from django import template
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

register = template.Library()

@register.filter
def sub(value, arg):
    """Subtract arg from value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def add_decimal(value, arg):
    """Add arg to value"""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def mul(value, arg):
    """Multiply value by arg"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def div(value, arg):
    """Divide value by arg"""
    try:
        return float(value) / float(arg) if float(arg) != 0 else 0
    except (ValueError, TypeError):
        return value

@register.filter
def abs_value(value):
    """Return absolute value"""
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value

@register.filter
def calculate_apy(option):
    """Calculate annualized premium yield for an option"""
    try:
        if not option.mid_price or not option.strike or option.dte <= 0:
            return 0
        premium = float(option.mid_price)
        strike = float(option.strike)
        dte = option.dte
        apy = (premium / strike) * (365 / dte) * 100
        return round(apy, 1)
    except:
        return 0

@register.filter
def apy_from_premium(premium, strike_dte):
    """Calculate APY from premium. Args: premium|apy_from_premium:'strike,dte'"""
    try:
        if not premium or not strike_dte:
            return 0
        strike, dte = str(strike_dte).split(',')
        premium_val = float(premium)
        strike_val = float(strike)
        dte_val = int(float(dte))
        if dte_val <= 0 or strike_val <= 0:
            return 0
        apy = (premium_val / strike_val) * (365 / dte_val) * 100
        return round(apy, 1)
    except:
        return 0

@register.filter
def calculate_breakeven(option):
    """Calculate break-even price for an option"""
    try:
        if not option.mid_price or not option.strike:
            return option.strike
        premium = float(option.mid_price)
        strike = float(option.strike)
        if option.option_type == 'PUT':
            return round(strike - premium, 2)
        else:  # CALL
            return round(strike + premium, 2)
    except:
        return option.strike

@register.filter
def price_vs_strike_pct(option, stock_price):
    """Calculate percentage difference between strike and stock price"""
    try:
        if not stock_price or not option.strike:
            return 0
        strike = float(option.strike)
        price = float(stock_price)
        diff_pct = ((strike - price) / price) * 100
        return round(diff_pct, 1)
    except:
        return 0

@register.filter
def is_wheel_delta(option):
    """Check if option delta is in wheel strategy range (0.25-0.35)"""
    try:
        if not option.delta:
            return False
        delta_abs = abs(float(option.delta))
        return 0.25 <= delta_abs <= 0.35
    except:
        return False

@register.filter
def is_good_entry(option):
    """
    Determine if option is a good entry based on WHEEL STRATEGY criteria.
    
    *** REQUIRES technical indicators (RSI, support levels) to be calculated first ***
    Without indicators, options cannot be properly evaluated for wheel strategy.
    
    Evaluation criteria:
    1. Stock must have technical indicators (REQUIRED)
    2. Stock timing must be favorable (RSI, support proximity)
    3. Option metrics: Delta 0.25-0.35, APY >=15%, liquidity, DTE 21-45 days
    
    Returns: 'excellent', 'good', 'fair', 'poor'
    """
    try:
        stock = option.stock
        
        # STEP 1: Check if stock has technical indicators calculated
        # WITHOUT indicators, we cannot evaluate wheel strategy suitability
        if not hasattr(stock, 'indicators') or not stock.indicators:
            return 'poor'  # Cannot rate without indicators
        
        indicator = stock.indicators
        
        # Check for required indicator data
        if not indicator.rsi or not indicator.support_level_1:
            return 'poor'  # Incomplete technical data
        
        # STEP 2: Check stock-level wheel strategy readiness
        # Even if option metrics are good, stock timing must be right
        
        # Overbought RSI = bad time to sell puts (high assignment risk)
        if indicator.rsi > 70:
            return 'poor'  # Don't sell puts when overbought
        
        # STEP 3: Evaluate option-specific criteria
        score = 0
        max_score = 5
        
        # Check delta (most important for wheel strategy)
        if option.delta:
            delta_abs = abs(float(option.delta))
            if 0.25 <= delta_abs <= 0.35:
                score += 2  # Perfect delta range for wheel
            elif 0.20 <= delta_abs <= 0.40:
                score += 1  # Acceptable range
        
        # Check APY (premium quality)
        if option.mid_price and option.strike and option.dte > 0:
            apy = (float(option.mid_price) / float(option.strike)) * (365 / option.dte) * 100
            if apy >= 20:
                score += 1
            elif apy >= 15:
                score += 0.5
        
        # Check liquidity
        if option.volume >= 10 or option.open_interest >= 50:
            score += 1
        
        # Check DTE (sweet spot: 21-45 days)
        if 21 <= option.dte <= 45:
            score += 1
        elif 14 <= option.dte <= 60:
            score += 0.5
        
        # Determine base rating
        if score >= 4:
            base_rating = 'excellent'
        elif score >= 3:
            base_rating = 'good'
        elif score >= 2:
            base_rating = 'fair'
        else:
            base_rating = 'poor'
        
        # STEP 4: Adjust rating based on stock conditions
        # Downgrade if RSI is not ideal (want oversold/neutral for puts)
        if indicator.rsi > 60 and base_rating == 'excellent':
            base_rating = 'good'  # Downgrade: stock not in ideal zone
        
        # Downgrade if near resistance (risky for put selling)
        if indicator.resistance_level_1 and stock.last_price:
            try:
                price = float(stock.last_price)
                resistance = float(indicator.resistance_level_1)
                distance_to_resistance = ((resistance - price) / price) * 100
                
                if distance_to_resistance < 3:  # Within 3% of resistance
                    if base_rating == 'excellent':
                        base_rating = 'good'  # Downgrade: too close to resistance
                    elif base_rating == 'good':
                        base_rating = 'fair'
            except:
                pass
        
        return base_rating
        
    except Exception as e:
        return 'poor'  # Safe default if any error

@register.filter
def connection_status(last_updated):
    """
    Determine connection status based on last update time:
    - live: Updated within last 5 minutes
    - delayed: Updated 5-60 minutes ago
    - disconnected: Updated over 60 minutes ago or never
    """
    try:
        if not last_updated:
            return 'disconnected'
        
        now = timezone.now()
        time_diff = now - last_updated
        
        if time_diff < timedelta(minutes=5):
            return 'live'
        elif time_diff < timedelta(hours=1):
            return 'delayed'
        else:
            return 'disconnected'
    except:
        return 'disconnected'

@register.filter
def time_since_update(last_updated):
    """Return human-readable time since last update"""
    try:
        if not last_updated:
            return 'Never'
        
        now = timezone.now()
        time_diff = now - last_updated
        
        if time_diff < timedelta(minutes=1):
            return 'Just now'
        elif time_diff < timedelta(hours=1):
            minutes = int(time_diff.total_seconds() / 60)
            return f'{minutes} min ago'
        elif time_diff < timedelta(days=1):
            hours = int(time_diff.total_seconds() / 3600)
            return f'{hours} hour{"s" if hours != 1 else ""} ago'
        else:
            days = time_diff.days
            return f'{days} day{"s" if days != 1 else ""} ago'
    except:
        return 'Unknown'

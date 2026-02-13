from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.db.models import Avg
from django.views.decorators.http import require_POST
from decimal import Decimal
import csv
import json
from datetime import datetime
from .models import Stock, Option, Signal, Watchlist, UserConfig, OptionPosition, StockWheelScore
from .services.stock_data_fetcher import StockDataFetcher
from .services.ai_analysis import AIAnalyzer
from .services.ibkr_client import IBKRClient
from .services.position_analyzer import PositionAnalyzer


def hub(request):
    """Main hub with tabs for positions, discovery (stocks/options/signals)"""
    # Get all data for all tabs
    # Get last updated time from any stock
    last_updated = Stock.objects.filter(last_updated__isnull=False).order_by('-last_updated').values_list('last_updated', flat=True).first()
    
    # POSITIONS TAB DATA
    open_positions = OptionPosition.objects.filter(status='OPEN').select_related('stock').order_by('-entry_date')
    closed_positions = OptionPosition.objects.exclude(status='OPEN').select_related('stock').order_by('-exit_date')[:10]
    
    # Update current_premium for open positions using live/delayed quotes
    try:
        client = IBKRClient()
        if client.ensure_connected():
            from decimal import Decimal
            for position in open_positions:
                try:
                    expiry_str = position.expiry_date.strftime('%Y%m%d')
                    right = 'P' if position.option_type == 'PUT' else 'C'
                    quote = client.get_option_quote(
                        position.stock.ticker, expiry_str,
                        float(position.strike), right
                    )
                    if quote:
                        price = quote.get('mid') or quote.get('last')
                        if price and price > 0:
                            position.current_premium = Decimal(str(price))
                            position.save(update_fields=['current_premium'])
                except Exception as e:
                    logger.warning(f"Could not fetch quote for {position}: {e}")
    except Exception as e:
        logger.warning(f"Could not update position premiums: {e}")
    
    # Add AI recommendations and enhanced analysis to positions
    for position in open_positions:
        # Get stock recommendation
        stock_rec = AIAnalyzer.get_stock_recommendation(position.stock)
        position.ai_recommendation = {
            'action': stock_rec['recommendation'],
            'confidence': stock_rec['confidence'],
            'reason': stock_rec['reasoning'],
            'color': 'green' if stock_rec['action'] == 'buy' else ('red' if stock_rec['action'] == 'sell' else 'yellow')
        }
        
        # Add enhanced position analysis
        position.analysis = PositionAnalyzer.analyze_position(position)
    
    # STOCKS TAB DATA
    stocks = Stock.objects.select_related('indicators').prefetch_related('options').all()
    stock_scores = []
    for stock in stocks:
        score_data = calculate_wheel_score(stock)
        stock.wheel_score = score_data['total_score']
        stock.score_breakdown = score_data
        
        entry_signal = calculate_entry_signal(stock)
        stock.entry_signal = entry_signal['signal']
        stock.entry_quality = entry_signal['quality']
        stock.entry_score = entry_signal['score']
        stock.entry_color = entry_signal['signal_color']
        
        stock_scores.append(stock)
    
    # Apply stock filters if provided
    grade_filter = request.GET.get('grade', 'all')
    price_range = request.GET.get('price_range', 'all')
    
    if grade_filter != 'all':
        stock_scores = [s for s in stock_scores if s.score_breakdown['grade'] == grade_filter]
    
    if price_range == 'sweet_spot':
        stock_scores = [s for s in stock_scores if s.last_price and 10 <= float(s.last_price) <= 50]
    elif price_range == 'under_50':
        stock_scores = [s for s in stock_scores if s.last_price and float(s.last_price) < 50]
    elif price_range == 'over_100':
        stock_scores = [s for s in stock_scores if s.last_price and float(s.last_price) > 100]
    
    # Sort stocks
    sort_by = request.GET.get('sort', 'wheel_score')
    if sort_by == 'wheel_score':
        stock_scores.sort(key=lambda x: x.wheel_score, reverse=True)
    elif sort_by == 'price':
        stock_scores.sort(key=lambda x: float(x.last_price) if x.last_price else 0, reverse=True)
    
    # OPTIONS TAB DATA
    selected_ticker = request.GET.get('ticker', '')
    selected_stock = None
    options = []
    available_stocks = Stock.objects.filter(options__isnull=False).distinct().order_by('ticker')
    
    if selected_ticker:
        selected_stock = Stock.objects.filter(ticker=selected_ticker).first()
        if selected_stock:
            options = Option.objects.filter(stock=selected_stock).order_by('expiry_date', 'strike')[:50]
    
    # SIGNALS TAB DATA
    signals = Signal.objects.filter(status='OPEN').select_related('stock', 'option').order_by('-quality_score')[:20]
    
    context = {
        'last_updated': last_updated,
        # Positions
        'open_positions': open_positions,
        'closed_positions': closed_positions,
        # Stocks
        'stocks': stock_scores,
        'sort_by': sort_by,
        'grade_filter': grade_filter,
        'price_range': price_range,
        # Options
        'selected_ticker': selected_ticker,
        'selected_stock': selected_stock,
        'options': options,
        'available_stocks': available_stocks,
        # Signals
        'signals': signals,
    }
    
    return render(request, 'ibkr/hub.html', context)


def dashboard(request):
    """Main IBKR dashboard with AI insights"""
    # Get watchlist tickers
    watchlist = Watchlist.objects.all()
    watchlist_tickers = list(watchlist.values_list('ticker', flat=True))
    
    # Only show stocks that are in the watchlist
    stocks = Stock.objects.filter(ticker__in=watchlist_tickers).select_related('indicators').order_by('-last_updated')[:10]
    
    # Add AI analysis to each stock
    for stock in stocks:
        stock.ai_analysis = AIAnalyzer.get_wheel_strategy_analysis(stock)
    
    signals = Signal.objects.filter(status='OPEN').select_related('stock', 'option').order_by('-quality_score')[:10]
    
    context = {
        'stocks': stocks,
        'signals': signals,
        'watchlist': watchlist,
        'total_stocks': Stock.objects.filter(ticker__in=watchlist_tickers).count(),
        'total_signals': Signal.objects.filter(status='OPEN').count(),
    }
    return render(request, 'ibkr/dashboard.html', context)


def stocks_list(request):
    """List all stocks with wheel strategy scoring and filtering - scans entire market"""
    cache_key = f"wheel_scores_{request.GET.urlencode()}"
    cached_data = cache.get(cache_key)
    
    if cached_data:
        return render(request, 'ibkr/stocks.html', cached_data)
    
    # Scan ALL stocks in database, not just watchlist
    stocks = Stock.objects.select_related('indicators').prefetch_related('options').all()
    
    # Calculate wheel scores and entry signals for each stock
    stock_scores = []
    for stock in stocks:
        stock.ai_analysis = AIAnalyzer.get_wheel_strategy_analysis(stock)
        score_data = calculate_wheel_score(stock)
        stock.wheel_score = score_data['total_score']
        stock.score_breakdown = score_data
        
        # Calculate entry timing signal
        entry_signal = calculate_entry_signal(stock)
        stock.entry_signal = entry_signal['signal']
        stock.entry_quality = entry_signal['quality']
        stock.entry_score = entry_signal['score']
        stock.entry_reasons = entry_signal['reasons']
        stock.entry_color = entry_signal['signal_color']
        
        stock_scores.append(stock)
        
        # Save to history (daily - check if already saved today)
        today = timezone.now().date()
        if not StockWheelScore.objects.filter(stock=stock, calculated_at__date=today).exists():
            StockWheelScore.objects.create(
                stock=stock,
                total_score=score_data['total_score'],
                volatility_score=score_data['volatility_score'],
                liquidity_score=score_data['liquidity_score'],
                technical_score=score_data['technical_score'],
                stability_score=score_data['stability_score'],
                price_score=score_data['price_score'],
                grade=score_data['grade']
            )
        
        # Add trend
        latest_score = StockWheelScore.objects.filter(stock=stock).first()
        stock.score_trend = latest_score.score_trend if latest_score else 'stable'
    
    # Get filter parameters
    grade_filter = request.GET.get('grade', 'all')
    price_range = request.GET.get('price_range', 'all')
    min_score = request.GET.get('min_score', 0)
    
    # Apply filters
    if grade_filter != 'all':
        stock_scores = [s for s in stock_scores if s.score_breakdown['grade'] == grade_filter]
    
    if price_range == 'sweet_spot':
        stock_scores = [s for s in stock_scores if s.last_price and 10 <= float(s.last_price) <= 50]
    elif price_range == 'under_50':
        stock_scores = [s for s in stock_scores if s.last_price and float(s.last_price) < 50]
    elif price_range == 'over_100':
        stock_scores = [s for s in stock_scores if s.last_price and float(s.last_price) > 100]
    
    if min_score:
        stock_scores = [s for s in stock_scores if s.wheel_score >= int(min_score)]
    
    # Get sort parameter and sort
    sort_by = request.GET.get('sort', 'wheel_score')
    
    if sort_by == 'wheel_score':
        stock_scores.sort(key=lambda x: x.wheel_score, reverse=True)
    elif sort_by == 'volatility':
        stock_scores.sort(key=lambda x: x.score_breakdown['volatility_score'], reverse=True)
    elif sort_by == 'liquidity':
        stock_scores.sort(key=lambda x: x.score_breakdown['liquidity_score'], reverse=True)
    elif sort_by == 'technical':
        stock_scores.sort(key=lambda x: x.score_breakdown['technical_score'], reverse=True)
    elif sort_by == 'stability':
        stock_scores.sort(key=lambda x: x.score_breakdown['stability_score'], reverse=True)
    elif sort_by == 'price':
        stock_scores.sort(key=lambda x: float(x.last_price) if x.last_price else 0, reverse=True)
    elif sort_by == 'entry_signal':
        stock_scores.sort(key=lambda x: x.entry_score, reverse=True)
    
    context = {
        'stocks': stock_scores,
        'sort_by': sort_by,
        'grade_filter': grade_filter,
        'price_range': price_range,
        'min_score': min_score,
    }
    
    # Cache for 5 minutes
    cache.set(cache_key, context, 300)
    
    return render(request, 'ibkr/stocks.html', context)


def calculate_wheel_score(stock):
    """
    Calculate multi-factor blended score for wheel strategy suitability
    
    Factors:
    1. Volatility Score (25%) - Higher IV = better premiums
    2. Liquidity Score (20%) - Volume and options availability
    3. Technical Score (25%) - RSI, trend, support levels
    4. Stability Score (20%) - Market cap, beta, fundamentals
    5. Price Level Score (10%) - Affordable for cash-secured puts
    
    Returns score 0-100
    """
    scores = {
        'volatility_score': 0,
        'liquidity_score': 0,
        'technical_score': 0,
        'stability_score': 0,
        'price_score': 0,
        'total_score': 0,
    }
    
    # 1. Volatility Score (25%) - Check IV from options
    if stock.options.exists():
        avg_iv = stock.options.filter(
            option_type='PUT',
            implied_volatility__isnull=False
        ).aggregate(Avg('implied_volatility'))['implied_volatility__avg']
        
        if avg_iv:
            iv_pct = float(avg_iv) * 100
            if iv_pct > 50:  # Very high IV
                scores['volatility_score'] = 25
            elif iv_pct > 35:  # High IV
                scores['volatility_score'] = 20
            elif iv_pct > 25:  # Moderate IV
                scores['volatility_score'] = 15
            elif iv_pct > 15:  # Low IV
                scores['volatility_score'] = 10
            else:  # Very low IV
                scores['volatility_score'] = 5
    
    # 2. Liquidity Score (20%)
    liquidity_points = 0
    if stock.avg_volume:
        if stock.avg_volume > 10_000_000:
            liquidity_points += 10
        elif stock.avg_volume > 5_000_000:
            liquidity_points += 8
        elif stock.avg_volume > 1_000_000:
            liquidity_points += 6
        elif stock.avg_volume > 500_000:
            liquidity_points += 4
        else:
            liquidity_points += 2
    
    # Check options liquidity (open interest)
    if stock.options.exists():
        avg_oi = stock.options.filter(
            option_type='PUT',
            open_interest__gt=0
        ).aggregate(Avg('open_interest'))['open_interest__avg']
        
        if avg_oi:
            if avg_oi > 1000:
                liquidity_points += 10
            elif avg_oi > 500:
                liquidity_points += 8
            elif avg_oi > 100:
                liquidity_points += 6
            elif avg_oi > 50:
                liquidity_points += 4
            else:
                liquidity_points += 2
    
    scores['liquidity_score'] = min(liquidity_points, 20)
    
    # 3. Technical Score (25%) - Prioritize Weekly Wheel Strategy criteria
    technical_points = 0
    if hasattr(stock, 'indicators') and stock.indicators:
        ind = stock.indicators
        
        # RSI analysis - Weekly Wheel Strategy prefers RSI < 35 (oversold)
        if ind.rsi:
            if ind.rsi < 35:  # Oversold - PRIME for weekly CSPs
                technical_points += 15
            elif ind.rsi < 50:  # Weak - GOOD for weekly CSPs
                technical_points += 12
            elif ind.rsi < 65:  # Neutral - wait for better entry
                technical_points += 8
            elif ind.rsi < 75:  # Elevated - caution
                technical_points += 4
            else:  # Overbought > 75 - avoid
                technical_points += 1
        
        # EMA trend - BULLISH (above 50-day EMA) is ideal for wheel strategy
        if ind.ema_trend == 'BULLISH':
            technical_points += 10  # Above 50-day EMA requirement
        elif ind.ema_trend == 'NEUTRAL':
            technical_points += 5
        else:
            technical_points += 0  # Below 50-day EMA is not ideal
    
    scores['technical_score'] = min(technical_points, 25)
    
    # 4. Stability Score (20%)
    stability_points = 0
    
    # Market cap (larger = more stable)
    if stock.market_cap:
        if stock.market_cap > 100_000_000_000:  # >100B
            stability_points += 8
        elif stock.market_cap > 10_000_000_000:  # >10B
            stability_points += 6
        elif stock.market_cap > 2_000_000_000:  # >2B
            stability_points += 4
        else:
            stability_points += 2
    
    # Beta (lower = less volatile, more stable)
    if stock.beta:
        if stock.beta < 0.8:
            stability_points += 6
        elif stock.beta < 1.2:
            stability_points += 4
        else:
            stability_points += 2
    
    # Dividend yield (income stocks are more stable)
    if stock.dividend_yield and stock.dividend_yield > 0:
        if stock.dividend_yield > 0.03:  # >3%
            stability_points += 6
        elif stock.dividend_yield > 0.01:  # >1%
            stability_points += 4
        else:
            stability_points += 2
    
    scores['stability_score'] = min(stability_points, 20)
    
    # 5. Price Level Score (10%) - Affordability for cash-secured puts
    if stock.last_price:
        price = float(stock.last_price)
        if 10 <= price <= 50:  # Sweet spot for wheel strategy
            scores['price_score'] = 10
        elif 5 <= price < 10 or 50 < price <= 100:
            scores['price_score'] = 7
        elif 100 < price <= 200:
            scores['price_score'] = 5
        elif price < 5:  # Too cheap, often risky
            scores['price_score'] = 3
        else:  # Very expensive
            scores['price_score'] = 2
    
    # Calculate total score
    scores['total_score'] = int(sum([
        scores['volatility_score'],
        scores['liquidity_score'],
        scores['technical_score'],
        scores['stability_score'],
        scores['price_score']
    ]))
    
    # Add grade
    if scores['total_score'] >= 80:
        scores['grade'] = 'A'
        scores['grade_color'] = 'green'
    elif scores['total_score'] >= 65:
        scores['grade'] = 'B'
        scores['grade_color'] = 'blue'
    elif scores['total_score'] >= 50:
        scores['grade'] = 'C'
        scores['grade_color'] = 'yellow'
    else:
        scores['grade'] = 'D'
        scores['grade_color'] = 'red'
    
    return scores


def calculate_entry_signal(stock):
    """
    Calculate entry signal for WHEEL STRATEGY - Selling Cash-Secured PUTS
    
    This tells you if NOW is a good time to SELL PUTS for wheel strategy.
    
    Wheel Strategy Goal: Sell puts to collect premium OR get assigned at good price
    Best Timing: Stock near support, RSI oversold/neutral, high IV for premium
    
    Factors:
    1. Technical Setup (40%) - RSI (want oversold/neutral), support proximity, trend
    2. Options Premium (30%) - IV levels (higher = better premium), open interest
    3. Market Context (20%) - 52-week position (lower = better), Bollinger Bands
    4. Risk Factors (penalty) - Near resistance (bad for puts), overbought RSI
    
    Returns signal: SELL PUT NOW, WAIT, AVOID with quality rating 0-100
    """
    signal_data = {
        'signal': 'WAIT',
        'quality': 'FAIR',
        'score': 0,
        'reasons': [],
        'signal_color': 'gray'
    }
    
    score = 0
    reasons = []
    
    if not hasattr(stock, 'indicators') or not stock.indicators:
        signal_data['signal'] = 'NO_DATA'
        signal_data['quality'] = 'N/A'
        signal_data['reasons'] = ['Technical indicators need to be calculated']
        return signal_data
    
    ind = stock.indicators
    
    # 1. Technical Setup (40 points)
    technical_score = 0
    
    # RSI - Best entries when oversold (< 35) per Weekly Wheel Strategy
    if ind.rsi:
        if ind.rsi < 35:  # Oversold - EXCELLENT for weekly CSPs
            technical_score += 20
            reasons.append(f"✅ RSI oversold ({ind.rsi:.1f}) - prime time for CSPs!")
        elif 35 <= ind.rsi < 50:  # Weak - GOOD for CSPs
            technical_score += 15
            reasons.append(f"✅ RSI favorable ({ind.rsi:.1f}) - good CSP entry")
        elif 50 <= ind.rsi < 65:  # Neutral - wait for better entry
            technical_score += 8
            reasons.append(f"⏳ RSI neutral ({ind.rsi:.1f}) - wait for dip")
        elif 65 <= ind.rsi < 75:  # Elevated - caution
            technical_score += 3
            reasons.append(f"⚠️ RSI elevated ({ind.rsi:.1f}) - not ideal")
        else:  # Overbought > 75 - avoid
            technical_score += 0
            reasons.append(f"❌ RSI overbought ({ind.rsi:.1f}) - avoid CSPs!")
    
    # Price vs Support - Best when near support
    if ind.support_level_1 and stock.last_price:
        distance_to_support = ((float(stock.last_price) - float(ind.support_level_1)) / float(ind.support_level_1)) * 100
        if distance_to_support < 3:  # Within 3% of support
            technical_score += 15
            reasons.append(f"✅ Near support ${ind.support_level_1} ({distance_to_support:.1f}% away)")
        elif distance_to_support < 8:  # Within 8% of support
            technical_score += 10
            reasons.append(f"↔️ Close to support ${ind.support_level_1} ({distance_to_support:.1f}% away)")
        elif distance_to_support < 15:  # Within 15% of support
            technical_score += 5
            reasons.append(f"⚠️ Moderate distance from support ({distance_to_support:.1f}%)")
    
    # Trend alignment - Above 50-day EMA (BULLISH) is REQUIRED for Weekly Wheel Strategy
    if ind.ema_trend == 'BULLISH':
        technical_score += 10
        reasons.append("✅ Above 50-day EMA - ideal for weekly wheel")
    elif ind.ema_trend == 'NEUTRAL':
        technical_score += 5
        reasons.append("↔️ Neutral trend - acceptable")
    else:
        technical_score += 0
        reasons.append("⚠️ Below 50-day EMA - not ideal for CSPs")
    
    score += min(technical_score, 40)
    
    # 2. Options Premium (30 points)
    premium_score = 0
    
    if stock.options.exists():
        # Check current IV levels
        avg_iv = stock.options.filter(
            option_type='PUT',
            implied_volatility__isnull=False
        ).aggregate(Avg('implied_volatility'))['implied_volatility__avg']
        
        if avg_iv:
            iv_pct = float(avg_iv) * 100
            if iv_pct > 40:  # High IV - great premiums
                premium_score += 20
                reasons.append(f"✅ High IV ({iv_pct:.1f}%) - excellent premiums")
            elif iv_pct > 25:  # Moderate IV
                premium_score += 15
                reasons.append(f"✅ Moderate IV ({iv_pct:.1f}%) - good premiums")
            elif iv_pct > 15:  # Low IV
                premium_score += 8
                reasons.append(f"↔️ Low IV ({iv_pct:.1f}%) - limited premiums")
            else:  # Very low IV
                premium_score += 3
                reasons.append(f"❌ Very low IV ({iv_pct:.1f}%) - poor premiums")
        
        # Check options liquidity for easy entry/exit
        avg_oi = stock.options.filter(
            option_type='PUT',
            open_interest__gt=0
        ).aggregate(Avg('open_interest'))['open_interest__avg']
        
        if avg_oi:
            if avg_oi > 500:
                premium_score += 10
                reasons.append(f"✅ High liquidity (OI: {int(avg_oi)})")
            elif avg_oi > 100:
                premium_score += 7
                reasons.append(f"↔️ Moderate liquidity (OI: {int(avg_oi)})")
            else:
                premium_score += 3
                reasons.append(f"⚠️ Low liquidity (OI: {int(avg_oi)})")
    
    score += min(premium_score, 30)
    
    # 3. Market Context (20 points)
    context_score = 0
    
    # Check if price is in lower half of 52-week range (better entry)
    if stock.fifty_two_week_high and stock.fifty_two_week_low and stock.last_price:
        range_position = ((float(stock.last_price) - float(stock.fifty_two_week_low)) / 
                         (float(stock.fifty_two_week_high) - float(stock.fifty_two_week_low))) * 100
        
        if range_position < 30:  # Lower 30% of range
            context_score += 15
            reasons.append(f"✅ Near 52-week low ({range_position:.0f}% of range)")
        elif range_position < 50:  # Lower half
            context_score += 10
            reasons.append(f"↔️ Below mid-range ({range_position:.0f}% of range)")
        elif range_position < 70:  # Upper half
            context_score += 5
            reasons.append(f"⚠️ In upper range ({range_position:.0f}% of range)")
        else:  # Near 52-week high
            context_score += 0
            reasons.append(f"❌ Near 52-week high ({range_position:.0f}% of range)")
    
    # Volatility regime check
    if ind.bb_position:
        if ind.bb_position == 'BELOW_LOWER':
            context_score += 5
            reasons.append("✅ Below lower Bollinger Band - oversold")
        elif ind.bb_position == 'MIDDLE':
            context_score += 3
            reasons.append("↔️ Mid Bollinger Band range")
        elif ind.bb_position == 'ABOVE_UPPER':
            context_score += 0
            reasons.append("❌ Above upper Bollinger Band - overbought")
    
    score += min(context_score, 20)
    
    # 4. Risk Factors (10 points deduction)
    risk_penalty = 0
    
    # Near resistance is a risk
    if ind.resistance_level_1 and stock.last_price:
        distance_to_resistance = ((float(ind.resistance_level_1) - float(stock.last_price)) / float(stock.last_price)) * 100
        if distance_to_resistance < 3:
            risk_penalty += 5
            reasons.append(f"⚠️ Near resistance ${ind.resistance_level_1} - risk of rejection")
    
    # Extreme overbought is risky (> 70 per Weekly Wheel Strategy)
    if ind.rsi and ind.rsi > 70:
        risk_penalty += 7
        reasons.append("⚠️ Overbought (RSI > 70) - avoid selling CSPs!")
    
    score = max(0, score - risk_penalty) + 10  # Add base 10 points
    
    # Determine signal based on score - Weekly Wheel Strategy criteria
    # Score 75+ = RSI < 35, Above EMA, High IV, Near Support = SELL CSPs NOW
    if score >= 75:
        signal_data['signal'] = 'SELL PUT NOW'
        signal_data['quality'] = 'EXCELLENT'
        signal_data['signal_color'] = 'green'
    elif score >= 60:
        signal_data['signal'] = 'GOOD ENTRY'
        signal_data['quality'] = 'GOOD'
        signal_data['signal_color'] = 'blue'
    elif score >= 45:
        signal_data['signal'] = 'WAIT FOR DIP'
        signal_data['quality'] = 'FAIR'
        signal_data['signal_color'] = 'yellow'
    else:
        signal_data['signal'] = 'AVOID'
        signal_data['quality'] = 'POOR'
        signal_data['signal_color'] = 'red'
    
    signal_data['score'] = int(score)
    signal_data['reasons'] = reasons
    
    return signal_data


def export_wheel_scores(request):
    """Export top stocks with wheel scores to CSV"""
    stocks = Stock.objects.select_related('indicators').prefetch_related('options').all()
    
    stock_scores = []
    for stock in stocks:
        score_data = calculate_wheel_score(stock)
        stock.wheel_score = score_data['total_score']
        stock.score_breakdown = score_data
        stock_scores.append(stock)
    
    # Sort by wheel score
    stock_scores.sort(key=lambda x: x.wheel_score, reverse=True)
    
    # Take top 10 or filtered set
    limit = int(request.GET.get('limit', 10))
    stock_scores = stock_scores[:limit]
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="wheel_scores_{datetime.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Ticker', 'Name', 'Price', 'Total Score', 'Grade',
        'Volatility Score', 'Liquidity Score', 'Technical Score', 
        'Stability Score', 'Price Score', 'RSI', 'IV Avg', 'Volume'
    ])
    
    for stock in stock_scores:
        avg_iv = stock.options.filter(
            option_type='PUT',
            implied_volatility__isnull=False
        ).aggregate(Avg('implied_volatility'))['implied_volatility__avg']
        
        rsi = stock.indicators.rsi if hasattr(stock, 'indicators') and stock.indicators else None
        
        writer.writerow([
            stock.ticker,
            stock.name,
            float(stock.last_price) if stock.last_price else '',
            stock.wheel_score,
            stock.score_breakdown['grade'],
            stock.score_breakdown['volatility_score'],
            stock.score_breakdown['liquidity_score'],
            stock.score_breakdown['technical_score'],
            stock.score_breakdown['stability_score'],
            stock.score_breakdown['price_score'],
            round(rsi, 2) if rsi else '',
            round(float(avg_iv) * 100, 2) if avg_iv else '',
            stock.avg_volume or ''
        ])
    
    return response


def options_list(request, ticker=None):
    """List options for a ticker with AI analysis"""
    if ticker:
        stock = get_object_or_404(Stock, ticker=ticker.upper())
        
        # Get filter parameters
        expiry_filter = request.GET.get('expiry', 'all')
        
        # Calculate wheel score and entry signal (consistent with screener)
        try:
            wheel_score_data = calculate_wheel_score(stock)
            entry_signal_data = calculate_entry_signal(stock)
            
            stock.ai_analysis = {
                'wheel_score': wheel_score_data['total_score'],
                'grade': wheel_score_data['grade'],
                'strategy_rating': f"Grade {wheel_score_data['grade']}" if wheel_score_data['total_score'] >= 50 else "Not Recommended",
                'strategy_color': wheel_score_data['grade_color'],
                'wheel_signals': [],
                'signals': [],
                'action': 'buy' if entry_signal_data['score'] >= 60 else 'wait' if entry_signal_data['score'] >= 45 else 'avoid',
                'confidence': entry_signal_data['score'],
                'reasoning': f"{entry_signal_data['signal']} - {entry_signal_data['quality']} quality"
            }
            
            # Add signals
            if wheel_score_data['volatility_score'] >= 20:
                stock.ai_analysis['wheel_signals'].append(f"✅ High IV - Great premiums")
            if wheel_score_data['liquidity_score'] >= 15:
                stock.ai_analysis['wheel_signals'].append(f"✅ High liquidity")
            if wheel_score_data['technical_score'] >= 18:
                stock.ai_analysis['wheel_signals'].append(f"✅ Strong technicals")
            
            if hasattr(stock, 'indicators') and stock.indicators:
                ind = stock.indicators
                if ind.rsi and ind.rsi < 40:
                    stock.ai_analysis['signals'].append(f"RSI {ind.rsi:.1f} - Good for puts")
                if ind.ema_trend:
                    stock.ai_analysis['signals'].append(f"Trend: {ind.ema_trend}")
        except Exception as e:
            stock.ai_analysis = {
                'recommendation': 'Calculate Indicators',
                'confidence': 0,
                'reasoning': 'Technical indicators need to be calculated first.',
                'action': 'neutral',
                'signals': [],
                'wheel_signals': [f'Run: python manage.py calculate_indicators --ticker={stock.ticker}'],
                'wheel_score': 0,
                'strategy_rating': 'Pending Analysis',
                'strategy_color': 'gray'
            }
        
        options = Option.objects.filter(stock=stock, option_type='PUT')
        
        # Apply expiry filter
        today = timezone.now().date()
        if expiry_filter == '7d':
            options = options.filter(expiry_date__lte=today + timezone.timedelta(days=7))
        elif expiry_filter == '30d':
            options = options.filter(expiry_date__lte=today + timezone.timedelta(days=30))
        elif expiry_filter == '60d':
            options = options.filter(expiry_date__lte=today + timezone.timedelta(days=60))
        elif expiry_filter == '90d':
            options = options.filter(expiry_date__lte=today + timezone.timedelta(days=90))
        
        options = options.order_by('expiry_date', 'strike')
    else:
        options = Option.objects.filter(option_type='PUT').order_by('-last_updated')[:50]
        stock = None
        expiry_filter = 'all'
    
    return render(request, 'ibkr/options.html', {
        'options': options,
        'stock': stock,
        'expiry_filter': expiry_filter
    })


def signals_list(request):
    """List all signals with quality scores"""
    signals = Signal.objects.select_related('stock').order_by('-quality_score', '-generated_at')
    # Get stocks for timestamp display
    stocks = Stock.objects.order_by('-last_updated')[:1]
    return render(request, 'ibkr/signals.html', {'signals': signals, 'stocks': stocks})


def discovery(request):
    """Discover wheel strategy opportunities with recommended entry strikes"""
    # Get filter parameters
    min_score = int(request.GET.get('min_score', 0))
    rsi_signal = request.GET.get('rsi_signal', 'all')
    trend = request.GET.get('trend', 'all')
    
    # Get all stocks with indicators
    stocks = Stock.objects.select_related('indicators').exclude(last_price__isnull=True)
    
    opportunities = []
    
    for stock in stocks:
        try:
            # Get indicators
            indicator = stock.indicators
            
            # Apply filters
            if rsi_signal != 'all' and indicator.rsi_signal != rsi_signal:
                continue
            if trend != 'all' and indicator.ema_trend != trend:
                continue
            
            # Get AI analysis
            analysis = AIAnalyzer.get_wheel_strategy_analysis(stock)
            
            # Filter by minimum score
            if analysis['wheel_score'] < min_score:
                continue
            
            # Calculate recommended entry strikes
            current_price = float(stock.last_price)
            support = float(indicator.support_level_1) if indicator.support_level_1 else current_price * 0.95
            
            recommended_strikes = []
            
            # Strike 1: At support (Optimal for wheel - best entry)
            strike1 = round(support * 0.98, 2)  # Slightly below support
            discount1 = ((current_price - strike1) / current_price) * 100
            recommended_strikes.append({
                'price': strike1,
                'vs_support': f'${support:.2f}',
                'discount_pct': round(discount1, 1),
                'target_delta': '0.30',
                'quality': 'optimal',
                'reasoning': 'At support level - Ideal for assignment with safety margin'
            })
            
            # Strike 2: 5% below current (Conservative)
            strike2 = round(current_price * 0.95, 2)
            discount2 = 5.0
            recommended_strikes.append({
                'price': strike2,
                'vs_support': f'${abs(strike2 - support):.2f} {"above" if strike2 > support else "below"}',
                'discount_pct': round(discount2, 1),
                'target_delta': '0.25-0.30',
                'quality': 'good',
                'reasoning': 'Conservative entry - Good premium with lower assignment risk'
            })
            
            # Strike 3: 10% below current (Aggressive)
            strike3 = round(current_price * 0.90, 2)
            discount3 = 10.0
            recommended_strikes.append({
                'price': strike3,
                'vs_support': f'${abs(strike3 - support):.2f} {"above" if strike3 > support else "below"}',
                'discount_pct': round(discount3, 1),
                'target_delta': '0.15-0.20',
                'quality': 'good',
                'reasoning': 'Aggressive discount - Lower premium but excellent entry if assigned'
            })
            
            # Build opportunity object
            opportunity = {
                'ticker': stock.ticker,
                'name': stock.name or stock.ticker,
                'price': stock.last_price,
                'wheel_score': analysis['wheel_score'],
                'grade': 'A' if analysis['wheel_score'] >= 80 else 'B' if analysis['wheel_score'] >= 60 else 'C',
                'rsi': indicator.rsi,
                'rsi_signal': indicator.rsi_signal,
                'trend': indicator.ema_trend,
                'support': support,
                'resistance': indicator.resistance_level_1 or current_price * 1.05,
                'near_support': indicator.near_support,
                'price_vs_resistance': f'${abs(current_price - float(indicator.resistance_level_1 or 0)):.2f} below' if indicator.resistance_level_1 else '—',
                'recommended_strikes': recommended_strikes,
                'strategy_recommendation': analysis['reasoning']
            }
            
            opportunities.append(opportunity)
            
        except Exception as e:
            # Skip stocks without indicators
            continue
    
    # Sort by wheel score
    opportunities.sort(key=lambda x: x['wheel_score'], reverse=True)
    
    return render(request, 'ibkr/discovery.html', {
        'opportunities': opportunities,
        'min_score': min_score,
        'rsi_signal': rsi_signal,
        'trend': trend
    })


def stock_detail(request, ticker):
    """Detailed view for a single stock"""
    stock = get_object_or_404(Stock, ticker=ticker.upper())
    
    # Get wheel score and entry signal (consistent with screener)
    try:
        # Calculate wheel score (5-factor system)
        wheel_score_data = calculate_wheel_score(stock)
        
        # Calculate entry signal
        entry_signal_data = calculate_entry_signal(stock)
        
        # Build analysis object with consistent scoring
        analysis = {
            'wheel_score': wheel_score_data['total_score'],
            'grade': wheel_score_data['grade'],
            'grade_color': wheel_score_data['grade_color'],
            'score_breakdown': wheel_score_data,
            
            # Entry signal
            'entry_signal': entry_signal_data['signal'],
            'entry_quality': entry_signal_data['quality'],
            'entry_score': entry_signal_data['score'],
            'entry_reasons': entry_signal_data['reasons'],
            'entry_color': entry_signal_data['signal_color'],
            
            # Strategy rating based on wheel score
            'strategy_rating': f"Grade {wheel_score_data['grade']}" if wheel_score_data['total_score'] >= 50 else "Not Recommended",
            'strategy_color': wheel_score_data['grade_color'],
            
            # Reasoning from entry signal
            'reasoning': f"{entry_signal_data['signal']} - {entry_signal_data['quality']} quality entry",
            
            # Wheel signals from breakdown
            'wheel_signals': [],
            'signals': [],  # Technical signals placeholder
            
            # Action and confidence
            'action': 'buy' if entry_signal_data['score'] >= 60 else 'wait' if entry_signal_data['score'] >= 45 else 'avoid',
            'confidence': entry_signal_data['score']
        }
        
        # Add wheel signals based on score breakdown
        if wheel_score_data['volatility_score'] >= 20:
            analysis['wheel_signals'].append(f"✅ High IV ({wheel_score_data['volatility_score']:.0f}/25) - Great premiums")
        if wheel_score_data['liquidity_score'] >= 15:
            analysis['wheel_signals'].append(f"✅ High liquidity ({wheel_score_data['liquidity_score']:.0f}/20) - Easy entry/exit")
        if wheel_score_data['technical_score'] >= 18:
            analysis['wheel_signals'].append(f"✅ Strong technicals ({wheel_score_data['technical_score']:.0f}/25)")
        if wheel_score_data['stability_score'] >= 14:
            analysis['wheel_signals'].append(f"✅ Good stability ({wheel_score_data['stability_score']:.0f}/20)")
        if wheel_score_data['price_score'] >= 8:
            analysis['wheel_signals'].append(f"✅ Ideal price ({wheel_score_data['price_score']:.0f}/10) - $10-$50 range")
        
        # Calculate average weekly premium (7-14 DTE)
        weekly_premium_avg = None
        weekly_premium_apy = None
        weekly_options_count = 0
        try:
            from datetime import timedelta
            today = timezone.now().date()
            dte_min_date = today + timedelta(days=7)
            dte_max_date = today + timedelta(days=14)
            
            # First try with delta filter (ideal wheel range)
            weekly_options = stock.options.filter(
                option_type='PUT',
                expiry_date__gte=dte_min_date,
                expiry_date__lte=dte_max_date,
                bid__isnull=False,
                bid__gt=0
            )
            
            # Apply delta filter if available
            weekly_with_delta = weekly_options.filter(
                delta__isnull=False,
                delta__gte=-0.40,
                delta__lte=-0.20
            )
            
            # Use delta-filtered options if available, otherwise use all weekly options
            options_to_use = weekly_with_delta if weekly_with_delta.exists() else weekly_options
            
            if options_to_use.exists():
                from django.db.models import F, ExpressionWrapper, FloatField
                # Calculate mid_price as (bid + ask) / 2 in the database
                options_with_mid = options_to_use.annotate(
                    calc_mid_price=ExpressionWrapper(
                        (F('bid') + F('ask')) / 2.0,
                        output_field=FloatField()
                    )
                )
                avg_premium = options_with_mid.aggregate(Avg('calc_mid_price'))['calc_mid_price__avg']
                weekly_options_count = options_to_use.count()
                if avg_premium and stock.last_price:
                    weekly_premium_avg = float(avg_premium)
                    # Calculate APY for weekly premium
                    weekly_premium_apy = (weekly_premium_avg / float(stock.last_price)) * (365 / 7) * 100
        except Exception as e:
            print(f"Error calculating weekly premium for {stock.ticker}: {e}")
            pass
        
        analysis['weekly_premium_avg'] = weekly_premium_avg
        analysis['weekly_premium_apy'] = weekly_premium_apy
        analysis['weekly_options_count'] = weekly_options_count
        
        # Add technical signals from indicators
        if hasattr(stock, 'indicators') and stock.indicators:
            ind = stock.indicators
            if ind.rsi:
                if ind.rsi < 30:
                    analysis['signals'].append(f"📉 RSI {ind.rsi:.1f} - Oversold (great for puts)")
                elif ind.rsi < 40:
                    analysis['signals'].append(f"➖ RSI {ind.rsi:.1f} - Neutral (good for puts)")
                elif ind.rsi > 70:
                    analysis['signals'].append(f"📈 RSI {ind.rsi:.1f} - Overbought (avoid puts)")
                else:
                    analysis['signals'].append(f"➖ RSI {ind.rsi:.1f} - Neutral")
            
            if ind.ema_trend:
                analysis['signals'].append(f"{'📈' if ind.ema_trend == 'BULLISH' else '📉' if ind.ema_trend == 'BEARISH' else '➖'} Trend: {ind.ema_trend}")
            
            if ind.support_level_1 and stock.last_price:
                dist = ((float(stock.last_price) - float(ind.support_level_1)) / float(stock.last_price)) * 100
                if dist < 5:
                    analysis['signals'].append(f"✅ Near support ${ind.support_level_1} ({dist:.1f}% away)")
    except Exception as e:
        # Fallback analysis if calculation fails
        analysis = {
            'wheel_score': 0,
            'grade': 'N/A',
            'strategy_rating': 'Calculate Indicators',
            'strategy_color': 'gray',
            'reasoning': f'Technical indicators need to be calculated first. Run: python manage.py calculate_indicators --ticker={ticker}',
            'wheel_signals': [f'❌ Run: python manage.py calculate_indicators --ticker={ticker}'],
            'signals': [],
            'action': 'neutral',
            'confidence': 0,
            'entry_signal': 'WAIT',
            'entry_score': 0
        }
    
    # Generate actionable signals from current options data
    signals = []
    if analysis.get('entry_score', 0) >= 45:  # Only if timing is decent
        try:
            # Get top PUT options for this stock
            top_puts = Option.objects.filter(
                stock=stock,
                option_type='PUT',
                dte__gte=14,  # At least 2 weeks
                dte__lte=60,  # At most 60 days
            ).exclude(
                mid_price__isnull=True
            ).order_by('-implied_volatility')[:5]
            
            for put in top_puts:
                if put.delta and put.mid_price and put.strike:
                    delta_abs = abs(float(put.delta))
                    
                    # Calculate metrics
                    apy = (float(put.mid_price) / float(put.strike)) * (365 / put.dte) * 100 if put.dte > 0 else 0
                    
                    # Only show if reasonable delta for wheel (0.20-0.40)
                    if 0.20 <= delta_abs <= 0.40 and apy >= 10:
                        # Create a signal-like dict for display
                        signal_dict = {
                            'signal_type': 'CASH_SECURED_PUT',
                            'option': put,
                            'premium': put.mid_price,
                            'apy_pct': round(apy, 1),
                            'quality_score': analysis['entry_score'],
                            'generated_at': timezone.now(),
                            'status': 'RECOMMENDED' if analysis['entry_score'] >= 60 else 'WATCH',
                            'technical_reason': f"{analysis['entry_signal']} - {analysis['entry_quality']} entry with {apy:.0f}% APY"
                        }
                        signals.append(signal_dict)
        except Exception as e:
            pass  # No options available
    
    return render(request, 'ibkr/stock_detail.html', {
        'stock': stock,
        'analysis': analysis,
        'signals': signals
    })



def watchlist_add(request):
    """Add ticker to watchlist and fetch stock data"""
    if request.method == 'POST':
        ticker = request.POST.get('ticker', '').upper().strip()
        if ticker:
            # Add to watchlist
            watchlist_item, created = Watchlist.objects.get_or_create(ticker=ticker)
            
            # Fetch and save stock data
            stock_data = StockDataFetcher.fetch_stock_data(ticker)
            if stock_data:
                # Update or create Stock entry
                Stock.objects.update_or_create(
                    ticker=ticker,
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
                messages.success(request, f'{ticker} added to watchlist with latest data')
            else:
                messages.warning(request, f'{ticker} added to watchlist but could not fetch data')
        else:
            messages.error(request, 'Please enter a valid ticker')
    return redirect('ibkr:dashboard')


def watchlist_remove(request, ticker):
    """Remove ticker from watchlist"""
    ticker = ticker.upper()
    watchlist_item = get_object_or_404(Watchlist, ticker=ticker)
    watchlist_item.delete()
    
    # Optionally remove the stock data as well (if not used elsewhere)
    # Stock.objects.filter(ticker=ticker).delete()
    
    messages.success(request, f'{ticker} removed from watchlist')
    return redirect('ibkr:dashboard')


def refresh_watchlist_data(request):
    """Refresh stock data for all watchlist tickers"""
    watchlist = Watchlist.objects.all()
    tickers = list(watchlist.values_list('ticker', flat=True))
    
    # Get the referring page to redirect back
    referer = request.META.get('HTTP_REFERER', '')
    
    if not tickers:
        messages.warning(request, 'No tickers in watchlist to refresh')
        # Redirect back to referring page or dashboard
        if referer:
            return redirect(referer)
        return redirect('ibkr:dashboard')
    
    success_count = 0
    error_count = 0
    
    for ticker in tickers:
        stock_data = StockDataFetcher.fetch_stock_data(ticker)
        if stock_data:
            Stock.objects.update_or_create(
                ticker=ticker,
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
            success_count += 1
        else:
            error_count += 1
    
    if success_count > 0:
        messages.success(request, f'Refreshed {success_count} stock(s) successfully')
    if error_count > 0:
        messages.warning(request, f'Failed to refresh {error_count} stock(s)')
    
    # Redirect back to referring page or dashboard
    if referer:
        return redirect(referer)
    return redirect('ibkr:dashboard')


def sync_yfinance_options_view(request):
    """Sync options data from Yahoo Finance for all stocks"""
    from django.core.management import call_command
    from io import StringIO
    
    try:
        # Capture command output
        out = StringIO()
        call_command('sync_yfinance_options', stdout=out)
        
        messages.success(request, 'Options data synced from Yahoo Finance successfully!')
    except Exception as e:
        messages.error(request, f'Error syncing options: {str(e)}')
    
    # Redirect back to options page or referer
    referer = request.META.get('HTTP_REFERER', '/')
    return redirect(referer)


def open_position(request):
    """Open a new option position"""
    if request.method == 'POST':
        try:
            stock_ticker = request.POST.get('ticker')
            option_type = request.POST.get('option_type')
            strike = Decimal(request.POST.get('strike'))
            expiry_date_str = request.POST.get('expiry_date')
            contracts = int(request.POST.get('contracts', 1))
            entry_premium = Decimal(request.POST.get('premium'))
            entry_stock_price = Decimal(request.POST.get('stock_price'))
            entry_delta = request.POST.get('delta')
            
            # Parse the date properly
            from datetime import datetime
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            
            stock = get_object_or_404(Stock, ticker=stock_ticker)
            
            # Try to find the option
            try:
                option = Option.objects.get(
                    stock=stock,
                    option_type=option_type,
                    strike=strike,
                    expiry_date=expiry_date
                )
            except Option.DoesNotExist:
                option = None
            
            # Create position
            position = OptionPosition.objects.create(
                stock=stock,
                option=option,
                option_type=option_type,
                strike=strike,
                expiry_date=expiry_date,
                contracts=contracts,
                entry_premium=entry_premium,
                total_premium=entry_premium * contracts * 100,
                entry_stock_price=entry_stock_price,
                entry_delta=Decimal(entry_delta) if entry_delta else None,
                status='OPEN'
            )
            
            messages.success(request, f'Position opened: {stock.ticker} ${strike} {option_type} x{contracts} contracts')
            return redirect('ibkr:positions')
        
        except Exception as e:
            messages.error(request, f'Error opening position: {str(e)}')
            return redirect('ibkr:dashboard')
    
    return redirect('ibkr:dashboard')


def positions_list(request):
    """List all option positions with AI recommendations"""
    open_positions = OptionPosition.objects.filter(status='OPEN').select_related('stock', 'option')
    closed_positions = OptionPosition.objects.exclude(status='OPEN').select_related('stock', 'option')[:10]
    
    # Update current premium for open positions
    for position in open_positions:
        if position.option and position.option.mid_price:
            position.current_premium = position.option.mid_price
            position.save()
        
        # Add AI recommendation
        position.ai_recommendation = get_position_ai_recommendation(position)
    
    context = {
        'open_positions': open_positions,
        'closed_positions': closed_positions,
    }
    return render(request, 'ibkr/positions.html', context)


def close_position(request, position_id):
    """Close an open position"""
    position = get_object_or_404(OptionPosition, id=position_id)
    
    if request.method == 'POST':
        exit_premium = Decimal(request.POST.get('exit_premium', 0))
        
        position.status = 'CLOSED'
        position.exit_date = timezone.now().date()
        position.exit_premium = exit_premium
        position.realized_pl = float(position.total_premium) - (float(exit_premium) * position.contracts * 100)
        position.save()
        
        messages.success(request, f'Position closed. P/L: ${position.realized_pl:.2f}')
    
    return redirect('ibkr:positions')


def get_position_ai_recommendation(position):
    """Generate AI recommendation for a position"""
    stock = position.stock
    dte = position.dte
    days_held = position.days_held
    
    # Get current P/L
    if position.unrealized_pl is not None:
        unrealized_pl_pct = position.unrealized_pl_pct
    else:
        unrealized_pl_pct = 0
    
    # Get stock analysis
    ai_analysis = AIAnalyzer.get_wheel_strategy_analysis(stock)
    
    recommendation = {
        'action': '',
        'reason': '',
        'confidence': 0,
        'color': 'gray'
    }
    
    # Decision logic
    if unrealized_pl_pct >= 50:
        recommendation['action'] = 'CLOSE - Take Profit'
        recommendation['reason'] = f'Position is up {unrealized_pl_pct:.1f}%. Lock in profits at 50%+ gain.'
        recommendation['confidence'] = 90
        recommendation['color'] = 'green'
    
    elif unrealized_pl_pct >= 25 and dte <= 7:
        recommendation['action'] = 'CLOSE - Near Expiration'
        recommendation['reason'] = f'Up {unrealized_pl_pct:.1f}% with {dte} days left. Close before theta decay reverses.'
        recommendation['confidence'] = 80
        recommendation['color'] = 'green'
    
    elif unrealized_pl_pct <= -20:
        if ai_analysis and ai_analysis.get('action') == 'buy':
            recommendation['action'] = 'HOLD - Technical Support'
            recommendation['reason'] = f'Down {abs(unrealized_pl_pct):.1f}%, but stock shows bullish signals. Consider rolling down if assigned.'
            recommendation['confidence'] = 60
            recommendation['color'] = 'yellow'
        else:
            recommendation['action'] = 'CONSIDER CLOSING'
            recommendation['reason'] = f'Down {abs(unrealized_pl_pct):.1f}% with weak technicals. May want to cut losses.'
            recommendation['confidence'] = 70
            recommendation['color'] = 'red'
    
    elif dte <= 3:
        if position.option_type == 'PUT' and stock.last_price and float(stock.last_price) > float(position.strike):
            recommendation['action'] = 'LET EXPIRE'
            recommendation['reason'] = f'Stock at ${stock.last_price} above strike ${position.strike}. Will expire worthless - keep premium.'
            recommendation['confidence'] = 95
            recommendation['color'] = 'green'
        else:
            recommendation['action'] = 'MONITOR CLOSELY'
            recommendation['reason'] = f'Expiring in {dte} days. Watch for assignment risk.'
            recommendation['confidence'] = 75
            recommendation['color'] = 'yellow'
    
    elif days_held >= 21 and unrealized_pl_pct >= 30:
        recommendation['action'] = 'ROLL OR CLOSE'
        recommendation['reason'] = f'Held for {days_held} days with {unrealized_pl_pct:.1f}% profit. Consider rolling to next month or closing.'
        recommendation['confidence'] = 70
        recommendation['color'] = 'blue'
    
    else:
        recommendation['action'] = 'HOLD'
        recommendation['reason'] = f'Position is performing normally. Current P/L: {unrealized_pl_pct:.1f}%. {dte} days until expiration.'
        recommendation['confidence'] = 60
        recommendation['color'] = 'blue'
    
    return recommendation


def health_check(request):
    """System health check view with detailed status"""
    from apps.ibkr.services.health_check import get_health_check_service, refresh_health_check
    
    # Check if refresh requested
    if request.GET.get('refresh') == 'true':
        results = refresh_health_check()
        messages.success(request, 'Health check refreshed')
    else:
        health_service = get_health_check_service()
        results = health_service.results
    
    context = {
        'health_results': results,
        'checks': results['checks'],
        'overall_status': results['overall_status'],
        'timestamp': results['timestamp'],
    }
    
    return render(request, 'ibkr/health_check.html', context)


def gateway_control(request):
    """IB Gateway control panel"""
    client = IBKRClient()
    
    context = {
        'is_connected': client.ensure_connected(),
        'gateway_host': client.host,
        'gateway_port': client.port,
        'client_id': client.client_id,
    }
    
    return render(request, 'ibkr/gateway_control.html', context)


def gateway_status_api(request):
    """API endpoint for gateway connection status"""
    client = IBKRClient()
    
    try:
        is_connected = client.ensure_connected()
        
        status_data = {
            'connected': is_connected,
            'host': client.host,
            'port': client.port,
            'client_id': client.client_id,
            'timestamp': timezone.now().isoformat(),
        }
        
        if is_connected:
            # Get account info if connected
            try:
                accounts = client.ib.managedAccounts()
                status_data['accounts'] = accounts
            except:
                status_data['accounts'] = []
        
        return JsonResponse(status_data)
    except Exception as e:
        return JsonResponse({
            'connected': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat(),
        }, status=500)


def gateway_connect_api(request):
    """API endpoint to connect to IB Gateway"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    client = IBKRClient()
    
    try:
        success = client.connect()
        
        if success:
            return JsonResponse({
                'success': True,
                'message': f'Connected to IB Gateway at {client.host}:{client.port}',
                'connected': True,
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Failed to connect to IB Gateway',
                'connected': False,
            }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'connected': False,
        }, status=500)


def gateway_disconnect_api(request):
    """API endpoint to disconnect from IB Gateway"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    client = IBKRClient()
    
    try:
        client.disconnect()
        return JsonResponse({
            'success': True,
            'message': 'Disconnected from IB Gateway',
            'connected': False,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


def refresh_all_data_api(request):
    """API endpoint to trigger data refresh"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    from django.core.management import call_command
    from io import StringIO
    import sys
    import json
    
    try:
        # Get refresh mode from request
        body = json.loads(request.body) if request.body else {}
        mode = body.get('mode', 'quick')  # 'quick' or 'full'
        
        # Capture command output
        output = StringIO()
        
        # Run refresh in a separate thread to avoid blocking
        import threading
        
        def run_refresh():
            try:
                if mode == 'quick':
                    # Quick refresh - only stale data
                    call_command('quick_refresh', stdout=output, stderr=output)
                else:
                    # Full refresh - everything
                    call_command('refresh_all_data', stdout=output, stderr=output)
                cache.set('refresh_status', 'completed', timeout=300)
                cache.set('refresh_output', output.getvalue(), timeout=300)
            except Exception as e:
                cache.set('refresh_status', 'error', timeout=300)
                cache.set('refresh_error', str(e), timeout=300)
        
        # Check if refresh is already running
        if cache.get('refresh_status') == 'running':
            return JsonResponse({
                'success': False,
                'error': 'Refresh already in progress',
                'status': 'running'
            })
        
        # Start refresh
        cache.set('refresh_status', 'running', timeout=3600)
        cache.set('refresh_started', timezone.now().isoformat(), timeout=3600)
        
        thread = threading.Thread(target=run_refresh)
        thread.daemon = True
        thread.start()
        
        return JsonResponse({
            'success': True,
            'message': f'Data refresh started ({mode} mode)',
            'status': 'running',
            'mode': mode,
            'started': timezone.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


def refresh_status_api(request):
    """API endpoint to check refresh status"""
    status = cache.get('refresh_status', 'idle')
    started = cache.get('refresh_started')
    output = cache.get('refresh_output', '')
    error = cache.get('refresh_error', '')
    progress = cache.get('refresh_progress', {})
    
    response = {
        'status': status,
        'started': started,
        'progress': progress,
    }
    
    if status == 'completed':
        response['message'] = 'Data refresh completed successfully'
        response['output'] = output
        # Get updated stats
        from .models import Stock, StockIndicator, Option
        response['stats'] = {
            'stocks': Stock.objects.count(),
            'indicators': StockIndicator.objects.count(),
            'options': Option.objects.count(),
        }
    elif status == 'error':
        response['error'] = error
        response['message'] = 'Data refresh failed'
        if progress:
            response['message'] = f"Failed at: {progress.get('message', 'Unknown step')}"
    elif status == 'running':
        if progress:
            response['message'] = progress.get('message', 'Data refresh in progress...')
            response['detail'] = progress.get('detail', '')
            response['percentage'] = progress.get('percentage', 0)
            response['step'] = progress.get('step', 1)
            response['total_steps'] = progress.get('total_steps', 3)
        else:
            response['message'] = 'Data refresh in progress...'
    else:
        response['message'] = 'No refresh in progress'
    
    return JsonResponse(response)


def sync_positions_api(request):
    """API endpoint to sync positions from IBKR"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    from django.core.management import call_command
    from io import StringIO
    import threading
    
    try:
        # Check if sync is already running
        if cache.get('sync_positions_status') == 'running':
            return JsonResponse({
                'success': False,
                'error': 'Position sync already in progress',
                'status': 'running'
            })
        
        # Capture command output
        output = StringIO()
        
        def run_sync():
            try:
                call_command('sync_positions', stdout=output, stderr=output)
                cache.set('sync_positions_status', 'completed', timeout=300)
                cache.set('sync_positions_output', output.getvalue(), timeout=300)
                
                # Store position counts
                from .models import OptionPosition
                cache.set('sync_positions_count', OptionPosition.objects.filter(status='OPEN').count(), timeout=300)
            except Exception as e:
                cache.set('sync_positions_status', 'error', timeout=300)
                cache.set('sync_positions_error', str(e), timeout=300)
        
        # Start sync
        cache.set('sync_positions_status', 'running', timeout=600)
        cache.set('sync_positions_started', timezone.now().isoformat(), timeout=600)
        
        thread = threading.Thread(target=run_sync)
        thread.daemon = True
        thread.start()
        
        return JsonResponse({
            'success': True,
            'message': 'Position sync started',
            'status': 'running',
            'started': timezone.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


def sync_positions_status_api(request):
    """API endpoint to check position sync status"""
    status = cache.get('sync_positions_status', 'idle')
    started = cache.get('sync_positions_started')
    output = cache.get('sync_positions_output', '')
    error = cache.get('sync_positions_error', '')
    count = cache.get('sync_positions_count', 0)
    
    response = {
        'status': status,
        'started': started,
    }
    
    if status == 'completed':
        response['message'] = f'Position sync completed - {count} open positions'
        response['output'] = output
        response['count'] = count
    elif status == 'error':
        response['error'] = error
        response['message'] = 'Position sync failed'
    elif status == 'running':
        response['message'] = 'Syncing positions from IBKR...'
    else:
        response['message'] = 'No sync in progress'
    
    return JsonResponse(response)


# === ALERT MANAGEMENT VIEWS ===

def create_alert_api(request):
    """API endpoint to create alerts"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        import json
        from .services.alert_service import AlertService
        from .models import OptionPosition, Stock
        
        data = json.loads(request.body)
        alert_type = data.get('alert_type')
        
        # Get notification preferences from client
        telegram_chat_id = request.session.get('telegram_chat_id') or data.get('telegram_chat_id')
        push_subscription = data.get('push_subscription')
        
        if alert_type == '50_PERCENT_PROFIT':
            position_id = data.get('position_id')
            position = OptionPosition.objects.get(id=position_id)
            
            alert = AlertService.create_50_percent_alert(
                position=position,
                telegram_chat_id=telegram_chat_id,
                push_subscription=push_subscription
            )
            
            return JsonResponse({
                'success': True,
                'message': '50% profit alert created',
                'alert_id': alert.id,
                'target_premium': float(alert.target_premium)
            })
        
        elif alert_type == 'STOCK_PRICE':
            ticker = data.get('ticker')
            target_price = data.get('target_price')
            trigger_above = data.get('trigger_above', False)
            
            stock = Stock.objects.get(ticker=ticker)
            
            alert = AlertService.create_stock_price_alert(
                stock=stock,
                target_price=target_price,
                trigger_above=trigger_above,
                telegram_chat_id=telegram_chat_id,
                push_subscription=push_subscription
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Price alert created for {ticker}',
                'alert_id': alert.id
            })
        
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid alert type'
            }, status=400)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def list_alerts_api(request):
    """API endpoint to list user's alerts"""
    from .models import Alert
    
    try:
        alerts = Alert.objects.filter(status='ACTIVE').select_related('position', 'stock')[:50]
        
        alert_list = []
        for alert in alerts:
            alert_data = {
                'id': alert.id,
                'type': alert.alert_type,
                'status': alert.status,
                'message': alert.message,
                'created_at': alert.created_at.isoformat(),
            }
            
            if alert.position:
                alert_data['position'] = {
                    'ticker': alert.position.stock.ticker,
                    'strike': float(alert.position.strike),
                    'option_type': alert.position.option_type
                }
            
            if alert.target_stock_price:
                alert_data['target_stock_price'] = float(alert.target_stock_price)
            
            if alert.target_premium:
                alert_data['target_premium'] = float(alert.target_premium)
            
            alert_list.append(alert_data)
        
        return JsonResponse({
            'success': True,
            'alerts': alert_list,
            'count': len(alert_list)
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def dismiss_alert_api(request, alert_id):
    """API endpoint to dismiss an alert"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        from .models import Alert
        
        alert = Alert.objects.get(id=alert_id)
        alert.status = 'DISMISSED'
        alert.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Alert dismissed'
        })
    
    except Alert.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Alert not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def save_telegram_chat_id(request):
    """Save user's Telegram chat ID in session"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        chat_id = data.get('chat_id')
        
        if chat_id:
            request.session['telegram_chat_id'] = chat_id
            return JsonResponse({
                'success': True,
                'message': 'Telegram chat ID saved'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Chat ID required'
            }, status=400)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ==========================================
# ORDER PLACEMENT API ENDPOINTS
# ==========================================

def place_order_api(request):
    """
    API endpoint to place an order through IBKR.
    Supports selling puts, selling calls, buying/selling stocks and options.
    
    POST JSON body:
    {
        "action": "SELL" or "BUY",
        "sec_type": "OPT" or "STK",
        "ticker": "AAPL",
        "quantity": 1,
        "order_type": "LMT" or "MKT",
        "limit_price": 1.50,          # required for LMT
        "strike": 150.0,              # required for OPT
        "expiry": "2026-03-20",       # required for OPT (YYYY-MM-DD)
        "right": "P" or "C",          # required for OPT
        "track_position": true         # also create a DB position record
    }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    action = data.get('action', '').upper()
    sec_type = data.get('sec_type', 'OPT').upper()
    ticker = data.get('ticker', '').upper()
    quantity = int(data.get('quantity', 1))
    order_type = data.get('order_type', 'LMT').upper()
    limit_price = data.get('limit_price')
    track_position = data.get('track_position', True)
    
    if not ticker:
        return JsonResponse({'success': False, 'error': 'Ticker is required'}, status=400)
    if action not in ('BUY', 'SELL'):
        return JsonResponse({'success': False, 'error': 'Action must be BUY or SELL'}, status=400)
    if order_type == 'LMT' and limit_price is None:
        return JsonResponse({'success': False, 'error': 'Limit price is required for limit orders'}, status=400)
    
    if limit_price is not None:
        limit_price = float(limit_price)
    
    try:
        client = IBKRClient()
        if not client.ensure_connected():
            return JsonResponse({
                'success': False,
                'error': 'Could not connect to IB Gateway. Make sure Gateway is running and logged in.'
            }, status=503)
        
        result = None
        
        if sec_type == 'OPT':
            # Option order
            strike = data.get('strike')
            expiry_str = data.get('expiry', '')
            right = data.get('right', '').upper()
            
            if not all([strike, expiry_str, right]):
                return JsonResponse({'success': False, 'error': 'Option orders require strike, expiry, and right (P/C)'}, status=400)
            if right not in ('P', 'C'):
                return JsonResponse({'success': False, 'error': 'Right must be P (put) or C (call)'}, status=400)
            
            strike = float(strike)
            # Convert YYYY-MM-DD to YYYYMMDD for ib_insync
            expiry = expiry_str.replace('-', '')
            
            if action == 'SELL':
                result = client.sell_option(ticker, expiry, strike, right, quantity, order_type, limit_price)
            else:
                result = client.buy_option(ticker, expiry, strike, right, quantity, order_type, limit_price)
            
            # Track position in DB if selling and successful
            if result.get('success') and action == 'SELL' and track_position:
                try:
                    stock, _ = Stock.objects.get_or_create(ticker=ticker, defaults={'name': ticker})
                    expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date() if '-' in expiry_str else datetime.strptime(expiry, '%Y%m%d').date()
                    premium = limit_price or 0
                    
                    position = OptionPosition.objects.create(
                        stock=stock,
                        option_type='PUT' if right == 'P' else 'CALL',
                        strike=Decimal(str(strike)),
                        expiry_date=expiry_date,
                        contracts=quantity,
                        entry_premium=Decimal(str(premium)),
                        total_premium=Decimal(str(premium)) * quantity * 100,
                        entry_stock_price=Decimal(str(stock.last_price or 0)),
                        status='OPEN',
                        notes=f"IBKR Order #{result.get('order_id', 'N/A')} - {order_type} @ ${premium}"
                    )
                    result['position_id'] = position.id
                    result['position_tracked'] = True
                except Exception as e:
                    result['position_tracked'] = False
                    result['position_error'] = str(e)
        
        elif sec_type == 'STK':
            # Stock order
            if action == 'BUY':
                result = client.buy_stock(ticker, quantity, order_type, limit_price)
            else:
                result = client.sell_stock(ticker, quantity, order_type, limit_price)
        
        else:
            return JsonResponse({'success': False, 'error': f'Unsupported security type: {sec_type}'}, status=400)
        
        if result:
            return JsonResponse(result, status=200 if result.get('success') else 400)
        else:
            return JsonResponse({'success': False, 'error': 'No result from order placement'}, status=500)
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def cancel_order_api(request):
    """API endpoint to cancel an open order"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        
        if not order_id:
            return JsonResponse({'success': False, 'error': 'order_id is required'}, status=400)
        
        client = IBKRClient()
        if not client.ensure_connected():
            return JsonResponse({'success': False, 'error': 'Could not connect to IB Gateway'}, status=503)
        
        result = client.cancel_order(int(order_id))
        return JsonResponse(result, status=200 if result.get('success') else 400)
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def open_orders_api(request):
    """API endpoint to list all open orders from IBKR"""
    try:
        client = IBKRClient()
        if not client.ensure_connected():
            return JsonResponse({
                'success': False,
                'error': 'Could not connect to IB Gateway'
            }, status=503)
        
        orders = client.get_open_orders()
        return JsonResponse({
            'success': True,
            'orders': orders,
            'count': len(orders)
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def option_quote_api(request):
    """
    API endpoint to get a live option quote.
    
    GET params: ticker, expiry (YYYYMMDD), strike, right (P/C)
    """
    ticker = request.GET.get('ticker', '').upper()
    expiry = request.GET.get('expiry', '').replace('-', '')
    strike = request.GET.get('strike')
    right = request.GET.get('right', '').upper()
    
    if not all([ticker, expiry, strike, right]):
        return JsonResponse({'success': False, 'error': 'ticker, expiry, strike, and right are required'}, status=400)
    
    try:
        client = IBKRClient()
        if not client.ensure_connected():
            return JsonResponse({'success': False, 'error': 'Could not connect to IB Gateway'}, status=503)
        
        quote = client.get_option_quote(ticker, expiry, float(strike), right)
        if quote:
            # Sanitize NaN/Inf values - they're not valid JSON
            import math
            clean = {}
            for k, v in quote.items():
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    clean[k] = None
                else:
                    clean[k] = v
            return JsonResponse({'success': True, **clean})
        else:
            return JsonResponse({'success': False, 'error': 'Could not get quote'}, status=404)
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def orders_page(request):
    """Orders management page - view open orders, place new ones"""
    try:
        client = IBKRClient()
        connected = client.ensure_connected() if client else False
        open_orders = client.get_open_orders() if connected else []
    except Exception:
        connected = False
        open_orders = []
    
    # Get watchlist stocks for the order form
    watchlist_stocks = Stock.objects.all().order_by('ticker')
    
    # Get all stocks as fallback
    all_stocks = Stock.objects.all().order_by('ticker')
    
    return render(request, 'ibkr/orders.html', {
        'open_orders': open_orders,
        'connected': connected,
        'watchlist_stocks': watchlist_stocks,
        'all_stocks': all_stocks,
    })


def vnc_viewer(request):
    """View to access IB Gateway VNC interface via iframe"""
    return render(request, 'ibkr/vnc.html', {
        'page_title': 'IB Gateway VNC',
    })

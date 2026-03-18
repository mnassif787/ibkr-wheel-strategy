from django.views.decorators.csrf import csrf_exempt
import logging
@csrf_exempt
def ibkr_debug(request):
    """Debug endpoint for IBKR connection and data fetch status"""
    logger = logging.getLogger('apps.ibkr.services.ibkr_client')
    import io
    import traceback
    from .services.ibkr_client import IBKRClient
    debug_info = {}
    try:
        client = IBKRClient()
        connected = client.ensure_connected()
        debug_info['connected'] = connected
        debug_info['is_connected'] = client.is_connected()
        # Try fetching account summary
        try:
            acct = client.get_account_summary()
            debug_info['account_summary'] = acct
        except Exception as e:
            debug_info['account_summary_error'] = str(e)
            debug_info['account_summary_trace'] = traceback.format_exc()
        # Try fetching portfolio positions
        try:
            positions = client.get_portfolio_positions()
            debug_info['portfolio_positions'] = positions
        except Exception as e:
            debug_info['portfolio_positions_error'] = str(e)
            debug_info['portfolio_positions_trace'] = traceback.format_exc()
    except Exception as e:
        debug_info['init_error'] = str(e)
        debug_info['init_trace'] = traceback.format_exc()
    # Optionally, include last 20 log lines if possible
    try:
        import os
        log_path = os.path.join(os.path.dirname(__file__), '../../services/ibkr_client.log')
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                lines = f.readlines()[-20:]
            debug_info['last_logs'] = lines
    except Exception:
        pass
    return JsonResponse(debug_info, safe=False)
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
from .models import Stock, Option, Signal, Watchlist, UserConfig, OptionPosition, StockWheelScore, StockIndicator, StockPosition
from .services.stock_data_fetcher import StockDataFetcher
from .services.ai_analysis import AIAnalyzer
from .services.ibkr_client import IBKRClient
from .services.position_analyzer import PositionAnalyzer
from .services.technical_analysis import TechnicalAnalysisService

# Initialize logger
logger = logging.getLogger(__name__)


def _auto_expire_stale_positions():
    """Mark OPEN option positions whose expiry has passed as EXPIRED or ASSIGNED.
    Runs cheaply on every hub page load — only touches rows that need updating.
    """
    from datetime import date as _d
    from decimal import Decimal as _Dec
    today = _d.today()
    stale = list(OptionPosition.objects.filter(status='OPEN', expiry_date__lt=today).select_related('stock'))
    for pos in stale:
        try:
            stock_price = float(pos.stock.last_price) if pos.stock.last_price else None
            strike = float(pos.strike)
            # Determine if the option expired in-the-money (assignment)
            if stock_price is not None:
                if pos.option_type == 'PUT' and stock_price < strike:
                    new_status = 'ASSIGNED'
                elif pos.option_type == 'CALL' and stock_price > strike:
                    new_status = 'ASSIGNED'
                else:
                    new_status = 'EXPIRED'
            else:
                new_status = 'EXPIRED'
            # For expired/assigned, realized P/L = total premium collected (kept)
            entry_p = float(pos.total_premium) if pos.total_premium else 0
            pos.status = new_status
            pos.exit_premium = _Dec('0')
            pos.realized_pl = _Dec(str(entry_p))
            pos.exit_date = today
            pos.save(update_fields=['status', 'exit_premium', 'realized_pl', 'exit_date'])
            logger.info(f'Auto-expired {pos} → {new_status}')
        except Exception as e:
            logger.warning(f'Could not auto-expire {pos}: {e}')


def _build_open_options_by_ticker(positions_list):
    """Build {ticker: [position_dicts]} from an already-evaluated list — zero extra DB queries."""
    result = {}
    for p in positions_list:
        ticker = p.stock.ticker
        if ticker not in result:
            result[ticker] = []
        result[ticker].append({
            'id': p.id,
            'option_type': p.option_type,
            'strike': p.strike,
            'expiry_date': p.expiry_date,
        })
    return result


def hub(request):
    # Handle manual stock add form
    if request.method == 'POST' and 'manual_add_ticker' in request.POST:
        ticker = request.POST.get('manual_add_ticker', '').upper().strip()
        if ticker:
            # Add to watchlist
            watchlist_item, created = Watchlist.objects.get_or_create(ticker=ticker)
            
            if created:
                # Fetch stock data immediately
                try:
                    stock_data = StockDataFetcher.fetch_stock_data(ticker)
                    
                    if stock_data:
                        # Save stock data to database
                        stock, stock_created = Stock.objects.update_or_create(
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
                        
                        # Calculate technical indicators
                        try:
                            indicators_data = TechnicalAnalysisService.calculate_all_indicators(ticker)
                            
                            if indicators_data:
                                StockIndicator.objects.update_or_create(
                                    stock=stock,
                                    defaults={
                                        'rsi': indicators_data.get('rsi'),
                                        'rsi_signal': indicators_data.get('rsi_signal', 'NEUTRAL'),
                                        'ema_50': indicators_data.get('ema_50'),
                                        'ema_200': indicators_data.get('ema_200'),
                                        'ema_trend': indicators_data.get('ema_trend', 'NEUTRAL'),
                                        'bb_upper': indicators_data.get('bb_upper'),
                                        'bb_middle': indicators_data.get('bb_middle'),
                                        'bb_lower': indicators_data.get('bb_lower'),
                                        'bb_position': indicators_data.get('bb_position', ''),
                                        'support_level_1': indicators_data.get('support_level_1'),
                                        'support_level_2': indicators_data.get('support_level_2'),
                                        'support_level_3': indicators_data.get('support_level_3'),
                                        'resistance_level_1': indicators_data.get('resistance_level_1'),
                                        'resistance_level_2': indicators_data.get('resistance_level_2'),
                                        'resistance_level_3': indicators_data.get('resistance_level_3'),
                                        'price_history': indicators_data.get('price_history', []),
                                        'last_calculated': timezone.now(),
                                    }
                                )
                                messages.success(request, f'✅ {ticker} added successfully! Price: ${stock_data.get("last_price", 0):.2f} | Wheel Score calculated')
                            else:
                                messages.success(request, f'✅ {ticker} added! Price: ${stock_data.get("last_price", 0):.2f} | Note: Technical indicators calculation pending')
                        except Exception as e:
                            logger.error(f"Error calculating indicators for {ticker}: {e}")
                            messages.success(request, f'✅ {ticker} added! Price: ${stock_data.get("last_price", 0):.2f} | Note: Technical indicators will be calculated on next refresh')
                    else:
                        messages.warning(request, f'⚠️ {ticker} added to watchlist but failed to fetch data. Click refresh to try again.')
                except Exception as e:
                    logger.error(f"Error fetching data for {ticker}: {e}")
                    messages.warning(request, f'⚠️ {ticker} added to watchlist but error fetching data: {str(e)}')
            else:
                messages.info(request, f'{ticker} is already in the watchlist.')
        else:
            messages.warning(request, 'Please enter a ticker symbol.')
        return redirect('ibkr:hub')

    """Main hub with tabs for positions, discovery (stocks/options/signals)"""
    # Get all data for all tabs
    # Get last updated time from any stock
    last_updated = Stock.objects.filter(last_updated__isnull=False).order_by('-last_updated').values_list('last_updated', flat=True).first()

    # POSITIONS TAB DATA
    # Stock positions
    stock_positions = list(StockPosition.objects.select_related('stock').prefetch_related('stock__options').order_by('-market_value'))

    # Pre-fetch all CALL options for stock positions in one query (avoids N queries)
    _sp_stock_ids = [sp.stock_id for sp in stock_positions]
    _all_calls_qs = (
        Option.objects.filter(stock_id__in=_sp_stock_ids, option_type='CALL')
        .order_by('expiry_date', 'strike')
        .values('id', 'stock_id', 'strike', 'expiry_date',
                'bid', 'ask', 'last', 'delta', 'implied_volatility')
    )
    from collections import defaultdict as _defaultdict
    from datetime import date as _today_cls
    _today = _today_cls.today()
    _calls_by_stock = _defaultdict(list)
    for _c in _all_calls_qs:
        # Compute dte and mid_price (not DB columns)
        _c['dte'] = (_c['expiry_date'] - _today).days if _c['expiry_date'] else None
        bid, ask = _c['bid'], _c['ask']
        if bid and ask:
            _c['mid_price'] = (float(bid) + float(ask)) / 2
        elif _c['last']:
            _c['mid_price'] = float(_c['last'])
        else:
            _c['mid_price'] = None
        _calls_by_stock[_c['stock_id']].append(_c)

    # Attach best covered call options to each stock position
    for sp in stock_positions:
        sp.covered_calls = []
        try:
            stock = sp.stock
            current_price = float(stock.last_price) if stock.last_price else None
            if current_price:
                all_calls = _calls_by_stock[sp.stock_id]  # no extra DB hit

                call_candidates = []
                for c in all_calls:
                    # c is a dict from .values() — use dict access
                    dte = c['dte']
                    mid_price = c['mid_price']
                    delta = c['delta']
                    strike = c['strike']
                    if not (dte and 1 <= dte <= 120 and mid_price and delta and strike):
                        continue
                    strike_f = float(strike)
                    # Covered calls ideally OTM (strike >= current price)
                    if strike_f < current_price:
                        continue
                    delta_abs = abs(float(delta))
                    if not (0.05 <= delta_abs <= 0.50):
                        continue
                    apy = (float(mid_price) / strike_f) * (365 / dte) * 100
                    if apy < 2:
                        continue
                    premium_f = float(mid_price)
                    breakeven = strike_f + premium_f
                    otm_pct = ((strike_f - current_price) / current_price) * 100
                    avg_cost_f = float(sp.avg_cost) if sp.avg_cost else 0
                    capital_pl_per_share = strike_f - avg_cost_f
                    total_pl_per_share = capital_pl_per_share + premium_f
                    total_pl_per_contract = total_pl_per_share * 100
                    call_candidates.append({
                        'option': c,
                        'option_id': c['id'],
                        'strike': strike_f,
                        'expiry': c['expiry_date'],
                        'dte': dte,
                        'delta': float(delta),
                        'iv': float(c['implied_volatility']) if c['implied_volatility'] else 0,
                        'premium': premium_f,
                        'premium_per_contract': premium_f * 100,
                        'bid': float(c['bid']) if c['bid'] else 0,
                        'ask': float(c['ask']) if c['ask'] else 0,
                        'apy_pct': round(apy, 1),
                        'breakeven': round(breakeven, 2),
                        'otm_pct': round(otm_pct, 1),
                        'prob_assignment': round(delta_abs * 100, 1),
                        'avg_cost': round(avg_cost_f, 2),
                        'capital_pl_per_share': round(capital_pl_per_share, 2),
                        'total_pl_per_share': round(total_pl_per_share, 2),
                        'total_pl_per_contract': round(total_pl_per_contract, 2),
                    })

                # Sort by APY descending, take top 8
                call_candidates.sort(key=lambda x: x['apy_pct'], reverse=True)
                sp.covered_calls = call_candidates[:8]
        except Exception as e:
            logger.warning(f"Error computing covered calls for {sp.stock.ticker}: {e}")
    
    # Auto-expire any OPEN positions whose expiry date has passed
    _auto_expire_stale_positions()

    # Option positions — evaluate QuerySet to list once so we can reuse without extra hits
    open_positions = OptionPosition.objects.filter(status='OPEN').select_related('stock').order_by('-entry_date')
    open_positions_list = list(open_positions)  # single DB hit, reused below
    closed_positions = OptionPosition.objects.exclude(status='OPEN').select_related('stock').order_by('-exit_date')[:10]

    # Account summary loaded async via /api/account-summary/ — skip sync fetch here
    # NOTE: Live IBKR quote refresh and AI analysis moved out of hub page load for performance.
    # Quotes update via the dedicated /api/account-summary/ endpoint; AI analysis deferred.
    
    # STOCKS TAB DATA
    # Get watchlist tickers for "My Stocks" tab
    watchlist_tickers = set(Watchlist.objects.values_list('ticker', flat=True))
    
    # Check if discovery filters are applied (only price range now)
    price_ranges = request.GET.getlist('price_range')  # Multi-select price ranges
    filters_applied = bool(price_ranges)
    
    # Always process preferred stocks (My Stocks tab)
    preferred_stocks_query = Stock.objects.filter(ticker__in=watchlist_tickers).select_related('indicators').prefetch_related('options')
    preferred_stock_scores = []
    
    for stock in preferred_stocks_query:
        score_data = calculate_wheel_score(stock)
        stock.wheel_score = score_data['total_score']
        stock.score_breakdown = score_data
        
        entry_signal = calculate_entry_signal(stock)
        stock.entry_signal = entry_signal['signal']
        stock.entry_quality = entry_signal['quality']
        stock.entry_score = entry_signal['score']
        stock.entry_color = entry_signal['signal_color']
        stock.in_watchlist = True
        
        preferred_stock_scores.append(stock)
    
    # Only process discovery stocks if filters are applied (price range search)
    discovery_stocks = []
    
    if filters_applied:
        # Fetch all stocks when price range filters are applied
        all_stocks = Stock.objects.select_related('indicators').prefetch_related('options').all()
        
        # Filter stocks by price range only (basic info, no complex calculations yet)
        for stock in all_stocks:
            if not stock.last_price:
                continue
            
            price = float(stock.last_price)
            price_matches = False
            
            # Check if stock matches any selected price range
            for price_range in price_ranges:
                if price_range == 'under_10' and price < 10:
                    price_matches = True
                    break
                elif price_range == '10_to_30' and 10 <= price <= 30:
                    price_matches = True
                    break
                elif price_range == '30_to_50' and 30 <= price <= 50:
                    price_matches = True
                    break
                elif price_range == '50_to_100' and 50 <= price <= 100:
                    price_matches = True
                    break
                elif price_range == 'over_100' and price > 100:
                    price_matches = True
                    break
            
            if price_matches:
                # Calculate wheel score and entry signal for discovery stocks
                stock.in_watchlist = stock.ticker in watchlist_tickers
                try:
                    score_data = calculate_wheel_score(stock)
                    stock.wheel_score = score_data['total_score']
                    stock.score_breakdown = score_data
                    
                    entry_signal = calculate_entry_signal(stock)
                    stock.entry_signal = entry_signal['signal']
                    stock.entry_quality = entry_signal['quality']
                    stock.entry_score = entry_signal['score']
                    stock.entry_color = entry_signal['signal_color']
                except Exception as e:
                    logger.warning(f"Error calculating scores for {stock.ticker}: {e}")
                    stock.wheel_score = 0
                    stock.score_breakdown = {'grade': 'N/A', 'total_score': 0}
                    stock.entry_signal = 'N/A'
                    stock.entry_color = 'gray'
                discovery_stocks.append(stock)
    
    # Sort stocks
    sort_by = request.GET.get('sort', 'price')
    
    # Sort preferred stocks (always available)
    if sort_by == 'price':
        preferred_stock_scores.sort(key=lambda x: float(x.last_price) if x.last_price else 0, reverse=True)
    elif sort_by == 'volume':
        preferred_stock_scores.sort(key=lambda x: x.avg_volume if x.avg_volume else 0, reverse=True)
    elif sort_by == 'wheel_score':
        preferred_stock_scores.sort(key=lambda x: x.wheel_score if hasattr(x, 'wheel_score') else 0, reverse=True)
    
    # Sort discovery stocks (only if filters were applied and we have results)
    if discovery_stocks:
        if sort_by == 'price':
            discovery_stocks.sort(key=lambda x: float(x.last_price) if x.last_price else 0, reverse=True)
        elif sort_by == 'volume':
            discovery_stocks.sort(key=lambda x: x.avg_volume if x.avg_volume else 0, reverse=True)
        elif sort_by == 'wheel_score':
            discovery_stocks.sort(key=lambda x: x.wheel_score if hasattr(x, 'wheel_score') else 0, reverse=True)
    
    # OPTIONS TAB DATA
    selected_ticker = request.GET.get('ticker', '')
    selected_stock = None
    options = []
    available_stocks = Stock.objects.filter(options__isnull=False).distinct().order_by('ticker')

    if selected_ticker:
        selected_stock = Stock.objects.filter(ticker=selected_ticker).first()
        if selected_stock:
            from datetime import date as _date, timedelta as _timedelta
            today = _date.today()
            dte_filter = request.GET.get('dte_filter', 'weekly')
            options_qs = Option.objects.filter(stock=selected_stock)

            if dte_filter == 'short':       # < 7 DTE
                options_qs = options_qs.filter(expiry_date__gte=today,
                                               expiry_date__lt=today + _timedelta(days=7))
            elif dte_filter == 'weekly':    # 7–14 DTE
                options_qs = options_qs.filter(expiry_date__gte=today + _timedelta(days=7),
                                               expiry_date__lte=today + _timedelta(days=14))
            elif dte_filter == 'biweekly': # 14–21 DTE
                options_qs = options_qs.filter(expiry_date__gt=today + _timedelta(days=14),
                                               expiry_date__lte=today + _timedelta(days=21))
            elif dte_filter == 'monthly':   # 21–45 DTE
                options_qs = options_qs.filter(expiry_date__gt=today + _timedelta(days=21),
                                               expiry_date__lte=today + _timedelta(days=45))
            elif dte_filter == 'leaps':     # 45–120 DTE
                options_qs = options_qs.filter(expiry_date__gt=today + _timedelta(days=45),
                                               expiry_date__lte=today + _timedelta(days=120))
            else:                           # 'all' — no DTE restriction
                options_qs = options_qs.filter(expiry_date__gte=today)

            # Apply min APY filter (calculated in template; pre-filter by mid_price > 0)
            options = options_qs.order_by('expiry_date', 'strike')
    
    # SIGNALS TAB DATA
    signals = Signal.objects.filter(status='OPEN').select_related('stock', 'option').order_by('-quality_score')[:20]
    
    context = {
        'last_updated': last_updated,
        # Positions
        'stock_positions': stock_positions,
        # Positions lists
        'open_positions': open_positions_list,
        'closed_positions': closed_positions,
        # Stocks - two separate lists
        'preferred_stocks': preferred_stock_scores,  # For "My Stocks" tab
        'open_option_tickers': {p.stock.ticker for p in open_positions_list},
        'open_stock_tickers': {sp.stock.ticker for sp in stock_positions},
        'open_options_by_ticker': _build_open_options_by_ticker(open_positions_list),
        'stocks': discovery_stocks,  # For "Discovery" tab
        'sort_by': sort_by,
        'price_ranges': price_ranges,  # Multi-select price ranges
        'filters_applied': filters_applied,  # Whether any filters are applied
        'watchlist_tickers': watchlist_tickers,  # For checking if stock is in watchlist
        # Options
        'selected_ticker': selected_ticker,
        'selected_stock': selected_stock,
        'options': options,
        'available_stocks': available_stocks,
        # Signals
        'signals': signals,
        # Account
        'account_summary': {},  # loaded async via JS
    }
    
    # Add debug and VNC links to context
    context['ibkr_debug_url'] = '/ibkr/api/ibkr/debug/'
    context['vnc_url'] = '/ibkr/vnc/'
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
    
    # Add grade with proper hex colors for good contrast
    if scores['total_score'] >= 80:
        scores['grade'] = 'A'
        scores['grade_color'] = '#10b981'  # green-500
    elif scores['total_score'] >= 65:
        scores['grade'] = 'B'
        scores['grade_color'] = '#3b82f6'  # blue-500
    elif scores['total_score'] >= 50:
        scores['grade'] = 'C'
        scores['grade_color'] = '#f59e0b'  # amber-500 (visible with white text)
    else:
        scores['grade'] = 'D'
        scores['grade_color'] = '#ef4444'  # red-500
    
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
        signal_data['signal_color'] = '#10b981'
    elif score >= 60:
        signal_data['signal'] = 'GOOD ENTRY'
        signal_data['quality'] = 'GOOD'
        signal_data['signal_color'] = '#3b82f6'
    elif score >= 45:
        signal_data['signal'] = 'WAIT FOR DIP'
        signal_data['quality'] = 'FAIR'
        signal_data['signal_color'] = '#d97706'  # Darker amber for better contrast with white text
    else:
        signal_data['signal'] = 'AVOID PUTS'
        signal_data['quality'] = 'POOR'
        signal_data['signal_color'] = '#ef4444'
    
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
    
    # Calculate IV Rank (current IV relative to 52-week range)
    try:
        current_iv = stock.options.filter(
            option_type='PUT',
            implied_volatility__isnull=False,
            dte__gte=14,
            dte__lte=45
        ).aggregate(Avg('implied_volatility'))['implied_volatility__avg']
        
        if current_iv:
            # Get 52-week IV range
            all_ivs = stock.options.filter(
                option_type='PUT',
                implied_volatility__isnull=False
            ).values_list('implied_volatility', flat=True)
            
            if all_ivs:
                iv_list = list(all_ivs)
                iv_min = min(iv_list)
                iv_max = max(iv_list)
                
                if iv_max > iv_min:
                    iv_rank = ((current_iv - iv_min) / (iv_max - iv_min)) * 100
                    analysis['iv_rank'] = round(iv_rank, 1)
    except Exception as e:
        pass
    
    # Generate actionable signals from current options data - ALWAYS show available options
    signals = []
    try:
        # Get PUT options for this stock sorted by DTE (nearest first)
        # Note: mid_price is a @property, cannot filter in DB query
        all_puts = Option.objects.filter(
            stock=stock,
            option_type='PUT',
        ).order_by('expiry_date')  # Sort by expiry (nearest first) not IV
        
        # Filter in Python for DTE range and valid mid_price - get up to 20 to ensure we catch good deltas
        candidate_puts = [p for p in all_puts if p.dte and 14 <= p.dte <= 60 and p.mid_price and p.delta][:20]
        
        best_entry_trade = None
        best_apy = 0
        
        for put in candidate_puts:
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
                    
                    # Track the best entry trade (ideal delta range 0.25-0.35, DTE 14-45, highest APY)
                    if 0.25 <= delta_abs <= 0.35 and 14 <= put.dte <= 45 and apy > best_apy:
                        best_apy = apy
                        premium_per_contract = float(put.mid_price) * 100
                        cost_if_assigned = float(put.strike) * 100
                        roi_pct = (premium_per_contract / cost_if_assigned) * 100 if cost_if_assigned > 0 else 0
                        
                        best_entry_trade = {
                            'strike': float(put.strike),
                            'expiry': put.expiry_date,  # Fixed: was expiration_date
                            'dte': put.dte,
                            'delta': put.delta,
                            'premium': float(put.mid_price),
                            'premium_per_contract': premium_per_contract,
                            'cost_if_assigned': cost_if_assigned,
                            'roi_pct': round(roi_pct, 2),
                            'apy_pct': round(apy, 1),
                            'bid': float(put.bid) if put.bid else 0,
                            'ask': float(put.ask) if put.ask else 0,
                            'iv': float(put.implied_volatility) if put.implied_volatility else 0
                        }
        
        # Add best entry trade to analysis
        analysis['best_entry_trade'] = best_entry_trade
    except Exception as e:
        # Log the error for debugging
        import traceback
        print(f"❌ Error generating options signals: {e}")
        print(traceback.format_exc())
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
        messages.warning(request, '⚠️ No tickers in watchlist to refresh. Add stocks first using the form above.')
        # Redirect back to referring page or dashboard
        if referer:
            return redirect(referer)
        return redirect('ibkr:dashboard')
    
    success_count = 0
    error_count = 0
    error_details = []
    
    for ticker in tickers:
        try:
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
                logger.info(f"Successfully refreshed {ticker}: ${stock_data.get('last_price', 0):.2f}")
            else:
                error_count += 1
                error_details.append(f"{ticker}: No data returned")
                logger.warning(f"Failed to fetch data for {ticker}: No data returned")
        except Exception as e:
            error_count += 1
            error_details.append(f"{ticker}: {str(e)}")
            logger.error(f"Error refreshing {ticker}: {e}", exc_info=True)
    
    if success_count > 0:
        messages.success(request, f'✅ Refreshed {success_count} stock(s) successfully')
    if error_count > 0:
        messages.warning(request, f'⚠️ Failed to refresh {error_count} stock(s). Check logs for details.')
        if error_details:
            logger.error(f"Refresh errors: {', '.join(error_details)}")
    
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

    # Check if refresh requested (support both ?refresh=true and ?refresh=1)
    if request.GET.get('refresh') in ('true', '1', 'yes'):
        results = refresh_health_check()
        messages.success(request, 'Health check refreshed')
    else:
        health_service = get_health_check_service()
        results = health_service.results

    # AJAX support: return JSON for XHR requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.http import JsonResponse
        import json
        return JsonResponse(results, safe=False, json_dumps_params={'default': str})

    # Convert timestamp to Abu Dhabi time (UTC+4) for display
    import pytz
    abudhabi_tz = pytz.timezone('Asia/Dubai')
    timestamp_ad = results['timestamp'].astimezone(abudhabi_tz)

    context = {
        'health_results': results,
        'checks': results['checks'],
        'overall_status': results['overall_status'],
        'timestamp': timestamp_ad,
        'passed': results.get('passed', 0),
        'warnings': results.get('warnings', 0),
        'failed': results.get('failed', 0),
        'total_time_ms': results.get('total_time_ms', 0),
    }

    return render(request, 'ibkr/health_check.html', context)


def gateway_control(request):
    """IB Gateway control panel - unified API status + VNC login"""
    client = IBKRClient()
    is_connected = client.ensure_connected()

    import os
    ibkr_host = client.host
    in_docker = ibkr_host not in ('localhost', '127.0.0.1')
    # noVNC is always accessed at localhost:6080 from the browser.
    # Docker maps container port 6080 to host port 6080.
    # Override with VNC_URL env var for Railway/cloud deployments.
    vnc_url = os.environ.get('VNC_URL', 'http://localhost:6080')

    # Detect Railway / cloud environment (VNC iframe won't work over HTTPS due to mixed-content)
    is_cloud = bool(
        os.environ.get('RAILWAY_ENVIRONMENT')
        or os.environ.get('RAILWAY_PROJECT_ID')
        or os.environ.get('RENDER')
        or os.environ.get('HEROKU_APP_NAME')
    )

    context = {
        'is_connected': is_connected,
        'gateway_host': client.host,
        'gateway_port': client.port,
        'client_id': client.client_id,
        'vnc_url': vnc_url,
        'in_docker': in_docker,
        'is_cloud': is_cloud,
    }

    return render(request, 'ibkr/gateway_control.html', context)


def account_summary_api(request):
    """JSON API: fetch live IBKR account summary for async page loading."""
    try:
        client = IBKRClient()
        if not client.ensure_connected():
            return JsonResponse({'connected': False, 'error': 'Not connected to IBKR Gateway'})
        raw = client.get_account_summary() or {}

        def _f(key, default='—'):
            v = raw.get(key, '')
            try:
                return f"{float(v):,.2f}" if v else default
            except Exception:
                return v or default

        return JsonResponse({
            'connected': True,
            'net_liquidation':  _f('NetLiquidation'),
            'total_cash':       _f('TotalCashValue'),
            'buying_power':     _f('BuyingPower'),
            'position_value':   _f('GrossPositionValue'),
            'unrealized_pnl':   _f('UnrealizedPnL'),
            'realized_pnl':     _f('RealizedPnL'),
            'available_funds':  _f('AvailableFunds'),
            'maint_margin':     _f('MaintMarginReq'),
            'currency':         raw.get('Currency', 'USD'),
        })
    except Exception as e:
        logger.warning(f"account_summary_api error: {e}")
        return JsonResponse({'connected': False, 'error': str(e)}, status=500)


def gateway_status_api(request):
    """API endpoint for gateway connection status — passive check only, no reconnect attempt."""
    client = IBKRClient()
    
    try:
        is_connected = client.is_connected()   # does NOT try to reconnect
        
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


def discover_stocks_api(request):
    """API endpoint to run discover_stocks management command and add new tickers to the DB"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    from django.core.management import call_command
    from io import StringIO
    import json

    try:
        body = json.loads(request.body) if request.body else {}
        preset = body.get('preset', 'popular')

        before_count = Stock.objects.count()

        output = StringIO()
        call_command('discover_stocks', preset=preset, stdout=output, stderr=output)

        after_count = Stock.objects.count()
        new_stocks = after_count - before_count

        return JsonResponse({
            'success': True,
            'new_stocks': new_stocks,
            'total_stocks': after_count,
            'message': f'Added {new_stocks} new stocks. Total: {after_count}.',
            'output': output.getvalue()[-500:],  # last 500 chars of output
        })
    except Exception as e:
        logger.error(f'discover_stocks_api error: {e}')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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


def auto_expire_positions_api(request):
    """Manually trigger auto-expire of stale open positions."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        from datetime import date
        today = date.today()
        stale_qs = OptionPosition.objects.filter(status='OPEN', expiry_date__lt=today)
        count_before = stale_qs.count()
        _auto_expire_stale_positions()
        return JsonResponse({
            'success': True,
            'expired_count': count_before,
            'message': f'{count_before} position(s) auto-expired/assigned.',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
    """Redirect VNC viewer to the unified gateway control page"""
    from django.shortcuts import redirect
    return redirect('ibkr:gateway_control')


def add_to_watchlist(request):
    """Add a stock to the user's preferred watchlist"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ticker = data.get('ticker', '').upper().strip()
            
            if not ticker:
                return JsonResponse({'success': False, 'error': 'Ticker is required'}, status=400)
            
            # Add to watchlist
            watchlist_item, created = Watchlist.objects.get_or_create(ticker=ticker)
            
            if created:
                # If the stock doesn't exist, fetch its data
                if not Stock.objects.filter(ticker=ticker).exists():
                    try:
                        stock_data = StockDataFetcher.fetch_stock_data(ticker)
                        if stock_data:
                            stock, _ = Stock.objects.update_or_create(
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
                            
                            # Calculate technical indicators
                            try:
                                indicators_data = TechnicalAnalysisService.calculate_all_indicators(ticker)
                                if indicators_data:
                                    StockIndicator.objects.update_or_create(
                                        stock=stock,
                                        defaults={
                                            'rsi': indicators_data.get('rsi'),
                                            'rsi_signal': indicators_data.get('rsi_signal', 'NEUTRAL'),
                                            'ema_50': indicators_data.get('ema_50'),
                                            'ema_200': indicators_data.get('ema_200'),
                                            'ema_trend': indicators_data.get('ema_trend', 'NEUTRAL'),
                                            'bb_upper': indicators_data.get('bb_upper'),
                                            'bb_middle': indicators_data.get('bb_middle'),
                                            'bb_lower': indicators_data.get('bb_lower'),
                                            'bb_position': indicators_data.get('bb_position', ''),
                                            'support_level_1': indicators_data.get('support_level_1'),
                                            'support_level_2': indicators_data.get('support_level_2'),
                                            'support_level_3': indicators_data.get('support_level_3'),
                                            'resistance_level_1': indicators_data.get('resistance_level_1'),
                                            'resistance_level_2': indicators_data.get('resistance_level_2'),
                                            'resistance_level_3': indicators_data.get('resistance_level_3'),
                                            'price_history': indicators_data.get('price_history', []),
                                            'last_calculated': timezone.now(),
                                        }
                                    )
                            except Exception as e:
                                logger.error(f"Error calculating indicators for {ticker}: {e}")
                    except Exception as e:
                        logger.error(f"Error fetching data for {ticker}: {e}")
                
                return JsonResponse({'success': True, 'message': f'{ticker} added to your watchlist!'})
            else:
                return JsonResponse({'success': True, 'message': f'{ticker} is already in your watchlist.'})
        
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error adding to watchlist: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)


# ==========================================
# AUTO-TRADE API ENDPOINTS
# ==========================================

def auto_trade_suggest_tickers_api(request):
    """
    GET: Return top-scoring stocks NOT already in the watchlist,
    as candidates to add to auto-trade.
    """
    from apps.ibkr.models import StockWheelScore, Stock

    # Tickers already in watchlist
    existing = set(Watchlist.objects.values_list('ticker', flat=True))

    # All scored stocks outside the watchlist, best first
    scores = (
        StockWheelScore.objects
        .select_related('stock')
        .exclude(stock__ticker__in=existing)
        .filter(grade__in=('A', 'B'))
        .order_by('-total_score')
    )[:30]

    suggestions = []
    seen = set()
    for s in scores:
        ticker = s.stock.ticker
        if ticker in seen:
            continue
        seen.add(ticker)
        suggestions.append({
            'ticker': ticker,
            'name': s.stock.name or ticker,
            'grade': s.grade,
            'score': int(s.total_score),
            'last_price': str(s.stock.last_price) if s.stock.last_price else None,
            'sector': s.stock.sector or '',
        })

    return JsonResponse({'success': True, 'suggestions': suggestions})


def auto_trade_config_api(request):
    """GET: load config + all stock configs. POST: save global config + stock toggles."""
    from apps.ibkr.models import AutoTradeConfig, AutoTradeStockConfig, Stock, StockWheelScore
    from apps.ibkr.services.auto_trade_engine import get_month_progress

    if request.method == 'GET':
        try:
            config = AutoTradeConfig.get_config()
            progress = get_month_progress()

            # Build per-stock list (all watchlist stocks)
            watchlist_tickers = list(Watchlist.objects.values_list('ticker', flat=True))
            stocks = Stock.objects.filter(ticker__in=watchlist_tickers).order_by('ticker')

            stock_data = []
            for stock in stocks:
                try:
                    sc = AutoTradeStockConfig.objects.get(stock=stock)
                except AutoTradeStockConfig.DoesNotExist:
                    sc = None

                score = StockWheelScore.objects.filter(stock=stock).first()
                from apps.ibkr.models import OptionPosition, StockPosition
                open_pos = OptionPosition.objects.filter(stock=stock, status='OPEN').first()
                stock_pos = StockPosition.objects.filter(stock=stock).first()

                if open_pos:
                    status_badge = f'OPEN {open_pos.option_type}'
                elif stock_pos and stock_pos.quantity >= 100:
                    status_badge = f'HOLDING {stock_pos.quantity} shares'
                else:
                    status_badge = 'No Position'

                stock_data.append({
                    'ticker': stock.ticker,
                    'name': stock.name,
                    'last_price': str(stock.last_price) if stock.last_price else None,
                    'grade': score.grade if score else None,
                    'total_score': float(score.total_score) if score else None,
                    'status': status_badge,
                    'auto_trade_enabled': sc.enabled if sc else False,
                    'max_contracts': sc.max_contracts if sc else None,
                })

            return JsonResponse({
                'success': True,
                'config': {
                    'enabled': config.enabled,
                    'monthly_goal': str(config.monthly_goal),
                    'risk_level': config.risk_level,
                    'last_run': config.last_run.isoformat() if config.last_run else None,
                },
                'progress': {
                    'earned': str(progress['earned']),
                    'goal': str(progress['goal']),
                    'remaining': str(progress['remaining']),
                    'pct': progress['pct'],
                },
                'stocks': stock_data,
            })
        except Exception as e:
            logger.error(f'auto_trade_config_api GET error: {e}', exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        config = AutoTradeConfig.get_config()

        # Global settings
        if 'enabled' in data:
            config.enabled = bool(data['enabled'])
        if 'monthly_goal' in data:
            try:
                config.monthly_goal = float(data['monthly_goal'])
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': 'Invalid monthly_goal'}, status=400)
        if 'risk_level' in data:
            if data['risk_level'] in ('conservative', 'moderate', 'aggressive'):
                config.risk_level = data['risk_level']
        config.save()

        # Per-stock toggles: [{'ticker': 'F', 'enabled': true, 'max_contracts': null}, ...]
        from apps.ibkr.models import AutoTradeStockConfig, Stock
        stock_updates = data.get('stocks', [])
        for su in stock_updates:
            ticker = su.get('ticker', '').upper()
            try:
                stock = Stock.objects.get(ticker=ticker)
                sc, _ = AutoTradeStockConfig.objects.get_or_create(stock=stock)
                if 'enabled' in su:
                    sc.enabled = bool(su['enabled'])
                if 'max_contracts' in su:
                    mc = su['max_contracts']
                    sc.max_contracts = int(mc) if mc else None
                sc.save()
            except Stock.DoesNotExist:
                pass

        return JsonResponse({'success': True, 'message': 'Auto-trade config saved.'})

    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)


def auto_trade_run_api(request):
    """POST: trigger one auto-trade cycle immediately."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    import threading
    from apps.ibkr.services.auto_trade_engine import run_auto_trade_cycle

    dry_run = json.loads(request.body).get('dry_run', False) if request.body else False

    result_holder = {}

    def _run():
        try:
            result_holder['summary'] = run_auto_trade_cycle(dry_run=dry_run)
        except Exception as e:
            result_holder['error'] = str(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)  # wait up to 2 min

    if 'error' in result_holder:
        return JsonResponse({'success': False, 'error': result_holder['error']}, status=500)

    summary = result_holder.get('summary', {})
    return JsonResponse({
        'success': True,
        'dry_run': dry_run,
        'trades': summary.get('trades', 0),
        'skipped': summary.get('skipped', 0),
        'earned': str(summary.get('earned', 0)),
        'goal_met': summary.get('goal_met', False),
        'errors': summary.get('errors', []),
    })


def auto_trade_logs_api(request):
    """GET: return last 30 AutoTradeLog entries."""
    from apps.ibkr.models import AutoTradeLog

    logs = (
        AutoTradeLog.objects
        .select_related('stock')
        .order_by('-timestamp')[:30]
    )
    data = []
    for log in logs:
        data.append({
            'id': log.id,
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'ticker': log.stock.ticker,
            'action': log.action,
            'status': log.status,
            'strike': str(log.strike) if log.strike else None,
            'expiry_date': str(log.expiry_date) if log.expiry_date else None,
            'contracts': log.contracts,
            'premium_per_contract': str(log.premium_per_contract) if log.premium_per_contract else None,
            'total_premium': str(log.total_premium) if log.total_premium else None,
            'ibkr_order_id': log.ibkr_order_id,
            'reason': log.reason,
            'goal_contribution': str(log.goal_contribution) if log.goal_contribution else None,
        })
    return JsonResponse({'success': True, 'logs': data})


def auto_trade_logs_clear_api(request):
    """POST: delete all AutoTradeLog entries."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    from apps.ibkr.models import AutoTradeLog
    deleted, _ = AutoTradeLog.objects.all().delete()
    logger.info(f'Auto-trade log cleared — {deleted} entries deleted.')
    return JsonResponse({'success': True, 'deleted': deleted})


def auto_trade_progress_api(request):
    """GET: current month earned vs goal."""
    from apps.ibkr.services.auto_trade_engine import get_month_progress
    progress = get_month_progress()
    return JsonResponse({
        'success': True,
        'earned': str(progress['earned']),
        'goal': str(progress['goal']),
        'remaining': str(progress['remaining']),
        'pct': progress['pct'],
    })


def auto_trade_positions_monitor_api(request):
    """GET: open positions with moneyness, DTE, and action recommendation."""
    from apps.ibkr.models import OptionPosition
    from datetime import date

    today = date.today()
    positions = (
        OptionPosition.objects
        .filter(status='OPEN')
        .select_related('stock')
        .order_by('expiry_date')
    )

    data = []
    for p in positions:
        price = float(p.stock.last_price) if p.stock.last_price else None
        strike = float(p.strike)
        dte = (p.expiry_date - today).days
        prem = float(p.total_premium) if p.total_premium else 0
        entry_prem = float(p.entry_premium) if p.entry_premium else 0
        contracts = p.contracts or 1

        # Moneyness
        if price is not None:
            if p.option_type == 'PUT':
                itm = price < strike
                pct_away = (strike - price) / price * 100
            else:
                itm = price > strike
                pct_away = (price - strike) / price * 100
            if itm:
                moneyness = 'ITM'
                pct_label = f'{abs(pct_away):.1f}% in-the-money'
            else:
                moneyness = 'OTM'
                pct_label = f'{abs(pct_away):.1f}% out-of-the-money'
        else:
            itm = False
            pct_away = 0
            moneyness = 'UNKNOWN'
            pct_label = 'price unavailable'

        # Premium decay — current value vs entry
        # Rough estimate: for OTM near expiry most value is gone
        decay_pct = None
        if entry_prem > 0 and p.option and p.option.ask is not None:
            try:
                current_val = float(p.option.ask) * contracts * 100
                decay_pct = round((1 - current_val / prem) * 100, 1) if prem else None
            except Exception:
                pass

        # Recommendation logic
        if itm and p.option_type == 'PUT':
            rec = 'ASSIGN'
            rec_label = 'Let assign — collect shares'
            rec_color = 'orange'
            rec_icon = '📥'
        elif itm and p.option_type == 'CALL':
            rec = 'ASSIGN'
            rec_label = 'Let assign — shares called away'
            rec_color = 'orange'
            rec_icon = '📤'
        elif not itm and dte <= 5:
            rec = 'EXPIRE'
            rec_label = 'Let expire worthless — keep premium'
            rec_color = 'green'
            rec_icon = '✅'
        elif not itm and decay_pct is not None and decay_pct >= 50:
            rec = 'CLOSE_EARLY'
            rec_label = f'50% profit rule — consider closing early ({decay_pct:.0f}% decayed)'
            rec_color = 'blue'
            rec_icon = '💰'
        elif not itm and dte <= 21:
            rec = 'WATCH'
            rec_label = 'Watch — approaching expiry, mostly safe'
            rec_color = 'yellow'
            rec_icon = '👀'
        else:
            rec = 'HOLD'
            rec_label = 'Hold — plenty of time remaining'
            rec_color = 'gray'
            rec_icon = '⏳'

        data.append({
            'ticker': p.stock.ticker,
            'option_type': p.option_type,
            'strike': str(p.strike),
            'expiry_date': str(p.expiry_date),
            'dte': dte,
            'contracts': contracts,
            'total_premium': f'{prem:.2f}',
            'entry_premium_per': f'{entry_prem:.2f}',
            'current_price': f'{price:.2f}' if price else None,
            'moneyness': moneyness,
            'pct_label': pct_label,
            'itm': itm,
            'decay_pct': decay_pct,
            'recommendation': rec,
            'rec_label': rec_label,
            'rec_color': rec_color,
            'rec_icon': rec_icon,
        })

    return JsonResponse({'success': True, 'positions': data})


def remove_from_watchlist(request):
    """Remove a stock from the user's preferred watchlist"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ticker = data.get('ticker', '').upper().strip()
            
            if not ticker:
                return JsonResponse({'success': False, 'error': 'Ticker is required'}, status=400)
            
            # Remove from watchlist
            deleted_count, _ = Watchlist.objects.filter(ticker=ticker).delete()
            
            if deleted_count > 0:
                return JsonResponse({'success': True, 'message': f'{ticker} removed from your watchlist.'})
            else:
                return JsonResponse({'success': False, 'error': f'{ticker} was not in your watchlist.'}, status=404)
        
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error removing from watchlist: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

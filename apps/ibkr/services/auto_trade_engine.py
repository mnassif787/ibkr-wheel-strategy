"""
Auto-Trade Engine
=================
Implements the wheel strategy auto-trading loop:
  1. Check if monthly goal is already met.
  2. For each enabled stock (best-scoring first):
     a. If holding shares → sell Covered CALL.
     b. Otherwise        → sell Cash-Secured PUT.
  3. Log every attempt to AutoTradeLog.
  4. Stop once the monthly income goal is reached.

Entry point: run_auto_trade_cycle(dry_run=False)
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Monthly-goal progress
# ---------------------------------------------------------------------------

def get_month_progress():
    """
    Return a dict with earned / goal / remaining / pct for the current calendar month.

    'earned' = realized_pl from positions closed/expired this month
              + total_premium from positions still OPEN that were opened this month
    """
    from apps.ibkr.models import AutoTradeConfig, OptionPosition

    config = AutoTradeConfig.get_config()
    today = date.today()

    # Realized from closed/expired positions this month
    closed_qs = OptionPosition.objects.filter(
        status__in=['CLOSED', 'EXPIRED', 'ASSIGNED'],
        exit_date__year=today.year,
        exit_date__month=today.month,
    )
    realized = sum(
        float(p.realized_pl) for p in closed_qs if p.realized_pl is not None
    )

    # Locked-in premium from still-OPEN positions opened this month
    open_qs = OptionPosition.objects.filter(
        status='OPEN',
        entry_date__year=today.year,
        entry_date__month=today.month,
    )
    locked_in = sum(
        float(p.total_premium) for p in open_qs if p.total_premium is not None
    )

    earned = Decimal(str(round(realized + locked_in, 2)))
    goal = config.monthly_goal
    remaining = max(goal - earned, Decimal('0'))
    pct = float(earned / goal * 100) if goal > 0 else 0.0

    return {
        'earned': earned,
        'goal': goal,
        'remaining': remaining,
        'pct': round(pct, 1),
    }


# ---------------------------------------------------------------------------
# IBKR buying power
# ---------------------------------------------------------------------------

def _get_buying_power(client):
    """Return AvailableFunds from IBKR account summary as Decimal, or None on error."""
    try:
        summary = client.get_account_summary()
        val = summary.get('AvailableFunds') or summary.get('available_funds')
        if val is not None:
            return Decimal(str(val))
    except Exception as e:
        logger.warning(f'Could not fetch buying power: {e}')
    return None


def _contracts_affordable(strike: Decimal, buying_power: Decimal) -> int:
    """How many CSP contracts buying_power can collateralize at given strike."""
    required_per_contract = strike * 100
    if required_per_contract <= 0:
        return 0
    return int(buying_power // required_per_contract)


# ---------------------------------------------------------------------------
# Option selection helpers
# ---------------------------------------------------------------------------

def _find_best_put(stock, stock_cfg, global_cfg):
    """
    Scan the Option table for the best cash-secured PUT for this stock.
    Returns a dict with the chosen option details, or None if nothing qualifies.
    """
    from apps.ibkr.models import Option

    dte_min, dte_max = global_cfg.dte_range()
    delta_min, delta_max = global_cfg.delta_range()

    # Use per-stock overrides if set
    if stock_cfg.dte_min_override is not None:
        dte_min = stock_cfg.dte_min_override
    if stock_cfg.dte_max_override is not None:
        dte_max = stock_cfg.dte_max_override
    if stock_cfg.delta_min_override is not None:
        delta_min = float(stock_cfg.delta_min_override)
    if stock_cfg.delta_max_override is not None:
        delta_max = float(stock_cfg.delta_max_override)

    today = date.today()
    from datetime import timedelta
    earliest = today + timedelta(days=dte_min)
    latest = today + timedelta(days=dte_max)

    # PUTs with negative delta (stored as negative or positive abs)
    # We store absolute values in the DB so compare directly.
    candidates = list(
        Option.objects.filter(
            stock=stock,
            option_type='PUT',
            expiry_date__range=(earliest, latest),
        ).exclude(bid=None).exclude(ask=None)
        .order_by('expiry_date', 'strike')
    )

    if not candidates:
        return None

    # Filter by delta range (stored as absolute value)
    qualified = []
    for opt in candidates:
        if opt.delta is None:
            continue
        abs_delta = abs(float(opt.delta))
        if delta_min <= abs_delta <= delta_max:
            mid = (float(opt.bid) + float(opt.ask)) / 2
            premium_yield = mid / float(opt.strike) if opt.strike else 0
            qualified.append({
                'option': opt,
                'mid': mid,
                'premium_yield': premium_yield,
            })

    if not qualified:
        # Relax: just take highest premium yield in the window
        for opt in candidates:
            mid = (float(opt.bid) + float(opt.ask)) / 2 if (opt.bid and opt.ask) else 0
            premium_yield = mid / float(opt.strike) if opt.strike else 0
            qualified.append({'option': opt, 'mid': mid, 'premium_yield': premium_yield})

    if not qualified:
        return None

    best = max(qualified, key=lambda x: x['premium_yield'])
    opt = best['option']
    return {
        'option_type': 'PUT',
        'strike': opt.strike,
        'expiry_date': opt.expiry_date,
        'expiry_str': opt.expiry_date.strftime('%Y%m%d'),
        'mid': Decimal(str(round(best['mid'], 2))),
        'dte': (opt.expiry_date - today).days,
        'delta': float(opt.delta) if opt.delta else None,
        'premium_yield': best['premium_yield'],
    }


def _find_best_call(stock, shares_held: int, stock_cfg, global_cfg):
    """
    Scan for the best covered CALL ~5-10% OTM for the held shares.
    Returns a dict or None.
    """
    from apps.ibkr.models import Option

    today = date.today()
    from datetime import timedelta
    # Covered calls: shorter window (14-30 days)
    earliest = today + timedelta(days=14)
    latest = today + timedelta(days=30)

    last_price = float(stock.last_price) if stock.last_price else None
    if not last_price:
        return None

    # OTM strikes: 3-15% above current price
    strike_min = Decimal(str(round(last_price * 1.03, 2)))
    strike_max = Decimal(str(round(last_price * 1.15, 2)))

    candidates = list(
        Option.objects.filter(
            stock=stock,
            option_type='CALL',
            expiry_date__range=(earliest, latest),
            strike__range=(strike_min, strike_max),
        ).exclude(bid=None).exclude(ask=None)
        .order_by('expiry_date', 'strike')
    )

    if not candidates:
        return None

    qualified = []
    for opt in candidates:
        mid = (float(opt.bid) + float(opt.ask)) / 2
        if mid <= 0:
            continue
        premium_yield = mid / last_price
        qualified.append({'option': opt, 'mid': mid, 'premium_yield': premium_yield})

    if not qualified:
        return None

    best = max(qualified, key=lambda x: x['premium_yield'])
    opt = best['option']
    # Max covered calls = shares // 100
    max_contracts = shares_held // 100
    return {
        'option_type': 'CALL',
        'strike': opt.strike,
        'expiry_date': opt.expiry_date,
        'expiry_str': opt.expiry_date.strftime('%Y%m%d'),
        'mid': Decimal(str(round(best['mid'], 2))),
        'dte': (opt.expiry_date - today).days,
        'delta': float(opt.delta) if opt.delta else None,
        'premium_yield': best['premium_yield'],
        'max_contracts': max_contracts,
    }


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------

def _is_market_hours():
    """Return True if current time is within NYSE regular hours (9:30–16:00 ET Mon–Fri)."""
    import pytz
    try:
        et = pytz.timezone('America/New_York')
    except Exception:
        # If pytz not available, fall through (assume open)
        return True
    now_et = datetime.now(et)
    if now_et.weekday() >= 5:  # Saturday / Sunday
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


def _has_open_position(stock):
    """True if stock already has an open option position."""
    from apps.ibkr.models import OptionPosition
    return OptionPosition.objects.filter(stock=stock, status='OPEN').exists()


def _get_stock_position(stock):
    """Return StockPosition for this stock, or None."""
    from apps.ibkr.models import StockPosition
    return StockPosition.objects.filter(stock=stock).first()


def _get_wheel_grade(stock):
    """Return StockWheelScore.grade or None."""
    from apps.ibkr.models import StockWheelScore
    score = StockWheelScore.objects.filter(stock=stock).first()
    return score.grade if score else None


# ---------------------------------------------------------------------------
# Log writer
# ---------------------------------------------------------------------------

def _write_log(stock, action, status, reason, strike=None, expiry_date=None,
               contracts=0, mid=None, ibkr_order_id='', buying_power=None,
               goal_contribution=None):
    from apps.ibkr.models import AutoTradeLog
    AutoTradeLog.objects.create(
        stock=stock,
        action=action,
        status=status,
        reason=reason,
        strike=strike,
        expiry_date=expiry_date,
        contracts=contracts,
        premium_per_contract=mid,
        total_premium=Decimal(str(mid * contracts)) if (mid and contracts) else None,
        ibkr_order_id=str(ibkr_order_id) if ibkr_order_id else '',
        buying_power_before=buying_power,
        goal_contribution=goal_contribution,
    )


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------

def run_auto_trade_cycle(dry_run=False):
    """
    Run one auto-trade cycle. Iterates enabled stocks (best score first),
    places trades until the monthly goal is met.

    Returns a summary dict: {'trades': int, 'skipped': int, 'earned': Decimal,
                              'goal_met': bool, 'errors': list}
    """
    from apps.ibkr.models import (
        AutoTradeConfig, AutoTradeStockConfig, StockWheelScore
    )
    from apps.ibkr.services.ibkr_client import IBKRClient
    from django.utils import timezone

    summary = {'trades': 0, 'skipped': 0, 'earned': Decimal('0'), 'goal_met': False, 'errors': []}

    config = AutoTradeConfig.get_config()

    if not config.enabled and not dry_run:
        logger.info('Auto-trade is disabled. Exiting cycle.')
        summary['errors'].append('Auto-trade is disabled.')
        return summary

    progress = get_month_progress()
    if progress['remaining'] <= 0:
        logger.info(f'Monthly goal already met (${progress["earned"]:.2f} / ${progress["goal"]:.2f}). Nothing to do.')
        summary['goal_met'] = True
        return summary

    remaining = progress['remaining']
    logger.info(
        f'🤖 Auto-trade cycle starting | Goal: ${progress["goal"]} | '
        f'Earned: ${progress["earned"]} | Remaining: ${remaining}'
    )

    # Fetch buying power once
    client = IBKRClient()
    buying_power = None
    connected = False
    if not dry_run:
        connected = client.ensure_connected()
        if connected:
            buying_power = _get_buying_power(client)
            logger.info(f'💰 Buying power: ${buying_power}')
        else:
            logger.warning('⚠️  IBKR not connected — running in simulation mode (no orders will be placed)')

    # Get enabled stocks ordered by wheel score desc
    stock_configs = (
        AutoTradeStockConfig.objects
        .filter(enabled=True)
        .select_related('stock')
    )

    # Sort by StockWheelScore.total_score descending
    def _score(cfg):
        score_obj = StockWheelScore.objects.filter(stock=cfg.stock).first()
        return score_obj.total_score if score_obj else 0

    ordered_configs = sorted(stock_configs, key=_score, reverse=True)

    for stock_cfg in ordered_configs:
        stock = stock_cfg.stock

        if remaining <= 0:
            logger.info(f'Monthly goal reached. Stopping after {summary["trades"]} trades.')
            summary['goal_met'] = True
            break

        # --- Safety: grade check ---
        grade = _get_wheel_grade(stock)
        if grade not in ('A', 'B'):
            reason = f'Wheel grade {grade or "N/A"} — only A/B allowed'
            logger.info(f'⏭  {stock.ticker}: {reason}')
            _write_log(stock, 'SKIPPED', 'SKIPPED', reason)
            summary['skipped'] += 1
            continue

        # --- Safety: no existing open position ---
        if _has_open_position(stock):
            reason = 'Already has an open option position'
            logger.info(f'⏭  {stock.ticker}: {reason}')
            _write_log(stock, 'SKIPPED', 'SKIPPED', reason)
            summary['skipped'] += 1
            continue

        # --- Determine if CC or CSP ---
        stock_position = _get_stock_position(stock)

        if stock_position and stock_position.quantity >= 100:
            # === Sell Covered CALL ===
            shares = stock_position.quantity
            pick = _find_best_call(stock, shares, stock_cfg, config)
            if pick is None:
                reason = 'No suitable CALL option found in DB (options may need syncing)'
                logger.info(f'⏭  {stock.ticker} CC: {reason}')
                _write_log(stock, 'SKIPPED', 'SKIPPED', reason)
                summary['skipped'] += 1
                continue

            contracts = pick['max_contracts']
            if stock_cfg.max_contracts:
                contracts = min(contracts, stock_cfg.max_contracts)
            if contracts < 1:
                reason = 'Insufficient shares for covered call (need ≥100)'
                _write_log(stock, 'SKIPPED', 'SKIPPED', reason)
                summary['skipped'] += 1
                continue

            total = pick['mid'] * contracts * 100
            logger.info(
                f'📞 {stock.ticker} SELL CALL: strike=${pick["strike"]} '
                f'exp={pick["expiry_date"]} dte={pick["dte"]} '
                f'mid=${pick["mid"]} × {contracts} contracts = ${total:.2f}'
            )

            order_id = ''
            trade_status = 'FILLED'
            if not dry_run and connected:
                try:
                    result = client.sell_option(
                        ticker=stock.ticker,
                        expiry=pick['expiry_str'],
                        strike=float(pick['strike']),
                        right='C',
                        quantity=contracts,
                        order_type='LMT',
                        limit_price=float(pick['mid']),
                    )
                    if result.get('success'):
                        order_id = str(result.get('order_id', ''))
                        trade_status = 'PENDING'
                        logger.info(f'✅ Order placed: id={order_id}')
                    else:
                        trade_status = 'FAILED'
                        err = result.get('error', 'Unknown error')
                        logger.error(f'❌ Order failed: {err}')
                        summary['errors'].append(f'{stock.ticker} CALL: {err}')
                except Exception as e:
                    trade_status = 'FAILED'
                    logger.error(f'❌ Exception placing CALL order for {stock.ticker}: {e}')
                    summary['errors'].append(f'{stock.ticker} CALL exception: {e}')
            elif dry_run:
                trade_status = 'SKIPPED'
                logger.info(f'🔵 DRY RUN — would place SELL CALL order')

            contribution = Decimal(str(round(float(pick['mid']) * contracts * 100, 2)))
            _write_log(
                stock, 'SELL_CALL', trade_status,
                f'CC {contracts}×${pick["strike"]} exp={pick["expiry_date"]} | {("DRY RUN" if dry_run else "placed")}',
                strike=pick['strike'], expiry_date=pick['expiry_date'],
                contracts=contracts, mid=pick['mid'],
                ibkr_order_id=order_id,
                buying_power=buying_power,
                goal_contribution=contribution,
            )

            if trade_status not in ('FAILED',):
                remaining -= contribution
                summary['trades'] += 1
                summary['earned'] += contribution

        else:
            # === Sell Cash-Secured PUT ===
            pick = _find_best_put(stock, stock_cfg, config)
            if pick is None:
                reason = 'No suitable PUT option found in DB (options may need syncing)'
                logger.info(f'⏭  {stock.ticker} CSP: {reason}')
                _write_log(stock, 'SKIPPED', 'SKIPPED', reason)
                summary['skipped'] += 1
                continue

            # How many contracts can we afford?
            if buying_power is not None:
                max_affordable = _contracts_affordable(pick['strike'], buying_power)
            else:
                max_affordable = 1  # can't verify — be conservative

            contracts = max_affordable
            if stock_cfg.max_contracts:
                contracts = min(contracts, stock_cfg.max_contracts)
            if contracts < 1:
                reason = (
                    f'Insufficient buying power for ${pick["strike"]} PUT '
                    f'(need ${float(pick["strike"]) * 100:.0f}, have ${buying_power})'
                )
                logger.info(f'⏭  {stock.ticker}: {reason}')
                _write_log(stock, 'SKIPPED', 'SKIPPED', reason, buying_power=buying_power)
                summary['skipped'] += 1
                continue

            total = float(pick['mid']) * contracts * 100
            logger.info(
                f'📥 {stock.ticker} SELL PUT: strike=${pick["strike"]} '
                f'exp={pick["expiry_date"]} dte={pick["dte"]} '
                f'mid=${pick["mid"]} × {contracts} contracts = ${total:.2f}'
            )

            order_id = ''
            trade_status = 'FILLED'
            if not dry_run and connected:
                try:
                    result = client.sell_option(
                        ticker=stock.ticker,
                        expiry=pick['expiry_str'],
                        strike=float(pick['strike']),
                        right='P',
                        quantity=contracts,
                        order_type='LMT',
                        limit_price=float(pick['mid']),
                    )
                    if result.get('success'):
                        order_id = str(result.get('order_id', ''))
                        trade_status = 'PENDING'
                        logger.info(f'✅ Order placed: id={order_id}')
                    else:
                        trade_status = 'FAILED'
                        err = result.get('error', 'Unknown error')
                        logger.error(f'❌ Order failed: {err}')
                        summary['errors'].append(f'{stock.ticker} PUT: {err}')
                except Exception as e:
                    trade_status = 'FAILED'
                    logger.error(f'❌ Exception placing PUT order for {stock.ticker}: {e}')
                    summary['errors'].append(f'{stock.ticker} PUT exception: {e}')
            elif dry_run:
                trade_status = 'SKIPPED'
                logger.info(f'🔵 DRY RUN — would place SELL PUT order')

            contribution = Decimal(str(round(float(pick['mid']) * contracts * 100, 2)))

            # Deduct reserved capital from buying_power so next stock sees correct amount
            if buying_power is not None and trade_status not in ('FAILED',):
                buying_power -= pick['strike'] * 100 * contracts

            _write_log(
                stock, 'SELL_PUT', trade_status,
                f'CSP {contracts}×${pick["strike"]} exp={pick["expiry_date"]} | {("DRY RUN" if dry_run else "placed")}',
                strike=pick['strike'], expiry_date=pick['expiry_date'],
                contracts=contracts, mid=pick['mid'],
                ibkr_order_id=order_id,
                buying_power=buying_power,
                goal_contribution=contribution,
            )

            if trade_status not in ('FAILED',):
                remaining -= contribution
                summary['trades'] += 1
                summary['earned'] += contribution

    # Update last_run
    if not dry_run:
        config.last_run = timezone.now()
        config.save(update_fields=['last_run'])

    if remaining <= 0:
        summary['goal_met'] = True

    logger.info(
        f'🏁 Auto-trade cycle done | trades={summary["trades"]} '
        f'skipped={summary["skipped"]} earned=${summary["earned"]:.2f} '
        f'goal_met={summary["goal_met"]}'
    )
    return summary

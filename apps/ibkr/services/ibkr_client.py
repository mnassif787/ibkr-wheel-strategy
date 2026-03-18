"""
IBKR Client - Interactive Brokers Connection Handler
Uses ib_insync library for TWS/Gateway API connection
"""
from ib_insync import IB, Stock, Option, util, LimitOrder, MarketOrder
from django.conf import settings
import logging
import threading
import asyncio
import time
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dedicated IB worker thread
# ---------------------------------------------------------------------------
# ib_insync sync wrappers (qualifyContracts, placeOrder, sleep …) call
# asyncio.get_event_loop().run_until_complete() internally.
# That call raises "This event loop is already running" if the loop is live
# (e.g. run_forever).  It also raises "no current event loop" in Django
# request threads (Python 3.10+).
#
# Fix: one permanent worker thread with its OWN event loop that is idle
# between operations.  All IB work is serialised through a queue, so
# get_event_loop() always returns a valid, non-running loop and
# run_until_complete() succeeds.
# ---------------------------------------------------------------------------

import queue as _queue

_work_queue: _queue.Queue = _queue.Queue()
_ib_worker_thread = None
_ib_worker_lock = threading.Lock()
_ib_worker_loop = None   # set by the worker thread


def _ib_worker():
    """Permanent background thread: owns the asyncio event loop for ib_insync."""
    global _ib_worker_loop
    _ib_worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ib_worker_loop)

    while True:
        fn, args, kwargs, promise = _work_queue.get()
        try:
            promise['result'] = fn(*args, **kwargs)
        except Exception as exc:
            promise['error'] = exc
        finally:
            promise['done'].set()


def _ensure_ib_worker():
    global _ib_worker_thread
    with _ib_worker_lock:
        if _ib_worker_thread is None or not _ib_worker_thread.is_alive():
            _ib_worker_thread = threading.Thread(
                target=_ib_worker, daemon=True, name='ibkr-worker'
            )
            _ib_worker_thread.start()
            logger.info('🔁 IBKR worker thread started')


def _ib_run(fn, *args, timeout: int = 30, **kwargs):
    """
    Submit *fn(*args, **kwargs)* to the IB worker thread and block until done.
    Returns the result or re-raises any exception raised inside fn.
    """
    _ensure_ib_worker()
    promise = {'result': None, 'error': None, 'done': threading.Event()}
    _work_queue.put((fn, args, kwargs, promise))
    if not promise['done'].wait(timeout=timeout):
        raise TimeoutError(f'IB operation timed out after {timeout}s')
    if promise['error']:
        raise promise['error']
    return promise['result']


# Per-process singleton IB instance (lives on the event-loop thread)
_ib_instance = None
_connection_lock = threading.Lock()
_last_connect_attempt = 0
_RECONNECT_COOLDOWN = 15   # minimum seconds between reconnect attempts
_consecutive_failures = 0
_MAX_FAILURE_COOLDOWN = 120  # seconds to wait after repeated failures


class IBKRClient:
    """Interactive Brokers API client wrapper"""

    def __init__(self, client_id=None):
        global _ib_instance
        # Create the IB singleton IN the event-loop thread so its internal
        # loop reference is set correctly.
        with _connection_lock:
            if _ib_instance is None:
                _ib_instance = _ib_run(IB)
        self.ib = _ib_instance
        self.host = settings.IBKR_HOST
        self.port = settings.IBKR_PORT
        pid = os.getpid()
        # Use a fixed clientId so the gateway shows only one tab and the
        # exponential backoff gives it time to release the slot between retries.
        self.client_id = client_id or settings.IBKR_CLIENT_ID
        self.connected = False
    
    # ------------------------------------------------------------------
    # Internal helpers that run on the event-loop thread
    # ------------------------------------------------------------------

    def _do_connect(self):
        """Called on the event-loop thread: create fresh IB, connect, set data type."""
        global _ib_instance
        # Use the fixed clientId set at init — the exponential backoff gives the
        # gateway enough time to release the old slot, so we don't need a new id
        # each attempt (which was creating a ghost tab for every failed retry).
        logger.info(f'🔌 Trying clientId={self.client_id}')
        ib = IB()
        ib.connect(self.host, self.port, clientId=self.client_id, timeout=10, readonly=False)
        ib.reqMarketDataType(3)
        _ib_instance = ib
        self.ib = ib

    def _do_disconnect(self):
        try:
            self.ib.disconnect()
        except Exception:
            pass

    def _do_is_connected(self):
        try:
            return self.ib.isConnected()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self):
        """Connect to TWS/Gateway with auto-reconnect logic"""
        global _last_connect_attempt, _consecutive_failures

        with _connection_lock:
            try:
                # If already connected and alive, reuse
                if _ib_run(self._do_is_connected):
                    self.connected = True
                    _consecutive_failures = 0
                    return True

                # Cooldown — back off longer after repeated failures
                now = time.time()
                cooldown = min(
                    _RECONNECT_COOLDOWN * (2 ** min(_consecutive_failures, 3)),
                    _MAX_FAILURE_COOLDOWN
                )
                if now - _last_connect_attempt < cooldown:
                    logger.debug(f'Skipping reconnect (cooldown {cooldown:.0f}s, failures={_consecutive_failures})')
                    return False
                _last_connect_attempt = now

                # Disconnect stale connection
                _ib_run(self._do_disconnect)

                logger.info(
                    f'🔄 Connecting to IBKR at {self.host}:{self.port} '
                    f'(pid={os.getpid()})'
                )

                # All IB construction + connect happen inside the event-loop thread
                _ib_run(self._do_connect)

                self.connected = True
                _consecutive_failures = 0
                logger.info(f'✅ Connected to IBKR at {self.host}:{self.port} clientId={self.client_id} (delayed data enabled)')
                return True

            except Exception as e:
                _consecutive_failures += 1
                logger.warning(f'❌ Failed to connect to IBKR: {e} (failure #{_consecutive_failures})')
                self.connected = False
                return False

    def disconnect(self):
        """Disconnect from TWS/Gateway"""
        if self.connected:
            _ib_run(self._do_disconnect)
            self.connected = False
            logger.info("Disconnected from IBKR")

    def is_connected(self):
        """Check if connected to IBKR"""
        return _ib_run(self._do_is_connected)

    def ensure_connected(self):
        """Ensure connection is active, reconnect if needed. Returns True if connected."""
        if self.is_connected():
            return True
        return self.connect()
    
    def get_stock_contract(self, ticker, exchange='SMART', currency='USD'):
        """
        Create stock contract for ticker
        
        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            exchange: Exchange (default: SMART for automatic routing)
            currency: Currency (default: USD)
        
        Returns:
            Stock contract object
        """
        return Stock(ticker, exchange, currency)
    
    # ------------------------------------------------------------------
    # get_stock_price
    # ------------------------------------------------------------------
    def get_stock_price(self, ticker):
        """Get current stock price"""
        return _ib_run(self._get_stock_price_impl, ticker)

    def _get_stock_price_impl(self, ticker):
        try:
            contract = self.get_stock_contract(ticker)
            self.ib.qualifyContracts(contract)
            ticker_obj = self.ib.reqMktData(contract, '', False, False)
            self.ib.sleep(2)
            data = {
                'ticker': ticker,
                'last': ticker_obj.last,
                'bid': ticker_obj.bid,
                'ask': ticker_obj.ask,
                'close': ticker_obj.close,
                'volume': ticker_obj.volume,
            }
            self.ib.cancelMktData(contract)
            return data
        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {e}")
            return None
    
    # ------------------------------------------------------------------
    # get_option_chain
    # ------------------------------------------------------------------
    def get_option_chain(self, ticker, expiry=None, strike=None):
        """Get options chain for a stock"""
        return _ib_run(self._get_option_chain_impl, ticker, expiry, strike)

    def _get_option_chain_impl(self, ticker, expiry=None, strike=None):
        try:
            stock_contract = self.get_stock_contract(ticker)
            self.ib.qualifyContracts(stock_contract)
            chains = self.ib.reqSecDefOptParams(
                stock_contract.symbol, '', stock_contract.secType, stock_contract.conId
            )
            if not chains:
                logger.warning(f"No options chain found for {ticker}")
                return []
            chain = chains[0]
            strikes = chain.strikes
            if strike:
                strikes = [s for s in strikes if abs(s - strike) < 5]
            expirations = chain.expirations
            if expiry:
                expirations = [exp for exp in expirations if exp == expiry]
            options = []
            for exp in expirations[:5]:
                for strike_price in strikes:
                    options.append(Option(ticker, exp, strike_price, 'P', 'SMART'))
            return self.ib.qualifyContracts(*options)
        except Exception as e:
            logger.error(f"Error fetching option chain for {ticker}: {e}")
            return []
    
    # ------------------------------------------------------------------
    # get_option_greeks
    # ------------------------------------------------------------------
    def get_option_greeks(self, option_contract):
        """Get Greeks for an option contract"""
        return _ib_run(self._get_option_greeks_impl, option_contract)

    def _get_option_greeks_impl(self, option_contract):
        try:
            ticker_obj = self.ib.reqMktData(option_contract, '', False, False)
            self.ib.sleep(2)
            greeks = {
                'delta': ticker_obj.modelGreeks.delta if ticker_obj.modelGreeks else None,
                'gamma': ticker_obj.modelGreeks.gamma if ticker_obj.modelGreeks else None,
                'theta': ticker_obj.modelGreeks.theta if ticker_obj.modelGreeks else None,
                'vega': ticker_obj.modelGreeks.vega if ticker_obj.modelGreeks else None,
                'iv': ticker_obj.modelGreeks.impliedVol if ticker_obj.modelGreeks else None,
            }
            self.ib.cancelMktData(option_contract)
            return greeks
        except Exception as e:
            logger.error(f"Error fetching Greeks: {e}")
            return None
    
    # ------------------------------------------------------------------
    # get_account_summary
    # ------------------------------------------------------------------
    def get_account_summary(self):
        """Get account summary"""
        return _ib_run(self._get_account_summary_impl)

    def _get_account_summary_impl(self):
        try:
            account_values = self.ib.accountSummary()
            summary = {}
            for item in account_values:
                summary[item.tag] = item.value
            return summary
        except Exception as e:
            logger.error(f"Error fetching account summary: {e}")
            return {}
    
    # ------------------------------------------------------------------
    # get_portfolio_positions
    # ------------------------------------------------------------------
    def get_portfolio_positions(self):
        """Get all portfolio positions (stocks and options)"""
        return _ib_run(self._get_portfolio_positions_impl)

    def _get_portfolio_positions_impl(self):
        try:
            positions = self.ib.positions()
            
            stock_positions = []
            option_positions = []
            
            for pos in positions:
                contract = pos.contract
                
                # Calculate market value manually if needed
                market_value = getattr(pos, 'marketValue', pos.avgCost * pos.position if hasattr(pos, 'avgCost') and hasattr(pos, 'position') else 0)
                
                position_data = {
                    'symbol': contract.symbol,
                    'position': pos.position,  # Quantity (negative = short)
                    'avg_cost': getattr(pos, 'avgCost', 0),
                    'market_value': market_value,
                    'unrealized_pnl': getattr(pos, 'unrealizedPNL', 0),
                    'realized_pnl': getattr(pos, 'realizedPNL', 0),
                    'account': pos.account,
                }
                
                if contract.secType == 'STK':
                    position_data.update({
                        'type': 'STOCK',
                        'exchange': contract.exchange,
                        'currency': contract.currency,
                    })
                    stock_positions.append(position_data)
                    
                elif contract.secType == 'OPT':
                    position_data.update({
                        'type': 'OPTION',
                        'strike': contract.strike,
                        'expiry': contract.lastTradeDateOrContractMonth,
                        'right': contract.right,  # 'P' or 'C'
                        'exchange': contract.exchange,
                        'multiplier': getattr(contract, 'multiplier', 100),
                    })
                    option_positions.append(position_data)
            
            logger.info(f"✅ Fetched {len(stock_positions)} stock positions and {len(option_positions)} option positions")
            return {
                'stocks': stock_positions,
                'options': option_positions
            }
            
        except Exception as e:
            logger.error(f"Error fetching portfolio positions: {e}")
            logger.exception("Full traceback:")
            return {'stocks': [], 'options': []}
    
    # ------------------------------------------------------------------
    # get_open_orders
    # ------------------------------------------------------------------
    def get_open_orders(self):
        """Get all open orders"""
        return _ib_run(self._get_open_orders_impl)

    def _get_open_orders_impl(self):
        try:
            trades = self.ib.openTrades()
            orders = []
            
            for trade in trades:
                order_data = {
                    'symbol': trade.contract.symbol,
                    'order_id': trade.order.orderId,
                    'action': trade.order.action,  # BUY or SELL
                    'quantity': trade.order.totalQuantity,
                    'order_type': trade.order.orderType,  # LMT, MKT, etc.
                    'limit_price': trade.order.lmtPrice,
                    'status': trade.orderStatus.status,
                    'filled': trade.orderStatus.filled,
                    'remaining': trade.orderStatus.remaining,
                }
                
                if trade.contract.secType == 'OPT':
                    order_data.update({
                        'type': 'OPTION',
                        'strike': trade.contract.strike,
                        'expiry': trade.contract.lastTradeDateOrContractMonth,
                        'right': trade.contract.right,
                    })
                else:
                    order_data['type'] = 'STOCK'
                
                orders.append(order_data)
            
            logger.info(f"✅ Fetched {len(orders)} open orders")
            return orders
            
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []
    
    # ------------------------------------------------------------------
    # sell_option
    # ------------------------------------------------------------------
    def sell_option(self, ticker, expiry, strike, right, quantity=1, order_type='LMT', limit_price=None):
        """Sell (write) an option contract – core of the wheel strategy."""
        return _ib_run(self._sell_option_impl, ticker, expiry, strike, right, quantity, order_type, limit_price)

    def _sell_option_impl(self, ticker, expiry, strike, right, quantity=1, order_type='LMT', limit_price=None):
        try:
            contract = Option(ticker, expiry, strike, right, 'SMART')
            qualified = self.ib.qualifyContracts(contract)
            if not qualified:
                return {'success': False, 'error': f'Could not qualify option contract {ticker} {expiry} {strike} {right}'}
            contract = qualified[0]
            if order_type == 'MKT':
                order = MarketOrder('SELL', quantity)
            else:
                if limit_price is None:
                    return {'success': False, 'error': 'Limit price required for limit orders'}
                order = LimitOrder('SELL', quantity, limit_price)
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)
            logger.info(f"✅ Placed SELL order: {ticker} {expiry} ${strike} {right} x{quantity} @ {order_type} {limit_price or 'MKT'}")
            return {
                'success': True,
                'order_id': trade.order.orderId,
                'status': trade.orderStatus.status,
                'action': 'SELL',
                'symbol': ticker,
                'strike': strike,
                'expiry': expiry,
                'right': right,
                'quantity': quantity,
                'order_type': order_type,
                'limit_price': limit_price,
            }
        except Exception as e:
            logger.error(f"❌ Error placing sell order: {e}")
            return {'success': False, 'error': str(e)}
    
    # ------------------------------------------------------------------
    # buy_option
    # ------------------------------------------------------------------
    def buy_option(self, ticker, expiry, strike, right, quantity=1, order_type='LMT', limit_price=None):
        """Buy an option contract (to close a short position)."""
        return _ib_run(self._buy_option_impl, ticker, expiry, strike, right, quantity, order_type, limit_price)

    def _buy_option_impl(self, ticker, expiry, strike, right, quantity=1, order_type='LMT', limit_price=None):
        try:
            contract = Option(ticker, expiry, strike, right, 'SMART')
            qualified = self.ib.qualifyContracts(contract)
            if not qualified:
                return {'success': False, 'error': 'Could not qualify option contract'}
            contract = qualified[0]
            if order_type == 'MKT':
                order = MarketOrder('BUY', quantity)
            else:
                if limit_price is None:
                    return {'success': False, 'error': 'Limit price required for limit orders'}
                order = LimitOrder('BUY', quantity, limit_price)
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)
            logger.info(f"✅ Placed BUY order: {ticker} {expiry} ${strike} {right} x{quantity} @ {order_type} {limit_price or 'MKT'}")
            return {
                'success': True,
                'order_id': trade.order.orderId,
                'status': trade.orderStatus.status,
                'action': 'BUY',
                'symbol': ticker,
                'strike': strike,
                'expiry': expiry,
                'right': right,
                'quantity': quantity,
                'order_type': order_type,
                'limit_price': limit_price,
            }
        except Exception as e:
            logger.error(f"❌ Error placing buy order: {e}")
            return {'success': False, 'error': str(e)}
    
    # ------------------------------------------------------------------
    # buy_stock
    # ------------------------------------------------------------------
    def buy_stock(self, ticker, quantity, order_type='LMT', limit_price=None):
        """Buy stock shares."""
        return _ib_run(self._buy_stock_impl, ticker, quantity, order_type, limit_price)

    def _buy_stock_impl(self, ticker, quantity, order_type='LMT', limit_price=None):
        try:
            contract = self.get_stock_contract(ticker)
            self.ib.qualifyContracts(contract)
            if order_type == 'MKT':
                order = MarketOrder('BUY', quantity)
            else:
                if limit_price is None:
                    return {'success': False, 'error': 'Limit price required for limit orders'}
                order = LimitOrder('BUY', quantity, limit_price)
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)
            logger.info(f"✅ Placed BUY STOCK order: {ticker} x{quantity} @ {order_type} {limit_price or 'MKT'}")
            return {
                'success': True,
                'order_id': trade.order.orderId,
                'status': trade.orderStatus.status,
                'action': 'BUY',
                'symbol': ticker,
                'quantity': quantity,
                'order_type': order_type,
                'limit_price': limit_price,
                'sec_type': 'STK',
            }
        except Exception as e:
            logger.error(f"❌ Error placing stock buy order: {e}")
            return {'success': False, 'error': str(e)}
    
    # ------------------------------------------------------------------
    # sell_stock
    # ------------------------------------------------------------------
    def sell_stock(self, ticker, quantity, order_type='LMT', limit_price=None):
        """Sell stock shares."""
        return _ib_run(self._sell_stock_impl, ticker, quantity, order_type, limit_price)

    def _sell_stock_impl(self, ticker, quantity, order_type='LMT', limit_price=None):
        try:
            contract = self.get_stock_contract(ticker)
            self.ib.qualifyContracts(contract)
            if order_type == 'MKT':
                order = MarketOrder('SELL', quantity)
            else:
                if limit_price is None:
                    return {'success': False, 'error': 'Limit price required for limit orders'}
                order = LimitOrder('SELL', quantity, limit_price)
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)
            logger.info(f"✅ Placed SELL STOCK order: {ticker} x{quantity} @ {order_type} {limit_price or 'MKT'}")
            return {
                'success': True,
                'order_id': trade.order.orderId,
                'status': trade.orderStatus.status,
                'action': 'SELL',
                'symbol': ticker,
                'quantity': quantity,
                'order_type': order_type,
                'limit_price': limit_price,
                'sec_type': 'STK',
            }
        except Exception as e:
            logger.error(f"❌ Error placing stock sell order: {e}")
            return {'success': False, 'error': str(e)}
    
    # ------------------------------------------------------------------
    # cancel_order
    # ------------------------------------------------------------------
    def cancel_order(self, order_id):
        """Cancel an open order."""
        return _ib_run(self._cancel_order_impl, order_id)

    def _cancel_order_impl(self, order_id):
        try:
            trades = self.ib.openTrades()
            for trade in trades:
                if trade.order.orderId == order_id:
                    self.ib.cancelOrder(trade.order)
                    self.ib.sleep(1)
                    logger.info(f"✅ Cancelled order {order_id}")
                    return {'success': True, 'order_id': order_id, 'message': 'Order cancelled'}
            return {'success': False, 'error': f'Order {order_id} not found in open orders'}
        except Exception as e:
            logger.error(f"❌ Error cancelling order {order_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    # ------------------------------------------------------------------
    # get_option_quote
    # ------------------------------------------------------------------
    def get_option_quote(self, ticker, expiry, strike, right):
        """Get a live or delayed quote for a specific option contract."""
        return _ib_run(self._get_option_quote_impl, ticker, expiry, strike, right, timeout=40)

    def _get_option_quote_impl(self, ticker, expiry, strike, right):
        import math

        def _is_valid(val):
            if val is None:
                return False
            try:
                if math.isnan(val) or math.isinf(val):
                    return False
            except (TypeError, ValueError):
                return False
            return val > 0

        try:
            self.ib.reqMarketDataType(3)
            contract = Option(ticker, expiry, strike, right, 'SMART')
            qualified = self.ib.qualifyContracts(contract)
            if not qualified:
                logger.warning(f"Could not qualify contract: {ticker} {expiry} {strike} {right}")
                return None
            contract = qualified[0]
            logger.info(f"📊 Requesting quote for {contract.localSymbol} (conId={contract.conId})")
            ticker_obj = self.ib.reqMktData(contract, '', False, False)
            for i in range(10):
                self.ib.sleep(0.5)
                if i in (2, 5, 9):
                    logger.info(f"  Poll {i}: bid={ticker_obj.bid} ask={ticker_obj.ask} last={ticker_obj.last}")
                if _is_valid(ticker_obj.bid) or _is_valid(ticker_obj.ask) or _is_valid(ticker_obj.last) or _is_valid(ticker_obj.close):
                    break
            bid   = ticker_obj.bid   if _is_valid(ticker_obj.bid)   else None
            ask   = ticker_obj.ask   if _is_valid(ticker_obj.ask)   else None
            last  = ticker_obj.last  if _is_valid(ticker_obj.last)  else None
            close = ticker_obj.close if _is_valid(ticker_obj.close) else None
            mid   = round((bid + ask) / 2, 2) if bid and ask else None
            if last is None and close is not None:
                last = close
            volume = ticker_obj.volume if _is_valid(ticker_obj.volume) else 0
            data = {'bid': bid, 'ask': ask, 'last': last, 'mid': mid, 'volume': volume}
            logger.info(f"✅ Option quote for {ticker} {expiry} {strike}{right}: {data}")
            self.ib.cancelMktData(contract)
            return data
        except Exception as e:
            logger.error(f"❌ Error fetching option quote for {ticker} {expiry} {strike} {right}: {e}")
            return None

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

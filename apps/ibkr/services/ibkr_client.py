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

# Per-process singleton to maintain connection across requests
# Each gunicorn worker is a separate process with its own globals
_ib_instance = None
_connection_lock = threading.Lock()
_last_connect_attempt = 0
_RECONNECT_COOLDOWN = 3  # seconds between reconnect attempts


class IBKRClient:
    """Interactive Brokers API client wrapper"""
    
    def __init__(self, client_id=None):
        global _ib_instance
        with _connection_lock:
            if _ib_instance is None:
                _ib_instance = IB()
        self.ib = _ib_instance
        self.host = settings.IBKR_HOST
        self.port = settings.IBKR_PORT
        # Use process-unique client ID to avoid conflicts across gunicorn workers
        pid = os.getpid()
        self.client_id = client_id or (settings.IBKR_CLIENT_ID + (pid % 32))
        self.connected = False
    
    def _ensure_event_loop(self):
        """Ensure a working event loop exists for the current thread."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("closed loop")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    
    def connect(self):
        """Connect to TWS/Gateway with auto-reconnect logic"""
        global _last_connect_attempt
        
        with _connection_lock:
            try:
                # If already connected and connection is alive, reuse it
                if self.ib.isConnected():
                    self.connected = True
                    return True
                
                # Cooldown to prevent hammering the gateway
                now = time.time()
                if now - _last_connect_attempt < _RECONNECT_COOLDOWN:
                    logger.debug("Skipping reconnect (cooldown)")
                    return False
                _last_connect_attempt = now
                
                # Disconnect stale connection before reconnecting
                try:
                    self.ib.disconnect()
                except Exception:
                    pass
                
                # Reset the IB instance for a clean reconnect
                global _ib_instance
                _ib_instance = IB()
                self.ib = _ib_instance
                
                loop = self._ensure_event_loop()
                
                logger.info(f"🔄 Connecting to IBKR at {self.host}:{self.port} (clientId={self.client_id}, pid={os.getpid()})")
                
                loop.run_until_complete(
                    self.ib.connectAsync(self.host, self.port, clientId=self.client_id, timeout=10, readonly=False)
                )
                
                self.connected = True
                # Request delayed market data (type 3) as fallback
                # This works without paid real-time subscriptions
                self.ib.reqMarketDataType(3)
                logger.info(f"✅ Connected to IBKR at {self.host}:{self.port} (delayed data enabled)")
                return True
                
            except Exception as e:
                logger.warning(f"❌ Failed to connect to IBKR: {e}")
                self.connected = False
                return False
    
    def disconnect(self):
        """Disconnect from TWS/Gateway"""
        if self.connected:
            try:
                self.ib.disconnect()
            except Exception:
                pass
            self.connected = False
            logger.info("Disconnected from IBKR")
    
    def is_connected(self):
        """Check if connected to IBKR"""
        try:
            return self.ib.isConnected()
        except Exception:
            return False
    
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
    
    def get_stock_price(self, ticker):
        """
        Get current stock price
        
        Args:
            ticker: Stock symbol
        
        Returns:
            dict with price data or None if failed
        """
        try:
            contract = self.get_stock_contract(ticker)
            self.ib.qualifyContracts(contract)
            ticker_obj = self.ib.reqMktData(contract, '', False, False)
            self.ib.sleep(2)  # Wait for data
            
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
    
    def get_option_chain(self, ticker, expiry=None, strike=None):
        """
        Get options chain for a stock
        
        Args:
            ticker: Stock symbol
            expiry: Optional expiry date filter (YYYYMMDD)
            strike: Optional strike price filter
        
        Returns:
            list of option contracts
        """
        try:
            stock_contract = self.get_stock_contract(ticker)
            self.ib.qualifyContracts(stock_contract)
            
            # Get option chain details
            chains = self.ib.reqSecDefOptParams(
                stock_contract.symbol,
                '',
                stock_contract.secType,
                stock_contract.conId
            )
            
            if not chains:
                logger.warning(f"No options chain found for {ticker}")
                return []
            
            chain = chains[0]
            
            # Filter strikes if needed
            strikes = chain.strikes
            if strike:
                strikes = [s for s in strikes if abs(s - strike) < 5]
            
            # Filter expirations if needed
            expirations = chain.expirations
            if expiry:
                expirations = [exp for exp in expirations if exp == expiry]
            
            # Create option contracts
            options = []
            for exp in expirations[:5]:  # Limit to next 5 expirations
                for strike_price in strikes:
                    # Put option
                    put = Option(ticker, exp, strike_price, 'P', 'SMART')
                    options.append(put)
            
            # Qualify contracts
            qualified = self.ib.qualifyContracts(*options)
            return qualified
            
        except Exception as e:
            logger.error(f"Error fetching option chain for {ticker}: {e}")
            return []
    
    def get_option_greeks(self, option_contract):
        """
        Get Greeks for an option contract
        
        Args:
            option_contract: Option contract object
        
        Returns:
            dict with Greeks data
        """
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
    
    def get_account_summary(self):
        """Get account summary"""
        try:
            account_values = self.ib.accountSummary()
            summary = {}
            for item in account_values:
                summary[item.tag] = item.value
            return summary
        except Exception as e:
            logger.error(f"Error fetching account summary: {e}")
            return {}
    
    def get_portfolio_positions(self):
        """
        Get all portfolio positions (stocks and options)
        
        Returns:
            dict with 'stocks' and 'options' lists
        """
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
    
    def get_open_orders(self):
        """
        Get all open orders
        
        Returns:
            list of open orders
        """
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
    
    def sell_option(self, ticker, expiry, strike, right, quantity=1, order_type='LMT', limit_price=None):
        """
        Sell (write) an option contract - core of the wheel strategy.
        
        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            expiry: Expiration date string (YYYYMMDD)
            strike: Strike price
            right: 'P' for put, 'C' for call
            quantity: Number of contracts to sell
            order_type: 'LMT' for limit or 'MKT' for market
            limit_price: Limit price per share (required for LMT orders)
        
        Returns:
            dict with order details or error
        """
        try:
            # Create and qualify the option contract
            contract = Option(ticker, expiry, strike, right, 'SMART')
            qualified = self.ib.qualifyContracts(contract)
            if not qualified:
                return {'success': False, 'error': f'Could not qualify option contract {ticker} {expiry} {strike} {right}'}
            
            contract = qualified[0]
            
            # Create the order (SELL = write the option)
            if order_type == 'MKT':
                order = MarketOrder('SELL', quantity)
            else:
                if limit_price is None:
                    return {'success': False, 'error': 'Limit price required for limit orders'}
                order = LimitOrder('SELL', quantity, limit_price)
            
            # Place the order
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)  # Wait for order acknowledgement
            
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
    
    def buy_option(self, ticker, expiry, strike, right, quantity=1, order_type='LMT', limit_price=None):
        """
        Buy an option contract (to close a short position).
        
        Args:
            ticker: Stock symbol
            expiry: Expiration date string (YYYYMMDD)
            strike: Strike price
            right: 'P' for put, 'C' for call
            quantity: Number of contracts
            order_type: 'LMT' or 'MKT'
            limit_price: Limit price per share (required for LMT)
        
        Returns:
            dict with order details or error
        """
        try:
            contract = Option(ticker, expiry, strike, right, 'SMART')
            qualified = self.ib.qualifyContracts(contract)
            if not qualified:
                return {'success': False, 'error': f'Could not qualify option contract'}
            
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
    
    def buy_stock(self, ticker, quantity, order_type='LMT', limit_price=None):
        """
        Buy stock shares (e.g., after assignment or to start covered calls).
        
        Args:
            ticker: Stock symbol
            quantity: Number of shares
            order_type: 'LMT' or 'MKT'
            limit_price: Limit price per share
        
        Returns:
            dict with order details or error
        """
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
    
    def sell_stock(self, ticker, quantity, order_type='LMT', limit_price=None):
        """
        Sell stock shares.
        
        Args:
            ticker: Stock symbol
            quantity: Number of shares
            order_type: 'LMT' or 'MKT'
            limit_price: Limit price per share
        
        Returns:
            dict with order details or error
        """
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
    
    def cancel_order(self, order_id):
        """
        Cancel an open order.
        
        Args:
            order_id: The order ID to cancel
        
        Returns:
            dict with cancellation result
        """
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
    
    def get_option_quote(self, ticker, expiry, strike, right):
        """
        Get a live or delayed quote for a specific option contract.
        Uses reqMarketDataType(3) for delayed data (free, no subscription needed).
        In ib_insync, delayed data populates the same bid/ask/last fields.
        
        Args:
            ticker: Stock symbol
            expiry: Expiration date (YYYYMMDD)
            strike: Strike price
            right: 'P' or 'C'
        
        Returns:
            dict with bid/ask/last/mid or None
        """
        import math
        
        def _is_valid(val):
            """Check if a price value is valid (not None, not NaN, not -1, > 0)."""
            if val is None:
                return False
            try:
                if math.isnan(val) or math.isinf(val):
                    return False
            except (TypeError, ValueError):
                return False
            return val > 0
        
        try:
            # Request delayed market data (type 3) - free, no subscription needed
            # Must be called BEFORE reqMktData. Delayed data fills same bid/ask/last fields.
            self.ib.reqMarketDataType(3)
            
            contract = Option(ticker, expiry, strike, right, 'SMART')
            qualified = self.ib.qualifyContracts(contract)
            if not qualified:
                logger.warning(f"Could not qualify contract: {ticker} {expiry} {strike} {right}")
                return None
            
            contract = qualified[0]
            logger.info(f"📊 Requesting quote for {contract.localSymbol} (conId={contract.conId})")
            
            ticker_obj = self.ib.reqMktData(contract, '', False, False)
            
            # Wait for data to arrive - poll up to ~5 seconds
            for i in range(10):
                self.ib.sleep(0.5)
                # Log raw values for debugging
                if i == 2 or i == 5 or i == 9:
                    logger.info(f"  Poll {i}: bid={ticker_obj.bid} ask={ticker_obj.ask} last={ticker_obj.last} close={ticker_obj.close} modelGreeks={ticker_obj.modelGreeks}")
                # Check if any useful data arrived
                if _is_valid(ticker_obj.bid) or _is_valid(ticker_obj.ask) or _is_valid(ticker_obj.last) or _is_valid(ticker_obj.close):
                    break
            
            bid = ticker_obj.bid if _is_valid(ticker_obj.bid) else None
            ask = ticker_obj.ask if _is_valid(ticker_obj.ask) else None
            last = ticker_obj.last if _is_valid(ticker_obj.last) else None
            close = ticker_obj.close if _is_valid(ticker_obj.close) else None
            
            mid = round((bid + ask) / 2, 2) if bid and ask else None
            
            # Use close price as fallback for last
            if last is None and close is not None:
                last = close
            
            volume = ticker_obj.volume if _is_valid(ticker_obj.volume) else 0
            
            data = {
                'bid': bid,
                'ask': ask,
                'last': last,
                'mid': mid,
                'volume': volume,
            }
            
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

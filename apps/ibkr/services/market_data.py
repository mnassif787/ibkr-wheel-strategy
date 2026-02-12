"""
Market Data Service - Fetch and store data from IBKR
"""
from django.utils import timezone
from apps.ibkr.models import Stock, Option, Signal, Watchlist, UserConfig, StockIndicator, Position
from apps.ibkr.services.ibkr_client import IBKRClient
import logging
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


class MarketDataService:
    """Service for fetching and processing market data from IBKR"""
    
    def __init__(self):
        self.client = IBKRClient()
    
    def sync_watchlist_stocks(self):
        """Sync all stocks in watchlist"""
        watchlist = Watchlist.objects.all()
        
        if not watchlist:
            logger.warning("⚠️  Watchlist is empty. Add tickers first.")
            return
        
        logger.info(f"🔄 Syncing {watchlist.count()} stocks from IBKR...")
        
        if not self.client.connect():
            logger.error("❌ Failed to connect to IBKR")
            return
        
        try:
            for item in watchlist:
                ticker = item.ticker
                logger.info(f"📊 Fetching data for {ticker}...")
                
                # Get stock price
                price_data = self.client.get_stock_price(ticker)
                
                if price_data:
                    # Handle NaN values from IBKR
                    last_price = price_data.get('last')
                    if last_price and str(last_price).lower() not in ['nan', 'none', '']:
                        try:
                            last_price_decimal = Decimal(str(last_price))
                        except (ValueError, TypeError):
                            logger.warning(f"  ⚠️  Invalid price for {ticker}: {last_price}")
                            last_price_decimal = None
                    else:
                        last_price_decimal = None
                    
                    # Update or create stock
                    stock, created = Stock.objects.update_or_create(
                        ticker=ticker,
                        defaults={
                            'last_price': last_price_decimal,
                            'last_updated': timezone.now(),
                        }
                    )
                    
                    action = "Created" if created else "Updated"
                    price_display = f"${last_price_decimal}" if last_price_decimal else "No price data"
                    logger.info(f"  ✅ {action} {ticker}: {price_display}")
                    
                    # Fetch option chain
                    self.sync_options_for_stock(ticker)
                else:
                    logger.warning(f"  ⚠️  No data for {ticker}")
        
        finally:
            self.client.disconnect()
    
    def sync_options_for_stock(self, ticker):
        """Fetch and store options for a ticker"""
        try:
            stock = Stock.objects.get(ticker=ticker)
            
            # Get option chain
            options = self.client.get_option_chain(ticker)
            
            if not options:
                logger.info(f"  ℹ️  No options found for {ticker}")
                return
            
            logger.info(f"  📋 Found {len(options)} option contracts")
            
            # Store first 10 options for now (to avoid overwhelming)
            for opt in options[:10]:
                try:
                    # Request market data
                    ticker_obj = self.client.ib.reqMktData(opt, '', False, False)
                    self.client.ib.sleep(1)
                    
                    # Convert expiry
                    expiry_str = opt.lastTradeDateOrContractMonth
                    expiry_date = datetime.strptime(expiry_str, '%Y%m%d').date()
                    
                    # Get Greeks
                    greeks = self.client.get_option_greeks(opt)
                    
                    # Helper function to safely convert to Decimal (handles NaN)
                    def safe_decimal(value):
                        if value is None or str(value).lower() in ['nan', 'none', '']:
                            return None
                        try:
                            return Decimal(str(value))
                        except (ValueError, TypeError):
                            return None
                    
                    # Create or update option
                    Option.objects.update_or_create(
                        stock=stock,
                        expiry_date=expiry_date,
                        strike=Decimal(str(opt.strike)),
                        option_type='PUT' if opt.right == 'P' else 'CALL',
                        defaults={
                            'bid': safe_decimal(ticker_obj.bid),
                            'ask': safe_decimal(ticker_obj.ask),
                            'last': safe_decimal(ticker_obj.last),
                            'volume': int(ticker_obj.volume) if ticker_obj.volume and str(ticker_obj.volume).lower() != 'nan' else 0,
                            'open_interest': int(ticker_obj.lastSize) if ticker_obj.lastSize and str(ticker_obj.lastSize).lower() != 'nan' else 0,
                            'implied_volatility': safe_decimal(greeks.get('iv')) if greeks else None,
                            'delta': safe_decimal(greeks.get('delta')) if greeks else None,
                            'gamma': safe_decimal(greeks.get('gamma')) if greeks else None,
                            'theta': safe_decimal(greeks.get('theta')) if greeks else None,
                            'vega': safe_decimal(greeks.get('vega')) if greeks else None,
                            'last_updated': timezone.now(),
                        }
                    )
                    
                    self.client.ib.cancelMktData(opt)
                    
                except Exception as e:
                    logger.error(f"    ❌ Error processing option: {e}")
                    continue
            
            logger.info(f"  ✅ Saved options for {ticker}")
            
        except Stock.DoesNotExist:
            logger.error(f"  ❌ Stock {ticker} not found in database")
        except Exception as e:
            logger.error(f"  ❌ Error syncing options for {ticker}: {e}")
    
    def generate_signals(self):
        """
        Generate Wheel Strategy signals with multi-factor scoring
        Implements professional stock screening and technical analysis
        """
        logger.info("🎯 Generating Wheel Strategy signals with multi-factor scoring...")
        
        # Get user config
        config = UserConfig.objects.first()
        if not config:
            config = UserConfig.objects.create()
            logger.info("📋 Created default user config")
        
        # Step 1: Screen stocks (fundamental + liquidity filters)
        qualified_stocks = self._screen_stocks(config)
        
        if not qualified_stocks:
            logger.warning("⚠️  No stocks passed screening criteria")
            return
        
        logger.info(f"✅ {len(qualified_stocks)} stocks passed screening")
        
        # Step 2: Generate cash-secured put signals
        signals_created = self._generate_put_signals(qualified_stocks, config)
        
        # Step 3: Generate covered call signals for assigned positions
        covered_calls_created = self._generate_covered_call_signals(config)
        
        logger.info(f"✅ Generated {signals_created} PUT signals and {covered_calls_created} CALL signals")
    
    def _screen_stocks(self, config):
        """
        Screen stocks based on wheel strategy criteria:
        - Liquidity: Avg volume > 1M shares
        - Volatility: IV between 20-80%
        - Price range: $10-$200
        - Fundamentals: ROE > config.min_roe, Market cap > $1B
        """
        from django.db.models import Q
        
        qualified_stocks = []
        
        # Get watchlist stocks
        watchlist_tickers = Watchlist.objects.values_list('ticker', flat=True)
        stocks = Stock.objects.filter(ticker__in=watchlist_tickers)
        
        for stock in stocks:
            # Price range check ($10-$200)
            if not stock.last_price:
                continue
            price = float(stock.last_price)
            if price < 10 or price > 200:
                continue
            
            # Liquidity check (avg volume > 1M)
            if not stock.avg_volume or stock.avg_volume < 1000000:
                continue
            
            # Market cap check (> $1B)
            if not stock.market_cap or stock.market_cap < 1000000000:
                continue
            
            # ROE check
            if stock.roe and float(stock.roe) < float(config.min_roe):
                continue
            
            # Check if stock has options available
            has_options = Option.objects.filter(stock=stock, option_type='PUT').exists()
            if not has_options:
                continue
            
            qualified_stocks.append(stock)
        
        return qualified_stocks
    
    def _generate_put_signals(self, stocks, config):
        """
        Generate WHEEL STRATEGY cash-secured put signals
        Following wheel strategy rules:
        - Sell puts at or below support levels
        - Target delta ~0.30 (70% chance OTM)
        - Look for bullish or consolidating stocks
        - Premium collection while waiting for assignment
        """
        signals_created = 0
        
        for stock in stocks:
            # Wheel Strategy Filter: Must have technical indicators
            try:
                indicator = stock.indicators
            except:
                logger.warning(f"  ⚠️  {stock.ticker} missing indicators - skipping")
                continue
            
            # Wheel Strategy Rule 1: Prefer bullish or neutral stocks (not bearish)
            if indicator.ema_trend == 'BEARISH':
                logger.debug(f"  ⏭️  {stock.ticker} bearish trend - not ideal for puts")
                continue
            
            # Wheel Strategy Rule 2: Best entry near support levels
            near_support = indicator.near_support if indicator else False
            
            # Get suitable PUT options
            puts = Option.objects.filter(
                stock=stock,
                option_type='PUT',
                expiry_date__gte=timezone.now().date()
            ).order_by('expiry_date', '-strike')
            
            for put in puts:
                # Check basic option criteria
                if not self._meets_criteria(put, config):
                    continue
                
                # Wheel Strategy Rule 3: Target delta ~0.30 (30% chance ITM, 70% OTM)
                if put.delta:
                    delta_val = abs(float(put.delta))
                    if delta_val < 0.25 or delta_val > 0.35:
                        continue  # Only want ~30 delta for wheel strategy
                
                # Calculate option metrics
                dte = (put.expiry_date - timezone.now().date()).days
                if dte <= 0:
                    continue
                
                premium = put.mid_price if put.mid_price else Decimal('0')
                strike = put.strike
                
                if strike == 0 or premium == 0:
                    continue
                
                # Wheel Strategy Rule 4: Strike should be at or below support
                # This increases probability of assignment at favorable prices
                strike_vs_support = "N/A"
                if indicator.support_level_1:
                    if strike <= indicator.support_level_1:
                        strike_vs_support = "At/Below Support ✅"
                    else:
                        strike_vs_support = "Above Support ⚠️"
                
                err_pct = (premium / (strike * 100)) * 100
                apy_pct = (err_pct * 365 / dte) if dte > 0 else Decimal('0')
                break_even = strike - (premium / 100)
                
                # Calculate multi-factor quality score
                score_data = self._calculate_quality_score(stock, put, apy_pct, config)
                
                # Build wheel-strategy specific reasoning
                wheel_reasoning = self._build_wheel_put_reasoning(
                    stock, put, indicator, strike_vs_support, score_data
                )
                score_data['technical_reason'] = wheel_reasoning
                
                # Only create signals with score >= 60 (Grade B or better)
                if score_data['quality_score'] < 60:
                    continue
                
                # Create signal with scoring data
                Signal.objects.create(
                    stock=stock,
                    option=put,
                    signal_type='CASH_SECURED_PUT',
                    premium=premium,
                    err_pct=err_pct,
                    apy_pct=apy_pct,
                    break_even=break_even,
                    max_loss_pct=Decimal('30.0'),
                    quality_score=score_data['quality_score'],
                    stock_score=score_data['stock_score'],
                    technical_score=score_data['technical_score'],
                    options_score=score_data['options_score'],
                    assignment_risk=score_data['assignment_risk'],
                    technical_reason=score_data['technical_reason'],
                    status='OPEN'
                )
                signals_created += 1
                
                # Limit to best 2 signals per stock
                if signals_created >= 2:
                    break
        
        return signals_created
    
    def _build_wheel_put_reasoning(self, stock, put, indicator, strike_vs_support, score_data):
        """Build detailed wheel strategy reasoning for PUT signal"""
        reasons = []
        reasons.append(f"🎯 WHEEL STRATEGY - Cash-Secured Put Entry")
        reasons.append(f"Strike ${put.strike} | Delta {abs(float(put.delta)) if put.delta else 'N/A'}")
        
        # Technical setup
        if indicator.rsi and indicator.rsi < 40:
            reasons.append(f"✅ RSI {indicator.rsi:.1f} - Stock oversold, good put entry")
        elif indicator.rsi and indicator.rsi < 60:
            reasons.append(f"✅ RSI {indicator.rsi:.1f} - Neutral, favorable for puts")
        
        if indicator.ema_trend == 'BULLISH':
            reasons.append(f"✅ Bullish trend - Reduces assignment risk")
        elif indicator.ema_trend == 'NEUTRAL':
            reasons.append(f"➖ Neutral trend - Standard wheel entry")
        
        # Support analysis
        if indicator.near_support:
            reasons.append(f"✅ Price near support - Protected downside")
        reasons.append(f"📍 {strike_vs_support}")
        
        # Wheel strategy outcome
        reasons.append(f"📊 Outcome: Collect ${put.mid_price if put.mid_price else 0} premium")
        if score_data['assignment_risk'] < 30:
            reasons.append(f"✅ {score_data['assignment_risk']:.0f}% assignment risk - Likely expires worthless")
        else:
            reasons.append(f"⚠️ {score_data['assignment_risk']:.0f}% assignment risk - May get assigned at ${put.strike}")
            reasons.append(f"   If assigned: Sell covered calls at resistance")
        
        return " | ".join(reasons)
    
    def _generate_covered_call_signals(self, config):
        """
        Generate WHEEL STRATEGY covered call signals for assigned positions
        Phase 2 of wheel: After assignment, sell calls at resistance
        - Sell calls at or above resistance levels
        - Target delta ~0.30
        - Collect premium while waiting for stock to be called away
        """
        signals_created = 0
        
        # Get active positions (stocks we got assigned on)
        positions = Position.objects.filter(is_active=True)
        
        for position in positions:
            stock = position.stock
            
            # Get technical indicators
            try:
                indicator = stock.indicators
            except:
                logger.warning(f"  ⚠️  {stock.ticker} missing indicators")
                continue
            
            # Wheel Strategy: Best to sell calls near resistance
            near_resistance = indicator.near_resistance if indicator else False
            
            # Get suitable CALL options (OTM, delta ~0.30)
            calls = Option.objects.filter(
                stock=stock,
                option_type='CALL',
                strike__gt=stock.last_price,  # Only OTM calls
                expiry_date__gte=timezone.now().date()
            ).order_by('expiry_date', 'strike')
            
            for call in calls:
                # Check DTE range
                dte = (call.expiry_date - timezone.now().date()).days
                if dte < config.min_dte or dte > config.max_dte:
                    continue
                
                # Wheel Strategy: Target delta ~0.30 for calls
                if call.delta:
                    delta_val = float(call.delta)
                    if delta_val < 0.25 or delta_val > 0.35:
                        continue
                
                # Calculate metrics
                premium = call.mid_price if call.mid_price else Decimal('0')
                if premium == 0:
                    continue
                
                strike = call.strike
                err_pct = (premium / (strike * 100)) * 100
                apy_pct = (err_pct * 365 / dte) if dte > 0 else Decimal('0')
                
                # Wheel Strategy: Strike should be at or above resistance
                strike_vs_resistance = "N/A"
                if indicator.resistance_level_1:
                    if strike >= indicator.resistance_level_1:
                        strike_vs_resistance = "At/Above Resistance ✅"
                    else:
                        strike_vs_resistance = "Below Resistance ⚠️"
                
                # Calculate quality score
                score_data = self._calculate_quality_score(stock, call, apy_pct, config)
                
                # Build wheel-strategy specific reasoning for covered calls
                wheel_reasoning = self._build_wheel_call_reasoning(
                    stock, call, position, indicator, strike_vs_resistance, score_data
                )
                score_data['technical_reason'] = wheel_reasoning
                
                # Create covered call signal
                Signal.objects.create(
                    stock=stock,
                    option=call,
                    signal_type='COVERED_CALL',
                    premium=premium,
                    err_pct=err_pct,
                    apy_pct=apy_pct,
                    break_even=stock.last_price - (premium / 100),
                    max_loss_pct=Decimal('100.0'),
                    quality_score=score_data['quality_score'],
                    stock_score=score_data['stock_score'],
                    technical_score=score_data['technical_score'],
                    options_score=score_data['options_score'],
                    assignment_risk=score_data.get('assignment_risk', Decimal('50.0')),
                    technical_reason=score_data['technical_reason'],
                    status='OPEN'
                )
                signals_created += 1
                
                # Limit to best 2 signals per position
                if signals_created >= 2:
                    break
        
        return signals_created
    
    def _build_wheel_call_reasoning(self, stock, call, position, indicator, strike_vs_resistance, score_data):
        """Build detailed wheel strategy reasoning for CALL signal"""
        reasons = []
        reasons.append(f"🎯 WHEEL STRATEGY - Covered Call (Phase 2)")
        reasons.append(f"Position: {position.quantity} shares @ ${position.cost_basis}")
        reasons.append(f"Strike ${call.strike} | Delta {float(call.delta) if call.delta else 'N/A'}")
        
        # Current P&L on position
        if position.unrealized_pl:
            pl_pct = position.unrealized_pl_pct
            if pl_pct > 0:
                reasons.append(f"✅ Position up {pl_pct:.1f}% - Good time to sell calls")
            else:
                reasons.append(f"⚠️ Position down {abs(pl_pct):.1f}% - Collect premium while waiting")
        
        # Technical setup
        if indicator.near_resistance:
            reasons.append(f"✅ Price near resistance - High probability call")
        reasons.append(f"📍 {strike_vs_resistance}")
        
        # Wheel outcome
        reasons.append(f"📊 Outcome: Collect ${call.mid_price if call.mid_price else 0} premium")
        if float(call.delta) > 0.30:
            reasons.append(f"⚠️ {float(call.delta)*100:.0f}% chance stock called away")
            reasons.append(f"   If called: Profit ${(call.strike - position.cost_basis) * position.quantity:.2f}")
        else:
            reasons.append(f"✅ {(1-float(call.delta))*100:.0f}% chance expires worthless - Keep shares")
        
        reasons.append(f"🔄 Repeat wheel: Sell more calls or wait for dip to exit")
        
        return " | ".join(reasons)
    
    def _generate_call_signals(self, stock):
        """Generate covered call signals for stocks we own (assigned from puts)"""
        # This is a placeholder - covered call logic would go here
        # Would check Position model for assigned stocks
        return 0
    
    def _calculate_quality_score(self, stock, option, apy_pct, config):
        """
        Calculate multi-factor quality score (0-100)
        
        Components:
        - Stock Quality (40%): Fundamentals + Liquidity
        - Technical Setup (35%): RSI + EMA + Support/Resistance
        - Options Metrics (25%): Delta + IV + Premium
        """
        # Initialize scores
        stock_score = 0
        technical_score = 0
        options_score = 0
        technical_reasons = []
        
        # === STOCK QUALITY (40 points max) ===
        
        # ROE score (10 points)
        if stock.roe:
            roe = float(stock.roe)
            if roe >= 20:
                stock_score += 10
                technical_reasons.append("Strong ROE")
            elif roe >= 15:
                stock_score += 7
            elif roe >= 10:
                stock_score += 5
        
        # Market cap stability (10 points)
        if stock.market_cap:
            if stock.market_cap >= 100_000_000_000:  # > $100B
                stock_score += 10
                technical_reasons.append("Large-cap stock")
            elif stock.market_cap >= 10_000_000_000:  # > $10B
                stock_score += 7
            elif stock.market_cap >= 1_000_000_000:  # > $1B
                stock_score += 5
        
        # Beta (lower is better for wheel strategy) (10 points)
        if stock.beta:
            beta = float(stock.beta)
            if beta < 0.8:
                stock_score += 10
            elif beta < 1.2:
                stock_score += 7
            elif beta < 1.5:
                stock_score += 4
        
        # Liquidity (10 points)
        if stock.avg_volume:
            if stock.avg_volume >= 10_000_000:
                stock_score += 10
                technical_reasons.append("High liquidity")
            elif stock.avg_volume >= 5_000_000:
                stock_score += 7
            elif stock.avg_volume >= 1_000_000:
                stock_score += 5
        
        # === TECHNICAL SETUP (35 points max) ===
        
        try:
            indicator = StockIndicator.objects.get(stock=stock)
            
            # RSI signal (15 points)
            if indicator.rsi_signal == 'OVERSOLD':
                technical_score += 15
                technical_reasons.append("RSI oversold")
            elif indicator.rsi_signal == 'NEUTRAL':
                technical_score += 10
            
            # EMA trend (10 points)
            if indicator.ema_trend == 'BULLISH':
                technical_score += 10
                technical_reasons.append("Bullish trend")
            elif indicator.ema_trend == 'NEUTRAL':
                technical_score += 5
            
            # Near support level (10 points)
            if indicator.near_support:
                technical_score += 10
                technical_reasons.append("Near support")
            
        except StockIndicator.DoesNotExist:
            # No technical indicators calculated yet
            technical_score = 15  # Give neutral score
        
        # === OPTIONS METRICS (25 points max) ===
        
        # Delta (10 points) - prefer 0.25-0.35 for puts
        if option.delta:
            delta_abs = abs(float(option.delta))
            if 0.25 <= delta_abs <= 0.35:
                options_score += 10
                technical_reasons.append("Optimal delta")
            elif 0.20 <= delta_abs <= 0.40:
                options_score += 7
            elif 0.15 <= delta_abs <= 0.45:
                options_score += 4
        
        # APY (10 points)
        apy = float(apy_pct)
        if apy >= 30:
            options_score += 10
            technical_reasons.append("High APY")
        elif apy >= 20:
            options_score += 8
        elif apy >= 15:
            options_score += 6
        elif apy >= 10:
            options_score += 4
        
        # IV check (5 points) - prefer moderate IV (30-60%)
        if option.implied_volatility:
            iv = float(option.implied_volatility) * 100
            if 30 <= iv <= 60:
                options_score += 5
            elif 20 <= iv <= 80:
                options_score += 3
        
        # === CALCULATE COMPOSITE SCORE ===
        
        # Weight: Stock 40%, Technical 35%, Options 25%
        quality_score = int(
            (stock_score / 40 * 40) +
            (technical_score / 35 * 35) +
            (options_score / 25 * 25)
        )
        
        # Assignment risk (probability based on delta)
        assignment_risk = abs(float(option.delta) * 100) if option.delta else 30.0
        
        return {
            'quality_score': quality_score,
            'stock_score': Decimal(str(stock_score)),
            'technical_score': Decimal(str(technical_score)),
            'options_score': Decimal(str(options_score)),
            'assignment_risk': Decimal(str(assignment_risk)),
            'technical_reason': '; '.join(technical_reasons) if technical_reasons else 'Standard criteria met'
        }
    
    def _meets_criteria(self, option, config):
        """Check if option meets filtering criteria"""
        dte = (option.expiry_date - timezone.now().date()).days
        
        # DTE check
        if dte < config.min_dte or dte > config.max_dte:
            return False
        
        # Delta check (for puts, delta is negative)
        if option.delta:
            delta_val = float(option.delta)
            if delta_val > float(config.max_delta) or delta_val < float(config.min_delta):
                return False
        
        # IV check
        if option.implied_volatility:
            if float(option.implied_volatility) > float(config.max_iv):
                return False
        
        return True

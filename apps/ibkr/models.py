from django.db import models
from django.utils import timezone


class Stock(models.Model):
    """Stock information from IBKR"""
    ticker = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=200, blank=True)
    last_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    market_cap = models.BigIntegerField(null=True, blank=True)
    beta = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    roe = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    free_cash_flow = models.BigIntegerField(null=True, blank=True)
    sector = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    
    # Additional financial metrics
    pe_ratio = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text='Price to Earnings Ratio')
    forward_pe = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text='Forward P/E Ratio')
    dividend_yield = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True, help_text='Dividend Yield %')
    fifty_two_week_high = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fifty_two_week_low = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    avg_volume = models.BigIntegerField(null=True, blank=True, help_text='Average Volume')
    
    last_updated = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['ticker']
    
    def __str__(self):
        return f"{self.ticker} - {self.name}"


class Option(models.Model):
    """Options data from IBKR"""
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='options')
    expiry_date = models.DateField()
    strike = models.DecimalField(max_digits=10, decimal_places=2)
    option_type = models.CharField(max_length=4, choices=[('PUT', 'Put'), ('CALL', 'Call')])
    bid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ask = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    last = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    volume = models.IntegerField(default=0)
    open_interest = models.IntegerField(default=0)
    implied_volatility = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    delta = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    gamma = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    theta = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    vega = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    last_updated = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['stock', 'expiry_date', 'strike']
        unique_together = ['stock', 'expiry_date', 'strike', 'option_type']
    
    def __str__(self):
        return f"{self.stock.ticker} ${self.strike} {self.option_type} {self.expiry_date}"
    
    @property
    def dte(self):
        """Days to expiration"""
        return (self.expiry_date - timezone.now().date()).days
    
    @property
    def mid_price(self):
        """Mid price between bid and ask"""
        if self.bid and self.ask:
            return (self.bid + self.ask) / 2
        return self.last


class Signal(models.Model):
    """Wheel Strategy signals"""
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('FILLED', 'Filled'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
    ]
    
    SIGNAL_TYPE_CHOICES = [
        ('CASH_SECURED_PUT', 'Cash-Secured Put'),
        ('COVERED_CALL', 'Covered Call'),
    ]
    
    GRADE_CHOICES = [
        ('A', 'A - Excellent'),
        ('B', 'B - Good'),
        ('C', 'C - Fair'),
    ]
    
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='signals')
    option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name='signals')
    signal_type = models.CharField(max_length=20, choices=SIGNAL_TYPE_CHOICES, default='CASH_SECURED_PUT')
    premium = models.DecimalField(max_digits=10, decimal_places=2)
    err_pct = models.DecimalField(max_digits=5, decimal_places=4, help_text='Expected Rate of Return %')
    apy_pct = models.DecimalField(max_digits=5, decimal_places=2, help_text='Annualized Percentage Yield')
    break_even = models.DecimalField(max_digits=10, decimal_places=2)
    max_loss_pct = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Multi-factor scoring (NEW)
    quality_score = models.IntegerField(default=0, help_text='Composite score 0-100')
    grade = models.CharField(max_length=1, choices=GRADE_CHOICES, blank=True, help_text='A/B/C based on score')
    stock_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Stock quality score (40%)')
    technical_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Technical setup score (35%)')
    options_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Options metrics score (25%)')
    assignment_risk = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text='Probability of assignment %')
    technical_reason = models.TextField(blank=True, help_text='Why this signal was generated')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    generated_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-quality_score', '-generated_at']
    
    def __str__(self):
        return f"{self.stock.ticker} Signal - {self.signal_type} ({self.grade or self.status})"
    
    def save(self, *args, **kwargs):
        """Auto-assign grade based on quality_score"""
        if self.quality_score >= 80:
            self.grade = 'A'
        elif self.quality_score >= 60:
            self.grade = 'B'
        else:
            self.grade = 'C'
        super().save(*args, **kwargs)


class Watchlist(models.Model):
    """User watchlist for stocks to monitor"""
    ticker = models.CharField(max_length=10, unique=True)
    added_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['ticker']
    
    def __str__(self):
        return self.ticker


class UserConfig(models.Model):
    """User trading preferences and settings"""
    # Strategy parameters
    min_dte = models.IntegerField(default=7, help_text='Minimum days to expiration')
    max_dte = models.IntegerField(default=45, help_text='Maximum days to expiration')
    min_delta = models.DecimalField(max_digits=3, decimal_places=2, default=-0.38)
    max_delta = models.DecimalField(max_digits=3, decimal_places=2, default=-0.20)
    max_iv = models.DecimalField(max_digits=4, decimal_places=2, default=1.29, help_text='Max implied volatility')
    min_premium_pct = models.DecimalField(max_digits=4, decimal_places=2, default=1.0, help_text='Min premium %')
    min_roe = models.DecimalField(max_digits=4, decimal_places=2, default=10.0, help_text='Min ROE %')
    
    # Risk management
    max_position_size = models.DecimalField(max_digits=10, decimal_places=2, default=10000)
    max_loss_per_trade = models.DecimalField(max_digits=5, decimal_places=2, default=30.0)
    
    # Notifications
    email_notifications = models.BooleanField(default=True)
    notification_email = models.EmailField(blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'User Configuration'
        verbose_name_plural = 'User Configurations'
    
    def __str__(self):
        return f"Config - Updated {self.updated_at.strftime('%Y-%m-%d')}"


class StockIndicator(models.Model):
    """Technical indicators for stocks"""
    stock = models.OneToOneField(Stock, on_delete=models.CASCADE, related_name='indicators', primary_key=True)
    
    # RSI (Relative Strength Index)
    rsi = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text='RSI (14-period)')
    rsi_signal = models.CharField(max_length=20, blank=True, choices=[
        ('OVERSOLD', 'Oversold < 30'),
        ('NEUTRAL', 'Neutral 30-70'),
        ('OVERBOUGHT', 'Overbought > 70')
    ])
    
    # EMAs (Exponential Moving Averages)
    ema_50 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='50-day EMA')
    ema_200 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='200-day EMA')
    ema_trend = models.CharField(max_length=20, blank=True, choices=[
        ('BULLISH', 'Bullish (50 > 200)'),
        ('BEARISH', 'Bearish (50 < 200)'),
        ('NEUTRAL', 'Neutral')
    ])
    
    # Bollinger Bands
    bb_upper = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bb_middle = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bb_lower = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bb_position = models.CharField(max_length=20, blank=True, help_text='Price position vs BB')
    
    # Support & Resistance Levels (detected from 6-month history)
    support_level_1 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Strongest support')
    support_level_2 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    support_level_3 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    resistance_level_1 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Strongest resistance')
    resistance_level_2 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    resistance_level_3 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Historical price data (JSON field for last 180 days)
    price_history = models.JSONField(null=True, blank=True, help_text='Last 180 days: [{date, open, high, low, close, volume}]')
    
    # Metadata
    last_calculated = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['stock']
    
    def __str__(self):
        return f"{self.stock.ticker} Indicators"
    
    @property
    def near_support(self):
        """Check if price is within 3% of any support level"""
        if not self.stock.last_price:
            return False
        price = float(self.stock.last_price)
        supports = [self.support_level_1, self.support_level_2, self.support_level_3]
        for support in supports:
            if support:
                support_val = float(support)
                if abs(price - support_val) / support_val <= 0.03:
                    return True
        return False
    
    @property
    def near_resistance(self):
        """Check if price is within 3% of any resistance level"""
        if not self.stock.last_price:
            return False
        price = float(self.stock.last_price)
        resistances = [self.resistance_level_1, self.resistance_level_2, self.resistance_level_3]
        for resistance in resistances:
            if resistance:
                resistance_val = float(resistance)
                if abs(price - resistance_val) / resistance_val <= 0.03:
                    return True
        return False


class Position(models.Model):
    """Track stock positions from assigned puts (for covered calls)"""
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='positions')
    quantity = models.IntegerField(default=100, help_text='Number of shares (typically 100 per contract)')
    cost_basis = models.DecimalField(max_digits=10, decimal_places=2, help_text='Average cost per share')
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, help_text='Total position cost')
    assigned_date = models.DateField(help_text='Date when put was assigned')
    assignment_strike = models.DecimalField(max_digits=10, decimal_places=2, help_text='Strike price of assigned put')
    premium_collected = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Premium from put sale')
    is_active = models.BooleanField(default=True, help_text='False if shares sold via covered call')
    exit_date = models.DateField(null=True, blank=True, help_text='Date when covered call was assigned')
    exit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Call strike price')
    total_profit_loss = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        status = "Active" if self.is_active else "Closed"
        return f"{self.stock.ticker} Position ({self.quantity} shares) - {status}"
    
    @property
    def current_value(self):
        """Current market value of position"""
        if self.stock.last_price and self.is_active:
            return float(self.stock.last_price) * self.quantity
        return None
    
    @property
    def unrealized_pl(self):
        """Unrealized profit/loss"""
        if self.current_value and self.is_active:
            return self.current_value - float(self.total_cost)
        return None
    
    @property
    def unrealized_pl_pct(self):
        """Unrealized P/L percentage"""
        if self.unrealized_pl and self.total_cost:
            return (self.unrealized_pl / float(self.total_cost)) * 100
        return None


class OptionPosition(models.Model):
    """Track sold option positions for wheel strategy"""
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('CLOSED', 'Closed - Bought Back'),
        ('ASSIGNED', 'Assigned'),
        ('EXPIRED', 'Expired Worthless'),
    ]
    
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='option_positions')
    option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name='positions', null=True, blank=True)
    option_type = models.CharField(max_length=4, choices=[('PUT', 'Put'), ('CALL', 'Call')])
    strike = models.DecimalField(max_digits=10, decimal_places=2)
    expiry_date = models.DateField()
    
    # Entry details
    contracts = models.IntegerField(default=1, help_text='Number of contracts')
    entry_date = models.DateField(default=timezone.now)
    entry_premium = models.DecimalField(max_digits=10, decimal_places=2, help_text='Premium collected per share')
    total_premium = models.DecimalField(max_digits=10, decimal_places=2, help_text='Total premium collected')
    entry_stock_price = models.DecimalField(max_digits=10, decimal_places=2, help_text='Stock price when opened')
    entry_delta = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    
    # Current status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    current_premium = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Current premium to close')
    
    # Exit details
    exit_date = models.DateField(null=True, blank=True)
    exit_premium = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Premium paid to close')
    realized_pl = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Tracking
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.stock.ticker} ${self.strike} {self.option_type} {self.expiry_date} - {self.status}"
    
    @property
    def days_held(self):
        """Number of days position has been held"""
        if self.status == 'OPEN':
            return (timezone.now().date() - self.entry_date).days
        elif self.exit_date:
            return (self.exit_date - self.entry_date).days
        return 0
    
    @property
    def dte(self):
        """Days to expiration"""
        return (self.expiry_date - timezone.now().date()).days
    
    @property
    def unrealized_pl(self):
        """Unrealized P/L for open positions"""
        if self.status == 'OPEN' and self.current_premium is not None:
            # For sold options: profit when premium decreases
            return float(self.total_premium) - (float(self.current_premium) * self.contracts * 100)
        return None
    
    @property
    def unrealized_pl_pct(self):
        """Unrealized P/L percentage"""
        if self.unrealized_pl is not None and self.total_premium:
            return (self.unrealized_pl / float(self.total_premium)) * 100
        return None
    
    @property
    def max_profit(self):
        """Maximum profit (premium collected)"""
        return float(self.total_premium)
    
    @property
    def max_loss(self):
        """Maximum loss (for puts: strike * contracts * 100 - premium)"""
        if self.option_type == 'PUT':
            return (float(self.strike) * self.contracts * 100) - float(self.total_premium)
        return None  # Undefined for naked calls
    
    @property
    def break_even(self):
        """Break-even price"""
        premium_per_share = float(self.entry_premium)
        if self.option_type == 'PUT':
            return float(self.strike) - premium_per_share
        else:  # CALL
            return float(self.strike) + premium_per_share
    
    @property
    def profit_target_50pct(self):
        """Price target for 50% profit"""
        if self.current_premium is not None:
            target_premium = float(self.entry_premium) * 0.5
            return target_premium * self.contracts * 100
        return None


class StockWheelScore(models.Model):
    """Historical wheel strategy scores for stocks"""
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='wheel_scores')
    total_score = models.IntegerField(default=0, help_text='Total blended score 0-100')
    volatility_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Volatility factor (25%)')
    liquidity_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Liquidity factor (20%)')
    technical_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Technical factor (25%)')
    stability_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Stability factor (20%)')
    price_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Price level factor (10%)')
    grade = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')], help_text='Letter grade')
    calculated_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-calculated_at']
        indexes = [
            models.Index(fields=['stock', '-calculated_at']),
        ]
    
    def __str__(self):
        return f"{self.stock.ticker} - Grade {self.grade} ({self.total_score}/100) - {self.calculated_at.date()}"
    
    @property
    def score_trend(self):
        """Compare to previous score to determine trend"""
        previous = StockWheelScore.objects.filter(
            stock=self.stock,
            calculated_at__lt=self.calculated_at
        ).first()
        
        if not previous:
            return 'stable'
        
        diff = self.total_score - previous.total_score
        if diff > 5:
            return 'improving'
        elif diff < -5:
            return 'declining'
        else:
            return 'stable'


class Alert(models.Model):
    """Price and premium alerts for positions and stocks"""
    ALERT_TYPE_CHOICES = [
        ('STOCK_PRICE', 'Stock Price Alert'),
        ('OPTION_PREMIUM', 'Option Premium Alert'),
        ('50_PERCENT_PROFIT', '50% Profit Target'),
        ('ASSIGNMENT_RISK', 'Assignment Risk Alert'),
        ('EXPIRATION_WARNING', 'Expiration Warning'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('TRIGGERED', 'Triggered'),
        ('DISMISSED', 'Dismissed'),
        ('EXPIRED', 'Expired'),
    ]
    
    NOTIFICATION_METHOD_CHOICES = [
        ('BROWSER', 'Browser Push'),
        ('TELEGRAM', 'Telegram'),
        ('BOTH', 'Both'),
    ]
    
    # Alert details
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    position = models.ForeignKey(OptionPosition, on_delete=models.CASCADE, related_name='alerts', null=True, blank=True)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='alerts', null=True, blank=True)
    
    # Trigger conditions
    target_stock_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Stock price to trigger alert')
    target_premium = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text='Option premium to trigger alert')
    trigger_above = models.BooleanField(default=False, help_text='True = alert when price goes above target, False = below')
    
    # Notification settings
    notification_method = models.CharField(max_length=10, choices=NOTIFICATION_METHOD_CHOICES, default='BOTH')
    telegram_chat_id = models.CharField(max_length=50, blank=True, help_text='Telegram chat ID for notifications')
    push_subscription = models.JSONField(null=True, blank=True, help_text='Browser push subscription data')
    
    # Alert metadata
    message = models.TextField(help_text='Alert message to display')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(default=timezone.now)
    triggered_at = models.DateTimeField(null=True, blank=True)
    last_checked = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'alert_type']),
            models.Index(fields=['position', 'status']),
        ]
    
    def __str__(self):
        if self.position:
            return f"{self.alert_type} - {self.position.stock.ticker} ({self.status})"
        return f"{self.alert_type} - {self.stock.ticker if self.stock else 'General'} ({self.status})"
    
    def check_trigger(self):
        """Check if alert should be triggered"""
        if self.status != 'ACTIVE':
            return False
        
        # Stock price alerts
        if self.alert_type in ['STOCK_PRICE', 'ASSIGNMENT_RISK'] and self.target_stock_price:
            stock = self.stock or (self.position.stock if self.position else None)
            if not stock or not stock.last_price:
                return False
            
            current_price = float(stock.last_price)
            target = float(self.target_stock_price)
            
            if self.trigger_above and current_price >= target:
                return True
            elif not self.trigger_above and current_price <= target:
                return True
        
        # Option premium alerts (50% profit, etc)
        if self.alert_type in ['OPTION_PREMIUM', '50_PERCENT_PROFIT'] and self.target_premium and self.position:
            if not self.position.current_premium:
                return False
            
            current_premium = float(self.position.current_premium)
            target = float(self.target_premium)
            
            # For sold options, we want to be notified when premium drops to target
            if current_premium <= target:
                return True
        
        # Expiration warnings
        if self.alert_type == 'EXPIRATION_WARNING' and self.position:
            if self.position.dte <= 3:  # 3 days or less
                return True
        
        return False
    
    def trigger(self):
        """Mark alert as triggered and send notifications"""
        self.status = 'TRIGGERED'
        self.triggered_at = timezone.now()
        self.save()
        
        # Send notifications based on method
        if self.notification_method in ['TELEGRAM', 'BOTH']:
            self.send_telegram_notification()
        
        if self.notification_method in ['BROWSER', 'BOTH']:
            self.send_browser_notification()
    
    def send_telegram_notification(self):
        """Send Telegram notification"""
        # Will implement in next step
        pass
    
    def send_browser_notification(self):
        """Send browser push notification"""
        # Will implement in next step
        pass


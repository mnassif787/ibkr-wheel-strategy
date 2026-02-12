from django.contrib import admin
from .models import Stock, Option, Signal, Watchlist, UserConfig, StockIndicator, Position


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'name', 'last_price', 'market_cap', 'beta', 'roe', 'last_updated']
    list_filter = ['sector', 'last_updated']
    search_fields = ['ticker', 'name', 'sector']
    readonly_fields = ['last_updated']


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ['stock', 'strike', 'option_type', 'expiry_date', 'bid', 'ask', 'volume', 'open_interest', 'dte']
    list_filter = ['option_type', 'expiry_date', 'last_updated']
    search_fields = ['stock__ticker']
    readonly_fields = ['last_updated']
    
    def dte(self, obj):
        return obj.dte
    dte.short_description = 'DTE'


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ['stock', 'option', 'signal_type', 'grade', 'quality_score', 'apy_pct', 'status', 'generated_at']
    list_filter = ['status', 'signal_type', 'grade', 'generated_at']
    search_fields = ['stock__ticker', 'technical_reason']
    readonly_fields = ['generated_at', 'quality_score']
    fieldsets = (
        ('Basic Info', {
            'fields': ('stock', 'option', 'signal_type', 'status')
        }),
        ('Financial Metrics', {
            'fields': ('premium', 'err_pct', 'apy_pct', 'break_even', 'max_loss_pct')
        }),
        ('Quality Scoring', {
            'fields': ('quality_score', 'grade', 'stock_score', 'technical_score', 'options_score', 'assignment_risk')
        }),
        ('Analysis', {
            'fields': ('technical_reason', 'notes')
        }),
        ('Metadata', {
            'fields': ('generated_at',)
        }),
    )


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'added_at', 'notes']
    search_fields = ['ticker']
    readonly_fields = ['added_at']


@admin.register(UserConfig)
class UserConfigAdmin(admin.ModelAdmin):
    list_display = ['min_dte', 'max_dte', 'min_delta', 'max_delta', 'email_notifications', 'updated_at']
    readonly_fields = ['updated_at']
    
    fieldsets = (
        ('Strategy Parameters', {
            'fields': ('min_dte', 'max_dte', 'min_delta', 'max_delta', 'max_iv', 'min_premium_pct', 'min_roe')
        }),
        ('Risk Management', {
            'fields': ('max_position_size', 'max_loss_per_trade')
        }),
        ('Notifications', {
            'fields': ('email_notifications', 'notification_email')
        }),
    )


@admin.register(StockIndicator)
class StockIndicatorAdmin(admin.ModelAdmin):
    list_display = ['stock', 'rsi', 'rsi_signal', 'ema_trend', 'last_calculated']
    list_filter = ['rsi_signal', 'ema_trend', 'last_calculated']
    search_fields = ['stock__ticker']
    readonly_fields = ['last_calculated']
    fieldsets = (
        ('RSI', {
            'fields': ('stock', 'rsi', 'rsi_signal')
        }),
        ('EMAs', {
            'fields': ('ema_50', 'ema_200', 'ema_trend')
        }),
        ('Bollinger Bands', {
            'fields': ('bb_upper', 'bb_middle', 'bb_lower', 'bb_position')
        }),
        ('Support Levels', {
            'fields': ('support_level_1', 'support_level_2', 'support_level_3')
        }),
        ('Resistance Levels', {
            'fields': ('resistance_level_1', 'resistance_level_2', 'resistance_level_3')
        }),
        ('Metadata', {
            'fields': ('last_calculated', 'price_history')
        }),
    )


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ['stock', 'quantity', 'cost_basis', 'assigned_date', 'is_active', 'unrealized_pl_pct']
    list_filter = ['is_active', 'assigned_date']
    search_fields = ['stock__ticker']
    readonly_fields = ['created_at', 'updated_at', 'current_value', 'unrealized_pl', 'unrealized_pl_pct']
    
    def unrealized_pl_pct(self, obj):
        if obj.unrealized_pl_pct:
            return f"{obj.unrealized_pl_pct:.2f}%"
        return "--"
    unrealized_pl_pct.short_description = 'P/L %'

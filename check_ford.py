import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.ibkr.models import Stock
from apps.ibkr.views import calculate_wheel_score, calculate_entry_signal

# Get Ford stock
f = Stock.objects.get(ticker='F')

print('=== FORD (F) STOCK DATA ===')
print(f'Price: ${f.last_price}')
print(f'Has indicators: {hasattr(f, "indicators")}')

ind = f.indicators if hasattr(f, 'indicators') else None
print(f'Indicator exists: {ind is not None}')

if ind:
    print(f'RSI: {ind.rsi}')
    print(f'EMA Trend: {ind.ema_trend}')
    print(f'Support Level 1: {ind.support_level_1}')
    print(f'Resistance Level 1: {ind.resistance_level_1}')

print(f'Options count: {f.options.count()}')

print('\n=== WHEEL SCORE ===')
try:
    ws = calculate_wheel_score(f)
    print(f'Total Score: {ws["total_score"]}')
    print(f'Grade: {ws["grade"]}')
    print(f'Volatility: {ws["volatility_score"]:.1f}/25')
    print(f'Liquidity: {ws["liquidity_score"]:.1f}/20')
    print(f'Technical: {ws["technical_score"]:.1f}/25')
    print(f'Stability: {ws["stability_score"]:.1f}/20')
    print(f'Price: {ws["price_score"]:.1f}/10')
except Exception as e:
    print(f'ERROR: {e}')

print('\n=== ENTRY SIGNAL ===')
try:
    es = calculate_entry_signal(f)
    print(f'Signal: {es["signal"]}')
    print(f'Quality: {es["quality"]}')
    print(f'Score: {es["score"]}/100')
    print(f'Reasons:')
    for reason in es["reasons"]:
        print(f'  - {reason}')
except Exception as e:
    print(f'ERROR: {e}')

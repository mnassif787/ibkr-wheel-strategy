import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.ibkr.models import Option

print(f'Total options: {Option.objects.count()}')
print(f'Options with bid: {Option.objects.filter(bid__isnull=False).count()}')
print(f'Options with ask: {Option.objects.filter(ask__isnull=False).count()}')
print(f'Options with delta: {Option.objects.filter(delta__isnull=False).count()}')
print(f'Options with implied_volatility: {Option.objects.filter(implied_volatility__isnull=False).count()}')

print('\n5 Sample AAPL options:')
for opt in Option.objects.filter(stock__ticker='AAPL', option_type='PUT')[:5]:
    print(f'  ${opt.strike} {opt.option_type} {opt.expiry_date}: Bid={opt.bid}, Ask={opt.ask}, Mid={opt.mid_price}, Delta={opt.delta}, DTE={opt.dte}')

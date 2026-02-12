import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.ibkr.models import Option
from django.db.models import Count

print(f'Total options: {Option.objects.count()}')
print('\nOptions by stock:')
for s in Option.objects.values('stock__ticker').annotate(count=Count('id')).order_by('-count'):
    print(f"  {s['stock__ticker']}: {s['count']} options")

if Option.objects.exists():
    opt = Option.objects.first()
    print(f'\nSample option: {opt}')
    print(f'  Bid: {opt.bid}, Ask: {opt.ask}, Delta: {opt.delta}')

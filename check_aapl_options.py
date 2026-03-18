#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.ibkr.models import Stock, Option

# Check CMCSA instead
cmcsa = Stock.objects.filter(ticker='CMCSA').first()
if not cmcsa:
    print("CMCSA not found")
    exit()

print(f"Stock: {cmcsa.ticker} - {cmcsa.name}")
print(f"Price: ${cmcsa.last_price}")
print(f"Last updated: {cmcsa.last_updated}")

# Get all PUT options (mid_price is a property, can't filter in query)
puts = Option.objects.filter(stock=cmcsa, option_type='PUT')
print(f"\nTotal PUTs: {puts.count()}")

# Show all PUTs with DTE
all_with_dte = [(p, p.dte, p.bid, p.ask, p.mid_price, p.delta) for p in puts if p.dte and p.dte >= 0]
all_with_dte.sort(key=lambda x: x[1])  # Sort by DTE
print(f"\nAll PUTs with DTE (showing first 20):")
for p, dte, bid, ask, mid, delta in all_with_dte[:20]:
    print(f"  Strike ${p.strike}, DTE: {dte}, Bid: ${bid}, Ask: ${ask}, Mid: ${mid}, Delta: {delta}")

# Filter by DTE and mid_price availability
valid_dte_puts = [p for p in puts if p.dte and 14 <= p.dte <= 60 and p.mid_price]
print(f"\nPUTs with DTE 14-60 and mid_price: {len(valid_dte_puts)}")

if valid_dte_puts:
    # Show first 3
    print("\nFirst 3 valid PUTs:")
    for p in valid_dte_puts[:3]:
        delta_abs = abs(float(p.delta)) if p.delta else 0
        print(f"  - Strike: ${p.strike}, DTE: {p.dte}, Mid: ${p.mid_price}, Delta: {p.delta} (abs: {delta_abs:.3f})")
        
    # Check for best entry trade criteria (delta 0.25-0.35, DTE 14-45)
    best_candidates = [p for p in valid_dte_puts if p.delta and 0.25 <= abs(float(p.delta)) <= 0.35 and 14 <= p.dte <= 45]
    print(f"\nBest entry trade candidates (delta 0.25-0.35, DTE 14-45): {len(best_candidates)}")
    
    if best_candidates:
        print("Top 3 candidates:")
        for p in best_candidates[:3]:
            apy = (float(p.mid_price) / float(p.strike)) * (365 / p.dte) * 100
            print(f"  - ${p.strike} {p.expiry_date}, DTE: {p.dte}, Delta: {p.delta}, APY: {apy:.1f}%")

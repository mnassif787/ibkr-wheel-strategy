#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.ibkr.models import Stock, Option
from django.utils import timezone

# Get CMCSA
cmcsa = Stock.objects.filter(ticker='CMCSA').first()
if not cmcsa:
    print("CMCSA not found")
    exit()

print(f"Testing signal generation for {cmcsa.ticker}")
print("=" * 60)

# Get all PUT options
all_puts = Option.objects.filter(
    stock=cmcsa,
    option_type='PUT',
).order_by('-implied_volatility')

print(f"Total PUTs: {all_puts.count()}")

# Filter in Python for DTE range and valid mid_price
top_puts = [p for p in all_puts if p.dte and 14 <= p.dte <= 60 and p.mid_price][:5]
print(f"Top 5 PUTs (DTE 14-60, has mid_price): {len(top_puts)}")

signals = []
best_entry_trade = None
best_apy = 0

for i, put in enumerate(top_puts, 1):
    print(f"\n--- Processing PUT #{i}: ${put.strike} exp {put.expiry_date} ---")
    print(f"  DTE: {put.dte}")
    print(f"  Bid: {put.bid}, Ask: {put.ask}, Last: {put.last}")
    print(f"  Mid price: {put.mid_price}")
    print(f"  Delta: {put.delta}")
    print(f"  Strike: {put.strike}")
    
    # Check conditions
    if put.delta:
        print(f"  ✓ Has delta: {put.delta}")
        delta_abs = abs(float(put.delta))
        print(f"  ✓ Delta abs: {delta_abs}")
        
        if put.mid_price:
            print(f"  ✓ Has mid_price: {put.mid_price}")
            
            if put.strike:
                print(f"  ✓ Has strike: {put.strike}")
                
                # Calculate APY
                apy = (float(put.mid_price) / float(put.strike)) * (365 / put.dte) * 100 if put.dte > 0 else 0
                print(f"  ✓ APY calculated: {apy:.1f}%")
                
                # Check delta and APY thresholds
                if 0.20 <= delta_abs <= 0.40:
                    print(f"  ✓ Delta in range 0.20-0.40")
                    
                    if apy >= 10:
                        print(f"  ✓ APY >= 10%")
                        print(f"  ✅ ADDED TO SIGNALS")
                        signals.append(put)
                        
                        # Check for best entry trade
                        if 0.25 <= delta_abs <= 0.35 and 14 <= put.dte <= 45 and apy > best_apy:
                            best_apy = apy
                            best_entry_trade = put
                            print(f"  ⭐ BEST ENTRY TRADE (APY: {apy:.1f}%)")
                    else:
                        print(f"  ✗ APY {apy:.1f}% < 10%")
                else:
                    print(f"  ✗ Delta {delta_abs:.3f} not in range 0.20-0.40")
            else:
                print(f"  ✗ No strike")
        else:
            print(f"  ✗ No mid_price")
    else:
        print(f"  ✗ No delta")

print("\n" + "=" * 60)
print(f"📊 Total signals created: {len(signals)}")
print(f"⭐ Best entry trade: {best_entry_trade}")
if best_entry_trade:
    print(f"   Strike: ${best_entry_trade.strike}, DTE: {best_entry_trade.dte}, APY: {best_apy:.1f}%")

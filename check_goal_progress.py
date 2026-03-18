import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.ibkr.models import OptionPosition
from datetime import date

today = date.today()
year, month = today.year, today.month
print(f"=== Monthly Goal Progress Breakdown — {today.strftime('%B %Y')} ===\n")

# --- Closed/Expired/Assigned this month ---
closed = OptionPosition.objects.filter(
    status__in=['CLOSED', 'EXPIRED', 'ASSIGNED'],
    exit_date__year=year,
    exit_date__month=month,
).select_related('stock').order_by('exit_date')

print(f"CLOSED / EXPIRED / ASSIGNED  (exit_date in {today.strftime('%B')}):")
realized_total = 0.0
if not closed:
    print("  (none)")
for p in closed:
    pl = float(p.realized_pl) if p.realized_pl is not None else 0.0
    realized_total += pl
    print(f"  {p.stock.ticker:<6} {p.option_type:<4} strike={p.strike:<8} exp={p.expiry_date}  "
          f"status={p.status:<10} exit={p.exit_date}  realized_pl={pl:+.2f}")
print(f"\n  SUBTOTAL realized P&L : ${realized_total:.2f}\n")

# --- Still OPEN but entered this month ---
open_pos = OptionPosition.objects.filter(
    status='OPEN',
    entry_date__year=year,
    entry_date__month=month,
).select_related('stock').order_by('entry_date')

print(f"OPEN positions entered in {today.strftime('%B')}  (locked-in premium counted toward goal):")
locked_total = 0.0
if not open_pos:
    print("  (none)")
for p in open_pos:
    tp = float(p.total_premium) if p.total_premium is not None else 0.0
    locked_total += tp
    print(f"  {p.stock.ticker:<6} {p.option_type:<4} strike={p.strike:<8} exp={p.expiry_date}  "
          f"entry={p.entry_date}  total_premium={tp:.2f}")
print(f"\n  SUBTOTAL locked-in premium: ${locked_total:.2f}\n")

grand = realized_total + locked_total
print("=" * 55)
print(f"  TOTAL EARNED THIS MONTH : ${grand:.2f}")
print(f"    = ${realized_total:.2f} realized  +  ${locked_total:.2f} locked-in")
print("=" * 55)

# Also show OPEN positions from PRIOR months (NOT counted toward goal)
prior_open = OptionPosition.objects.filter(
    status='OPEN',
).exclude(entry_date__year=year, entry_date__month=month).select_related('stock')

if prior_open.exists():
    print(f"\nNOTE — OPEN positions from PRIOR months (NOT counted in goal):")
    for p in prior_open:
        tp = float(p.total_premium) if p.total_premium else 0
        print(f"  {p.stock.ticker:<6} {p.option_type:<4} strike={p.strike:<8} exp={p.expiry_date}  "
              f"entry={p.entry_date}  total_premium={tp:.2f}  (excluded)")

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.ibkr.models import Stock
from apps.ibkr.services.yfinance_options import YFinanceOptionsService

# Get first stock
stock = Stock.objects.first()
print(f"Testing with: {stock.ticker}")
print(f"Stock last_price: {stock.last_price}")

# Fetch options
print("\nFetching options...")
options_data = YFinanceOptionsService.get_options_chain(stock.ticker, max_expiries=2)

print(f"\nReturned {len(options_data)} options")

if options_data:
    print("\nFirst option:")
    opt = options_data[0]
    for key, value in opt.items():
        print(f"  {key}: {value}")
else:
    print("No options returned!")

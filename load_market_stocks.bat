@echo off
echo ========================================
echo Loading Comprehensive Market Stocks
echo ========================================
echo.
echo This will load 300+ stocks covering all major sectors
echo and calculate their wheel strategy scores.
echo.
echo This process may take 10-15 minutes.
echo.
pause

echo.
echo Step 1/3: Discovering stocks from market...
python manage.py discover_stocks --preset market

echo.
echo Step 2/3: Calculating technical indicators (RSI, EMA, Support/Resistance)...
python manage.py calculate_indicators

echo.
echo Step 3/3: Fetching options data from Yahoo Finance...
python manage.py sync_yfinance_options

echo.
echo ========================================
echo ✅ Market data loading complete!
echo ========================================
echo.
echo You now have comprehensive market coverage in your Discovery tab.
echo Refresh your browser to see all stocks ranked by wheel score.
echo.
pause

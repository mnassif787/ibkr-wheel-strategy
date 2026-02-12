@echo off
REM Add popular wheel strategy stocks to database
echo ========================================
echo Adding Popular Wheel Strategy Stocks
echo ========================================
echo.
echo This will add 50 popular stocks for wheel strategy screening
echo including: AAPL, MSFT, TSLA, F, SOFI, SPY, QQQ, and more...
echo.
pause

cd "C:\Nassif\AI\Wheel Strategy\Wheel Strategy\ibkr-wheel-django"
call venv\Scripts\activate.bat

echo.
echo Step 1: Adding stocks from market...
python manage.py discover_stocks --preset=popular --limit=50

echo.
echo Step 2: Calculating technical indicators...
python manage.py calculate_indicators

echo.
echo Step 3: Syncing options data...
python manage.py sync_yfinance_options

echo.
echo ========================================
echo ✅ Complete! Stocks added and analyzed.
echo ========================================
echo.
echo Refresh your browser to see new stocks with:
echo - Wheel Scores (stock quality)
echo - Entry Signals (timing to sell puts)
echo.
pause

@echo off
echo ========================================
echo Complete Data Refresh for All Stocks
echo ========================================
echo.
echo This will populate all missing data for your 110 stocks:
echo - Technical Indicators (RSI, EMA, Support/Resistance)
echo - Options Chain Data from Yahoo Finance
echo.
echo This process may take 5-10 minutes.
echo.
pause

echo.
echo Step 1/2: Calculating technical indicators for all stocks...
echo ========================================
python manage.py calculate_indicators
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ⚠️  Some errors occurred but continuing...
)

echo.
echo Step 2/2: Fetching options data from Yahoo Finance...
echo ========================================
python manage.py sync_yfinance_options
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ⚠️  Some errors occurred but continuing...
)

echo.
echo ========================================
echo ✅ Data refresh complete!
echo ========================================
echo.
echo Now click "Refresh" button in your browser to reload the data.
echo Your Discovery tab should show all 110 stocks with full data.
echo.
pause

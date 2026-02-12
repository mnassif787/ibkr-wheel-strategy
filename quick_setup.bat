@echo off
REM Quick setup: Add stocks + Calculate indicators + Sync options
echo ========================================
echo Wheel Strategy - Quick Setup
echo ========================================
echo.
echo This will:
echo 1. Add 50 popular wheel strategy stocks
echo 2. Calculate technical indicators
echo 3. Sync options data from Yahoo Finance
echo.
echo Estimated time: 5-10 minutes
echo.
pause

cd "C:\Nassif\AI\Wheel Strategy\Wheel Strategy\ibkr-wheel-django"
call venv\Scripts\activate.bat

echo.
echo [1/3] 📥 Discovering stocks...
echo.
python manage.py discover_stocks --preset=popular --limit=50

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Error adding stocks. Check error above.
    pause
    exit /b 1
)

echo.
echo [2/3] 📊 Calculating technical indicators...
echo.
python manage.py calculate_indicators

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Error calculating indicators. Check error above.
    pause
    exit /b 1
)

echo.
echo [3/3] 📈 Syncing options data...
echo.
python manage.py sync_yfinance_options

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ⚠️ Some options may have failed, but continuing...
)

echo.
echo ========================================
echo ✅ SETUP COMPLETE!
echo ========================================
echo.
echo You now have:
echo - 50+ stocks in database
echo - Wheel Scores calculated
echo - Entry Signals calculated
echo - Options data synced
echo.
echo 🌐 Go to: http://127.0.0.1:8000/ibkr/stocks/
echo.
echo To start the server:
echo   python manage.py runserver
echo.
pause

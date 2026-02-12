@echo off
REM Calculate technical indicators for Ford (F) stock
echo ========================================
echo Calculating Technical Indicators for F
echo ========================================
echo.

cd "C:\Nassif\AI\Wheel Strategy\Wheel Strategy\ibkr-wheel-django"
call venv\Scripts\activate.bat
python manage.py calculate_indicators --ticker=F

echo.
echo ========================================
echo Done! Refresh the stocks page to see updated scores.
echo ========================================
pause

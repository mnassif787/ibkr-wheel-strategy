@echo off
REM Sync trading positions from IBKR
echo ================================================
echo   Syncing Positions from IBKR Gateway/TWS
echo ================================================
echo.
python manage.py sync_positions
echo.
pause

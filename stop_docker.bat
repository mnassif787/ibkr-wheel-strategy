@echo off
echo ============================================
echo  IBKR Wheel Strategy - Stop Docker
echo ============================================
echo.

echo Stopping all containers...
docker compose down
echo.
echo [OK] All containers stopped.
echo.
pause

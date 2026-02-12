@echo off
echo ============================================
echo  IBKR Wheel Strategy - Docker Logs
echo ============================================
echo.
echo Press Ctrl+C to stop viewing logs
echo.
docker compose logs -f --tail=50

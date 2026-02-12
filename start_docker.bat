@echo off
echo ============================================
echo  IBKR Wheel Strategy - Docker Startup
echo ============================================
echo.

:: Check Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Desktop is not running!
    echo Please start Docker Desktop first, then try again.
    echo.
    pause
    exit /b 1
)

echo [OK] Docker Desktop is running
echo.

:: Build and start containers
echo [1/3] Building containers (first time takes 2-5 minutes)...
docker compose build --no-cache
echo.

echo [2/3] Starting IB Gateway + Web App...
docker compose up -d
echo.

echo [3/3] Waiting for services to start...
timeout /t 15 /nobreak >nul

:: Check status
echo.
echo ============================================
echo  STATUS CHECK
echo ============================================
docker compose ps
echo.
echo ============================================
echo  ACCESS YOUR PLATFORM
echo ============================================
echo.
echo  Web Dashboard:     http://localhost:8000
echo  IB Gateway VNC:    vnc://localhost:5900  (password: ibkrvnc)
echo.
echo  To view logs:      docker compose logs -f
echo  To stop:           docker compose down
echo.
echo  To access ONLINE, run: start_ngrok.bat
echo ============================================
echo.
pause

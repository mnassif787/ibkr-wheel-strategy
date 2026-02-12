@echo off
echo ============================================
echo  IBKR Wheel Strategy - Ngrok Online Access
echo ============================================
echo.

:: Check if ngrok is installed
where ngrok >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Ngrok is not installed or not in PATH.
    echo.
    echo  INSTALLATION STEPS:
    echo  1. Go to https://ngrok.com and sign up (FREE)
    echo  2. Download ngrok for Windows
    echo  3. Extract ngrok.exe to this folder or add to PATH
    echo  4. Run: ngrok config add-authtoken YOUR_TOKEN
    echo  5. Then run this script again
    echo.
    pause
    exit /b 1
)

:: Check Docker containers are running
docker compose ps --format "{{.State}}" 2>nul | findstr "running" >nul
if %errorlevel% neq 0 (
    echo [!] Docker containers not running. Starting them first...
    call start_docker.bat
)

echo.
echo [OK] Starting ngrok tunnel to port 8000...
echo.
echo  Your platform will be available at the HTTPS URL shown below.
echo  Share this URL to access from your phone, tablet, or anywhere!
echo.
echo  Press Ctrl+C to stop the tunnel.
echo ============================================
echo.

ngrok http 8000 --scheme https

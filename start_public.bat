@echo off
echo ======================================
echo   IBKR Wheel Strategy Platform
echo   Starting with Public Access
echo ======================================
echo.

REM Start Docker containers
echo [1/3] Starting Docker containers...
docker-compose up -d

REM Wait for services to be ready
echo [2/3] Waiting for services to start...
timeout /t 10 /nobreak > nul

REM Check if ngrok exists
if not exist "ngrok.exe" (
    echo.
    echo ERROR: ngrok.exe not found!
    echo Please download from: https://ngrok.com/download
    echo Place ngrok.exe in this folder.
    pause
    exit /b
)

REM Start ngrok tunnel
echo [3/3] Creating public tunnel...
echo.
echo ======================================
echo   Platform Ready!
echo ======================================
echo.
echo Local:  http://localhost:8000
echo Public: (see ngrok URL below)
echo.
echo IB Gateway VNC: localhost:5900
echo.
echo Press Ctrl+C to stop the tunnel
echo ======================================
echo.

ngrok http 8000

@echo off
echo ========================================
echo IBKR Wheel Strategy - Setup Script
echo ========================================
echo.

echo [1/6] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo [2/6] Activating virtual environment...
call venv\Scripts\activate

echo [3/6] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo [4/6] Creating .env file...
if not exist .env (
    copy .env.example .env
    echo .env file created. Please update with your settings!
) else (
    echo .env file already exists. Skipping...
)

echo [5/6] Running database migrations...
python manage.py migrate
if errorlevel 1 (
    echo ERROR: Failed to run migrations
    pause
    exit /b 1
)

echo [6/6] Creating superuser...
echo.
echo Please create a superuser account:
python manage.py createsuperuser

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Update .env file with your settings
echo 2. Start TWS or IB Gateway
echo 3. Run: python manage.py runserver
echo 4. Visit: http://localhost:8000
echo.
pause

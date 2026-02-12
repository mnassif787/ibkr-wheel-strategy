@echo off
echo ============================================
echo  Deploy to Railway - Step by Step
echo ============================================
echo.

:: Check if git is initialized
if not exist ".git" (
    echo [1/4] Initializing Git repository...
    git init
    git add .
    git commit -m "Initial commit for Railway deployment"
    echo.
) else (
    echo [1/4] Git repository already initialized
    echo.
)

:: Check if remote exists
git remote -v | findstr "origin" >nul 2>&1
if %errorlevel% neq 0 (
    echo [2/4] Setting up GitHub remote...
    echo.
    echo Please enter your GitHub repository URL
    echo Example: https://github.com/username/ibkr-wheel-django.git
    echo.
    set /p REPO_URL="GitHub URL: "
    git remote add origin %REPO_URL%
    echo.
) else (
    echo [2/4] GitHub remote already configured
    echo.
)

:: Push to GitHub
echo [3/4] Pushing to GitHub...
git add .
git commit -m "Railway deployment configuration" 2>nul
git branch -M main
git push -u origin main
echo.

:: Instructions for Railway
echo [4/4] Next Steps - Railway Setup
echo ============================================
echo.
echo 1. Go to: https://railway.app
echo 2. Click "Login" and sign in with GitHub
echo 3. Click "New Project" -^> "Deploy from GitHub repo"
echo 4. Select your repository: ibkr-wheel-django
echo 5. Railway will auto-build using the Dockerfile
echo.
echo After deployment:
echo.
echo 6. Click your service -^> "Variables" tab
echo 7. Add the environment variables from RAILWAY_FULL_DEPLOY.md
echo 8. Click "Settings" -^> "Public Networking" -^> "Generate Domain"
echo.
echo Full instructions: See RAILWAY_FULL_DEPLOY.md
echo ============================================
echo.
pause

@echo off
REM DayDay Tax - Scraper & Worker Setup Script (Windows)
REM This script helps set up Playwright and Celery for the scraper module

echo ==================================
echo DayDay Tax - Scraper Setup
echo ==================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo X Python not found. Please install Python 3.11+
    exit /b 1
)

echo + Python found
python --version
echo.

REM Check if virtual environment is activated
if "%VIRTUAL_ENV%"=="" (
    echo ! Virtual environment not activated
    echo Please run: venv\Scripts\activate
    set /p continue="Continue anyway? (y/n): "
    if /i not "%continue%"=="y" exit /b 1
)

echo ==================================
echo Step 1: Installing Python packages
echo ==================================
pip install -r requirements.txt

echo.
echo ==================================
echo Step 2: Installing Playwright browsers
echo ==================================
playwright install chromium

echo.
echo ==================================
echo Step 3: Verifying Playwright installation
echo ==================================
playwright --version

echo.
echo ==================================
echo Step 4: Checking Redis connection
echo ==================================

redis-cli ping >nul 2>&1
if %errorlevel% neq 0 (
    echo ! Redis not running. Please start Redis manually or use Docker:
    echo   docker run -d --name dayday-redis -p 6379:6379 redis:7-alpine
) else (
    echo + Redis is running
)

echo.
echo ==================================
echo Setup Complete!
echo ==================================
echo.
echo Next steps:
echo.
echo 1. Start the FastAPI server:
echo    uvicorn app.main:app --reload
echo.
echo 2. Start the Celery worker:
echo    celery -A app.worker worker --loglevel=info --concurrency=2 --pool=solo
echo.
echo 3. (Optional) Start Celery Beat for scheduled tasks:
echo    celery -A app.worker beat --loglevel=info
echo.
echo 4. Run quick start tests:
echo    python quickstart.py
echo.
echo For detailed documentation, see SCRAPER_DOCS.md
echo.

pause

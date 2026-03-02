#!/bin/bash
# DayDay Tax - Scraper & Worker Setup Script
# This script helps set up Playwright and Celery for the scraper module

set -e

echo "=================================="
echo "DayDay Tax - Scraper Setup"
echo "=================================="
echo ""

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo "❌ Python not found. Please install Python 3.11+"
    exit 1
fi

echo "✅ Python found: $(python --version)"
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Virtual environment not activated"
    echo "Please run: source venv/bin/activate (Linux/Mac) or venv\\Scripts\\activate (Windows)"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "=================================="
echo "Step 1: Installing Python packages"
echo "=================================="
pip install -r requirements.txt

echo ""
echo "=================================="
echo "Step 2: Installing Playwright browsers"
echo "=================================="
playwright install chromium

echo ""
echo "=================================="
echo "Step 3: Verifying Playwright installation"
echo "=================================="
playwright --version

echo ""
echo "=================================="
echo "Step 4: Checking Redis connection"
echo "=================================="

if command -v redis-cli &> /dev/null; then
    if redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis is running"
    else
        echo "⚠️  Redis not running. Starting with Docker..."
        docker run -d --name dayday-redis -p 6379:6379 redis:7-alpine
        sleep 2
        if redis-cli ping > /dev/null 2>&1; then
            echo "✅ Redis started successfully"
        else
            echo "❌ Failed to start Redis"
        fi
    fi
else
    echo "⚠️  redis-cli not found. Assuming Redis is running..."
fi

echo ""
echo "=================================="
echo "Step 5: Checking PostgreSQL"
echo "=================================="

if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL client found"
else
    echo "⚠️  psql not found. Make sure PostgreSQL is installed."
fi

echo ""
echo "=================================="
echo "Setup Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the FastAPI server:"
echo "   uvicorn app.main:app --reload"
echo ""
echo "2. Start the Celery worker:"
echo "   celery -A app.worker worker --loglevel=info --concurrency=2 --pool=solo"
echo ""
echo "3. (Optional) Start Celery Beat for scheduled tasks:"
echo "   celery -A app.worker beat --loglevel=info"
echo ""
echo "4. Run quick start tests:"
echo "   python quickstart.py"
echo ""
echo "For detailed documentation, see SCRAPER_DOCS.md"
echo ""

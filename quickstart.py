#!/usr/bin/env python3
"""
Quick Start Script for DayDay Tax Development
==============================================

This script helps you quickly set up and test the scraper and worker.
"""

import asyncio
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_database_connection():
    """Test database connectivity"""
    try:
        from app.db.session import engine
        from sqlalchemy import text
        
        logger.info("Testing database connection...")
        
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.scalar()
        
        logger.info("✅ Database connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


async def test_redis_connection():
    """Test Redis connectivity"""
    try:
        import redis
        from app.core.config import settings
        
        logger.info("Testing Redis connection...")
        
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        
        logger.info("✅ Redis connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        return False


async def create_sample_data():
    """Create sample accountant and users for testing"""
    try:
        from app.db.session import AsyncSessionLocal
        from app.models import Accountant, User, Wallet, Task, TaskType, TaskStatus, UserStatus
        from sqlalchemy import select
        
        logger.info("Creating sample data...")
        
        async with AsyncSessionLocal() as db:
            # Check if sample accountant already exists
            result = await db.execute(
                select(Accountant).where(Accountant.phone_number == "+994501234567")
            )
            accountant = result.scalar_one_or_none()
            
            if not accountant:
                # Create sample accountant
                accountant = Accountant(
                    voen="1234567890",
                    phone_number="+994501234567",
                    is_active=True,
                    current_session_cookie=None
                )
                db.add(accountant)
                await db.flush()
                logger.info(f"✅ Created sample accountant (ID: {accountant.id})")
            else:
                logger.info(f"ℹ️  Sample accountant already exists (ID: {accountant.id})")
            
            # Create sample users
            for i in range(1, 4):
                voen = f"100000000{i}"
                
                result = await db.execute(
                    select(User).where(User.voen == voen)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    user = User(
                        assigned_accountant_id=accountant.id,
                        voen=voen,
                        status=UserStatus.ACTIVE
                    )
                    db.add(user)
                    await db.flush()
                    
                    # Create wallet
                    wallet = Wallet(
                        user_id=user.id,
                        balance=0.00
                    )
                    db.add(wallet)
                    
                    # Create sample task
                    task = Task(
                        user_id=user.id,
                        type=TaskType.INBOX_SCAN,
                        status=TaskStatus.PENDING
                    )
                    db.add(task)
                    
                    logger.info(f"✅ Created sample user {voen} with task")
                else:
                    logger.info(f"ℹ️  Sample user {voen} already exists")
            
            await db.commit()
            logger.info("✅ Sample data created successfully")
            return True
    
    except Exception as e:
        logger.error(f"❌ Failed to create sample data: {e}")
        return False


async def test_scraper():
    """Test the TaxBot scraper"""
    try:
        from app.services.scraper import TaxBot
        
        logger.info("Testing TaxBot scraper (headless mode)...")
        
        async with TaxBot(headless=True) as bot:
            logger.info("✅ Browser started successfully")
            logger.info("ℹ️  To test login, run manual test with real credentials")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Scraper test failed: {e}")
        logger.info("Make sure Playwright is installed: playwright install chromium")
        return False


def test_celery():
    """Test Celery worker connectivity"""
    try:
        from app.worker import celery_app
        
        logger.info("Testing Celery worker...")
        
        # Check if Celery can connect to Redis
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        
        if stats:
            logger.info(f"✅ Celery worker running: {len(stats)} workers")
        else:
            logger.warning("⚠️  No Celery workers detected. Start with: celery -A app.worker worker")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Celery test failed: {e}")
        return False


async def run_all_tests():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("DayDay Tax - Quick Start Test Suite")
    logger.info("=" * 60)
    logger.info("")
    
    results = {}
    
    # Test database
    results["database"] = await test_database_connection()
    logger.info("")
    
    # Test Redis
    results["redis"] = await test_redis_connection()
    logger.info("")
    
    # Create sample data
    if results["database"]:
        results["sample_data"] = await create_sample_data()
        logger.info("")
    
    # Test scraper
    results["scraper"] = await test_scraper()
    logger.info("")
    
    # Test Celery
    results["celery"] = test_celery()
    logger.info("")
    
    # Summary
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{test.upper()}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        logger.info("")
        logger.info("🎉 All tests passed! You're ready to start development.")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Start Celery worker: celery -A app.worker worker --loglevel=info")
        logger.info("2. Start FastAPI: uvicorn app.main:app --reload")
        logger.info("3. Trigger test task: from app.worker import process_batch; process_batch.delay(1)")
    else:
        logger.info("")
        logger.info("⚠️  Some tests failed. Check the errors above.")
    
    return all_passed


def main():
    """Main entry point"""
    try:
        result = asyncio.run(run_all_tests())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

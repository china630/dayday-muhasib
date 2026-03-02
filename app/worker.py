"""
Celery Worker for Asynchronous Task Processing
==============================================

This module sets up Celery for background task processing in the DayDay Tax system.

Architecture:
------------
- Uses Redis as the message broker and result backend
- Processes tasks for multiple users assigned to a single accountant in batches
- Maintains a single browser session per accountant to maximize efficiency
- Handles task retries and error recovery

Batch Processing Strategy:
-------------------------
Instead of creating one task per user (expensive), we create one task per accountant
that processes ALL users assigned to that accountant. This approach:
1. Logs in ONCE per accountant
2. Iterates through all assigned users
3. Switches taxpayer context for each user (fast)
4. Processes their pending tasks
5. Reuses the same browser session throughout

This dramatically reduces login overhead and speeds up processing.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from celery import Celery
from celery.signals import worker_init, worker_shutdown
from celery.schedules import crontab
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.models import Accountant, User, Task, Message, TaskType, TaskStatus
from app.services.scraper import TaxBot, ScraperException, LoginFailedException, TaxpayerSwitchException


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Initialize Celery
celery_app = Celery(
    "dayday_tax_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Baku",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.TASK_TIMEOUT_SECONDS,
    task_soft_time_limit=settings.TASK_TIMEOUT_SECONDS - 30,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)


@worker_init.connect
def on_worker_init(**kwargs):
    """Called when worker starts"""
    logger.info("🚀 DayDay Tax Celery Worker started")
    logger.info(f"Redis: {settings.REDIS_URL}")
    logger.info(f"Database: {settings.DATABASE_URL[:50]}...")


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """Called when worker stops"""
    logger.info("🛑 DayDay Tax Celery Worker shutting down")


async def get_accountant_with_users(accountant_id: int, db: AsyncSession) -> Optional[Dict[str, Any]]:
    """
    Get accountant and all active users assigned to them with pending tasks
    
    Args:
        accountant_id: Accountant ID
        db: Database session
    
    Returns:
        Dict with accountant info and list of users with tasks
    """
    try:
        # Get accountant
        result = await db.execute(
            select(Accountant).where(
                Accountant.id == accountant_id,
                Accountant.is_active == True
            )
        )
        accountant = result.scalar_one_or_none()
        
        if not accountant:
            logger.error(f"Accountant {accountant_id} not found or inactive")
            return None
        
        # Get all active users assigned to this accountant
        result = await db.execute(
            select(User).where(
                User.assigned_accountant_id == accountant_id,
                User.status == "ACTIVE"
            )
        )
        users = result.scalars().all()
        
        if not users:
            logger.info(f"No active users assigned to accountant {accountant_id}")
            return None
        
        # Get pending tasks for each user
        users_with_tasks = []
        for user in users:
            result = await db.execute(
                select(Task).where(
                    Task.user_id == user.id,
                    Task.status == TaskStatus.PENDING
                ).order_by(Task.created_at)
            )
            pending_tasks = result.scalars().all()
            
            if pending_tasks:
                users_with_tasks.append({
                    "user": user,
                    "tasks": pending_tasks
                })
        
        if not users_with_tasks:
            logger.info(f"No pending tasks for users of accountant {accountant_id}")
            return None
        
        return {
            "accountant": accountant,
            "users_with_tasks": users_with_tasks,
            "total_users": len(users_with_tasks),
            "total_tasks": sum(len(u["tasks"]) for u in users_with_tasks)
        }
    
    except Exception as e:
        logger.error(f"Error fetching accountant data: {e}")
        return None


async def process_task(
    task: Task,
    user: User,
    bot: TaxBot,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Process a single task for a user
    
    Args:
        task: Task to process
        user: User who owns the task
        bot: TaxBot instance (already logged in and switched to user's context)
        db: Database session
    
    Returns:
        Dict with processing result
    """
    try:
        logger.info(f"Processing task {task.id} ({task.type.value}) for user {user.voen}")
        
        # Update task status to PROCESSING
        task.status = TaskStatus.PROCESSING
        await db.commit()
        
        result_payload = {}
        
        # Execute task based on type
        if task.type == TaskType.INBOX_SCAN:
            # Fetch and store inbox messages
            messages = await bot.fetch_inbox()
            
            # Store messages in database
            for msg_data in messages:
                # Check if message already exists (avoid duplicates)
                existing = await db.execute(
                    select(Message).where(
                        Message.user_id == user.id,
                        Message.subject == msg_data["subject"],
                        Message.received_at == msg_data["received_at"]
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                
                # Create new message
                message = Message(
                    user_id=user.id,
                    subject=msg_data["subject"],
                    body_text=msg_data["body"],
                    is_risk_flagged=msg_data["is_risk_flagged"],
                    received_at=datetime.now()  # Use parsed date if available
                )
                db.add(message)
            
            result_payload = {
                "messages_fetched": len(messages),
                "risk_messages": sum(1 for m in messages if m["is_risk_flagged"]),
                "timestamp": datetime.now().isoformat()
            }
        
        elif task.type == TaskType.DEBT_CHECK:
            # Check debt status
            debt_info = await bot.check_debt()
            result_payload = debt_info
        
        elif task.type == TaskType.FILING:
            # Submit filing (would need filing data from task)
            filing_result = await bot.submit_filing(task.result_payload or {})
            result_payload = filing_result
        
        else:
            result_payload = {"error": f"Unknown task type: {task.type}"}
        
        # Update task as completed
        task.status = TaskStatus.COMPLETED
        task.result_payload = result_payload
        task.completed_at = datetime.now()
        task.error_message = None
        
        await db.commit()
        
        logger.info(f"✅ Task {task.id} completed successfully")
        return {"success": True, "task_id": task.id, "result": result_payload}
    
    except Exception as e:
        logger.error(f"❌ Error processing task {task.id}: {e}")
        
        # Update task as failed
        task.status = TaskStatus.FAILED
        task.error_message = str(e)
        await db.commit()
        
        return {"success": False, "task_id": task.id, "error": str(e)}


async def process_batch_async(accountant_id: int) -> Dict[str, Any]:
    """
    Async implementation of batch processing
    
    This function:
    1. Retrieves the accountant and all users with pending tasks
    2. Starts a browser and logs in ONCE
    3. Iterates through users, switching context for each
    4. Processes all pending tasks for each user
    5. Closes browser and returns results
    
    Args:
        accountant_id: ID of the accountant to process tasks for
    
    Returns:
        Dict with batch processing results
    """
    start_time = datetime.now()
    results = {
        "accountant_id": accountant_id,
        "started_at": start_time.isoformat(),
        "total_users": 0,
        "total_tasks": 0,
        "successful_tasks": 0,
        "failed_tasks": 0,
        "errors": [],
        "user_results": []
    }
    
    db: Optional[AsyncSession] = None
    bot: Optional[TaxBot] = None
    
    try:
        # Get database session
        db = AsyncSessionLocal()
        
        # Get accountant and users with tasks
        logger.info(f"📊 Starting batch processing for accountant {accountant_id}")
        
        data = await get_accountant_with_users(accountant_id, db)
        if not data:
            logger.info(f"No work to do for accountant {accountant_id}")
            return results
        
        accountant = data["accountant"]
        users_with_tasks = data["users_with_tasks"]
        results["total_users"] = data["total_users"]
        results["total_tasks"] = data["total_tasks"]
        
        logger.info(
            f"Found {results['total_users']} users with {results['total_tasks']} pending tasks"
        )
        
        # Initialize browser and login ONCE
        logger.info(f"🌐 Starting browser for accountant {accountant.phone_number}")
        bot = TaxBot(headless=True, screenshot_dir="/tmp/dayday_screenshots")
        
        async with bot:
            # Login with accountant credentials
            logger.info(f"🔐 Logging in accountant {accountant.phone_number}...")
            
            try:
                await bot.login_accountant(accountant.phone_number, wait_for_pin_seconds=120)
                logger.info("✅ Accountant logged in successfully")
            except LoginFailedException as e:
                logger.error(f"❌ Login failed: {e}")
                results["errors"].append(f"Login failed: {e}")
                return results
            
            # Process each user's tasks
            for user_data in users_with_tasks:
                user = user_data["user"]
                tasks = user_data["tasks"]
                
                user_result = {
                    "user_id": user.id,
                    "user_voen": user.voen,
                    "tasks_processed": 0,
                    "tasks_successful": 0,
                    "tasks_failed": 0,
                    "errors": []
                }
                
                try:
                    # Switch to this user's taxpayer context
                    logger.info(f"🔄 Switching to user {user.voen}...")
                    
                    try:
                        await bot.switch_taxpayer(user.voen)
                        logger.info(f"✅ Switched to user {user.voen}")
                    except TaxpayerSwitchException as e:
                        logger.error(f"❌ Failed to switch to user {user.voen}: {e}")
                        user_result["errors"].append(f"Taxpayer switch failed: {e}")
                        results["user_results"].append(user_result)
                        continue
                    
                    # Process all tasks for this user
                    for task in tasks:
                        user_result["tasks_processed"] += 1
                        
                        task_result = await process_task(task, user, bot, db)
                        
                        if task_result["success"]:
                            user_result["tasks_successful"] += 1
                            results["successful_tasks"] += 1
                        else:
                            user_result["tasks_failed"] += 1
                            results["failed_tasks"] += 1
                            user_result["errors"].append(
                                f"Task {task.id}: {task_result.get('error', 'Unknown error')}"
                            )
                        
                        # Small delay between tasks
                        await asyncio.sleep(1)
                    
                    logger.info(
                        f"✅ User {user.voen}: {user_result['tasks_successful']}/{user_result['tasks_processed']} tasks successful"
                    )
                
                except Exception as e:
                    logger.error(f"❌ Error processing user {user.voen}: {e}")
                    user_result["errors"].append(f"User processing error: {e}")
                
                results["user_results"].append(user_result)
        
        # Calculate duration
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["completed_at"] = end_time.isoformat()
        results["duration_seconds"] = duration
        
        logger.info(
            f"🎉 Batch processing completed for accountant {accountant_id}: "
            f"{results['successful_tasks']}/{results['total_tasks']} tasks successful "
            f"in {duration:.2f}s"
        )
        
        return results
    
    except Exception as e:
        logger.error(f"❌ Batch processing error: {e}")
        results["errors"].append(f"Batch processing error: {e}")
        return results
    
    finally:
        # Cleanup
        if db:
            await db.close()


@celery_app.task(name="process_batch", bind=True, max_retries=3)
def process_batch(self, accountant_id: int) -> Dict[str, Any]:
    """
    Celery task for batch processing all pending tasks for an accountant's users
    
    This is the main entry point for task processing. It:
    - Retrieves all users assigned to the accountant
    - Logs in once using the accountant's credentials
    - Iterates through users using context switching
    - Processes all pending tasks
    
    Args:
        accountant_id: ID of the accountant whose users' tasks should be processed
    
    Returns:
        Dict with batch processing results
    
    Usage:
        # Trigger task processing for accountant 1
        from app.worker import process_batch
        process_batch.delay(accountant_id=1)
    """
    try:
        logger.info(f"🚀 Celery task started: process_batch for accountant {accountant_id}")
        
        # Run async function in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(process_batch_async(accountant_id))
            return result
        finally:
            loop.close()
    
    except Exception as e:
        logger.error(f"❌ Celery task error: {e}")
        
        # Retry with exponential backoff
        retry_delay = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
        
        logger.info(f"⏰ Retrying in {retry_delay}s (attempt {self.request.retries + 1}/3)")
        
        raise self.retry(exc=e, countdown=retry_delay)


@celery_app.task(name="process_all_accountants")
def process_all_accountants() -> Dict[str, Any]:
    """
    Trigger batch processing for all active accountants
    
    This is useful for scheduled processing (e.g., via Celery Beat)
    
    Returns:
        Dict with summary of triggered tasks
    """
    async def get_active_accountants():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Accountant).where(Accountant.is_active == True)
            )
            return result.scalars().all()
    
    try:
        logger.info("🔍 Finding all active accountants...")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            accountants = loop.run_until_complete(get_active_accountants())
        finally:
            loop.close()
        
        if not accountants:
            logger.info("No active accountants found")
            return {"triggered_tasks": 0, "accountants": []}
        
        # Trigger batch processing for each accountant
        triggered = []
        for accountant in accountants:
            logger.info(f"🚀 Triggering batch processing for accountant {accountant.id}")
            task = process_batch.delay(accountant.id)
            triggered.append({
                "accountant_id": accountant.id,
                "task_id": task.id
            })
        
        logger.info(f"✅ Triggered {len(triggered)} batch processing tasks")
        
        return {
            "triggered_tasks": len(triggered),
            "accountants": triggered
        }
    
    except Exception as e:
        logger.error(f"❌ Error triggering batch tasks: {e}")
        return {"error": str(e)}


@celery_app.task(name="monthly_billing")
def monthly_billing() -> Dict[str, Any]:
    """
    Process monthly subscription billing for all users.
    
    This task:
    - Runs on the 1st of each month (configured in beat_schedule)
    - Deducts 10 AZN from each user's wallet
    - Blocks users with insufficient balance
    - Reactivates users who now have sufficient balance
    
    Returns:
        Dict with billing results
    
    Usage:
        # Manual trigger
        from app.worker import monthly_billing
        monthly_billing.delay()
    """
    try:
        logger.info("🏦 Starting monthly billing task...")
        
        # Import here to avoid circular imports
        from app.services.billing import BillingService
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run_billing():
            async with AsyncSessionLocal() as db:
                billing_service = BillingService(db)
                return await billing_service.process_monthly_billing()
        
        try:
            result = loop.run_until_complete(run_billing())
            
            logger.info(
                f"✅ Monthly billing completed: "
                f"charged={result['users_charged']}, "
                f"blocked={result['users_blocked']}, "
                f"total={result['total_amount_charged']} AZN"
            )
            
            return result
        finally:
            loop.close()
    
    except Exception as e:
        logger.error(f"❌ Monthly billing error: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "users_processed": 0,
            "users_charged": 0,
            "users_blocked": 0,
            "total_amount_charged": 0
        }


@celery_app.task(name="billing_preview")
def billing_preview() -> Dict[str, Any]:
    """
    Preview monthly billing impact without actually charging users.
    
    Useful for administrative purposes to see what would happen if billing runs.
    
    Returns:
        Dict with preview results
    """
    try:
        logger.info("📊 Generating billing preview...")
        
        from app.services.billing import BillingService
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run_preview():
            async with AsyncSessionLocal() as db:
                billing_service = BillingService(db)
                return await billing_service.preview_billing_impact()
        
        try:
            result = loop.run_until_complete(run_preview())
            logger.info(f"✅ Billing preview generated")
            return result
        finally:
            loop.close()
    
    except Exception as e:
        logger.error(f"❌ Billing preview error: {e}")
        return {"error": str(e)}


# Celery Beat schedule for periodic processing
celery_app.conf.beat_schedule = {
    "process-all-accountants-every-hour": {
        "task": "process_all_accountants",
        "schedule": 3600.0,  # Every hour
    },
    "monthly-billing-on-first-of-month": {
        "task": "monthly_billing",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),  # 1st of month at midnight
    },
}


if __name__ == "__main__":
    # For testing: run worker directly
    # python -m app.worker
    logger.info("Starting Celery worker...")
    celery_app.worker_main([
        "worker",
        "--loglevel=info",
        "--concurrency=2",
        "--pool=solo",  # Use solo pool for async tasks
    ])

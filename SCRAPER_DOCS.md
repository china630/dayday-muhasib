# DayDay Tax Scraper & Worker Documentation

## Overview

The scraper module provides automated interaction with the Azerbaijan tax portal (e-taxes.gov.az) using Playwright. The Celery worker handles batch processing of tasks for multiple users efficiently.

## Architecture

### Key Components

1. **TaxBot (scraper.py)**: Playwright-based automation for e-taxes.gov.az
2. **Celery Worker (worker.py)**: Asynchronous task processing
3. **Batch Processing**: Efficient multi-user task processing

### Critical Design Decisions

#### 1. Desktop Emulation (CRITICAL)

The e-taxes.gov.az website **blocks mobile user agents**. We must emulate a desktop browser:

```python
VIEWPORT = {"width": 1920, "height": 1080}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
```

Without this, the site will redirect to a mobile version or block access entirely.

#### 2. Context Switching Architecture

One accountant can manage multiple clients. Instead of logging in for each user:

```
❌ BAD: Login → Process User 1 → Logout → Login → Process User 2 → Logout
✅ GOOD: Login ONCE → Switch to User 1 → Process → Switch to User 2 → Process
```

This reduces login overhead by ~90%.

#### 3. Batch Processing Strategy

We process tasks by **accountant** (not by user):

```
Task 1: process_batch(accountant_id=1)
  ├── User 1 (3 tasks)
  ├── User 2 (5 tasks)
  └── User 3 (2 tasks)
```

Benefits:
- Single browser session
- Single login
- Fast context switching
- Reduced resource usage

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 2. Configure Environment

Add to `.env`:

```bash
# Celery/Redis
REDIS_URL=redis://localhost:6379/0

# Scraper settings
TASK_TIMEOUT_SECONDS=300
MAX_CONCURRENT_TASKS=10
```

### 3. Start Redis

```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or using docker-compose (already configured)
docker-compose up -d redis
```

### 4. Start Celery Worker

```bash
# Start worker
celery -A app.worker worker --loglevel=info --concurrency=2 --pool=solo

# With auto-reload for development
watchfiles 'celery -A app.worker worker --loglevel=info --concurrency=2 --pool=solo' app/
```

### 5. (Optional) Start Celery Beat for Scheduling

```bash
celery -A app.worker beat --loglevel=info
```

This will automatically trigger `process_all_accountants` every hour.

## Usage Examples

### Example 1: Trigger Batch Processing for One Accountant

```python
from app.worker import process_batch

# Trigger task processing for accountant ID 1
result = process_batch.delay(1)

# Get result (blocking)
print(result.get())
```

### Example 2: Process All Accountants

```python
from app.worker import process_all_accountants

# Trigger processing for all active accountants
result = process_all_accountants.delay()

print(result.get())
# Output: {'triggered_tasks': 5, 'accountants': [...]}
```

### Example 3: Direct TaxBot Usage

```python
import asyncio
from app.services.scraper import TaxBot

async def test_scraper():
    async with TaxBot(headless=False) as bot:
        # Login
        await bot.login_accountant("+994501234567")
        
        # Switch to client
        await bot.switch_taxpayer("1234567890")
        
        # Fetch inbox
        messages = await bot.fetch_inbox()
        
        for msg in messages:
            if msg['is_risk_flagged']:
                print(f"🚨 RISK: {msg['subject']}")

asyncio.run(test_scraper())
```

### Example 4: Create Tasks via API (Future)

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models import Task, TaskType, TaskStatus
from app.worker import process_batch

router = APIRouter()

@router.post("/tasks/inbox-scan/{user_id}")
async def create_inbox_scan_task(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    # Create task
    task = Task(
        user_id=user_id,
        type=TaskType.INBOX_SCAN,
        status=TaskStatus.PENDING
    )
    db.add(task)
    await db.commit()
    
    # Get user's accountant
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one()
    
    # Trigger batch processing for this accountant
    if user.assigned_accountant_id:
        process_batch.delay(user.assigned_accountant_id)
    
    return {"task_id": task.id, "status": "queued"}
```

## TaxBot Methods

### `login_accountant(phone_number, wait_for_pin_seconds=120)`

Authenticates using ASAN İmza.

**Parameters:**
- `phone_number`: Accountant's phone (e.g., "+994501234567")
- `wait_for_pin_seconds`: Max time to wait for PIN entry

**Flow:**
1. Navigate to login page
2. Click "ASAN İmza" button
3. Enter phone number
4. Wait for external PIN entry (Android Farm ADB or manual)
5. Verify successful login

**Raises:**
- `LoginFailedException`: If login fails or times out

### `switch_taxpayer(client_voen)`

Switches to a different client's taxpayer context.

**Parameters:**
- `client_voen`: Client's VOEN/Tax ID (10 digits)

**Flow:**
1. Locate taxpayer dropdown in header
2. Click to open dropdown
3. Find and select target VOEN
4. Wait for context switch

**Raises:**
- `TaxpayerSwitchException`: If switching fails

### `fetch_inbox()`

Scans inbox for messages and flags risks.

**Returns:**
```python
[
    {
        "subject": "Xəbərdarlıq haqqında...",
        "body": "...",
        "received_at": "2024-01-15",
        "is_risk_flagged": True,  # Contains risk keywords
        "sender": "Vergi Nazirliyi",
        "message_id": "msg_0"
    },
    ...
]
```

**Risk Keywords:**
- xəbərdarlıq / xeberdarliq (Warning)
- cərimə / cerime (Fine)
- borc (Debt)
- yoxlama (Audit)

**Raises:**
- `InboxFetchException`: If fetching fails

## Celery Tasks

### `process_batch(accountant_id)`

Main task for batch processing.

**Parameters:**
- `accountant_id`: ID of accountant

**Returns:**
```python
{
    "accountant_id": 1,
    "started_at": "2024-01-15T10:30:00",
    "completed_at": "2024-01-15T10:35:00",
    "duration_seconds": 300,
    "total_users": 5,
    "total_tasks": 12,
    "successful_tasks": 11,
    "failed_tasks": 1,
    "user_results": [...]
}
```

**Retry Policy:**
- Max retries: 3
- Backoff: 60s, 120s, 240s

### `process_all_accountants()`

Triggers batch processing for all active accountants.

**Returns:**
```python
{
    "triggered_tasks": 5,
    "accountants": [
        {"accountant_id": 1, "task_id": "abc123"},
        ...
    ]
}
```

## Monitoring

### Check Celery Worker Status

```bash
celery -A app.worker inspect active
celery -A app.worker inspect stats
```

### Check Task Results

```bash
celery -A app.worker result <task_id>
```

### Monitor with Flower (Optional)

```bash
pip install flower
celery -A app.worker flower --port=5555
```

Open http://localhost:5555

## Troubleshooting

### Issue: Playwright Browser Won't Start

```bash
# Reinstall browsers
playwright install --force chromium

# Check if chromium installed
playwright install --dry-run chromium
```

### Issue: Login Timeout

**Cause:** PIN not entered within timeout period.

**Solution:**
- Increase `wait_for_pin_seconds`
- Ensure Android Farm ADB is working
- Check ASAN İmza service status

### Issue: Taxpayer Switch Fails

**Cause:** Selectors may be outdated if site changes.

**Solution:**
- Run with `headless=False` to debug
- Inspect actual HTML structure
- Update selectors in `switch_taxpayer()`

### Issue: Mobile Block

**Cause:** Desktop emulation not working.

**Solution:**
- Verify `USER_AGENT` is desktop (contains "Windows NT")
- Verify `VIEWPORT` is desktop size (1920x1080)
- Check browser context creation

### Issue: Celery Tasks Not Processing

```bash
# Check Redis connection
redis-cli ping

# Check if worker is running
celery -A app.worker inspect ping

# Check for errors
celery -A app.worker events
```

## Production Considerations

### 1. Scalability

Run multiple workers:
```bash
# Worker 1
celery -A app.worker worker -n worker1@%h --concurrency=2

# Worker 2
celery -A app.worker worker -n worker2@%h --concurrency=2
```

### 2. Resource Management

- Limit concurrent tasks to avoid overwhelming browser pool
- Set appropriate timeouts
- Monitor memory usage (Playwright can be heavy)

### 3. Logging

Configure structured logging:

```python
import logging
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
```

### 4. Error Alerting

Integrate with Sentry:

```python
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[CeleryIntegration()]
)
```

### 5. Rate Limiting

Avoid overwhelming e-taxes.gov.az:

```python
@celery_app.task(rate_limit="10/m")  # 10 per minute
def process_batch(accountant_id):
    ...
```

## Security Considerations

### 1. Credentials

- **Never** store accountant phone numbers or PINs in code
- Store in database encrypted at rest
- Use environment variables for sensitive config

### 2. Session Management

- Rotate session cookies regularly
- Implement session expiry detection
- Re-authenticate when session expires

### 3. Screenshots

- Disable screenshots in production (contains sensitive data)
- If enabled, encrypt and delete after debugging

### 4. Logging

- Sanitize logs (remove VOENs, phone numbers)
- Use secure log storage
- Implement log retention policies

## Future Enhancements

1. **Session Persistence**: Save browser state to avoid re-login
2. **Parallel Processing**: Process multiple accountants concurrently
3. **Smart Scheduling**: Process high-priority users first
4. **Automatic Retry**: Retry failed tasks with exponential backoff
5. **Health Checks**: Monitor accountant availability
6. **Analytics**: Track processing metrics and success rates

## License

Proprietary - DayDay Tax

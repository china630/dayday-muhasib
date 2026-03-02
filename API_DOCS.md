# DayDay Tax API Documentation

## Overview

Complete REST API documentation for the DayDay Tax backend system.

**Base URL**: `http://localhost:8000`  
**API Version**: v1  
**API Prefix**: `/api/v1`

## Authentication

For MVP: Use Bearer token format with user's VOEN.

**Format**: `Bearer voen:{YOUR_VOEN}`

**Example**:
```bash
curl -H "Authorization: Bearer voen:1234567890" \
  http://localhost:8000/api/v1/wallet/balance
```

**Headers**:
```
Authorization: Bearer voen:1234567890
Content-Type: application/json
```

In production, this should be replaced with proper JWT tokens with signing and expiry.

## API Endpoints

### Health & Status

#### GET /
Root endpoint - API information

**Response**:
```json
{
  "app": "DayDay Tax API",
  "version": "1.0.0",
  "status": "running",
  "docs": "/docs"
}
```

#### GET /health
Basic health check

**Response**:
```json
{
  "status": "healthy"
}
```

#### GET /health/db
Database health check

**Response**:
```json
{
  "status": "healthy",
  "database": "connected"
}
```

#### GET /health/celery
Celery worker health check

**Response**:
```json
{
  "status": "healthy",
  "workers": 2,
  "worker_list": ["worker1@hostname", "worker2@hostname"]
}
```

---

## Wallet Endpoints

### GET /api/v1/wallet/balance
Get current wallet balance for authenticated user.

**Authentication**: Required

**Response**:
```json
{
  "user_id": 1,
  "voen": "1234567890",
  "balance": "45.50",
  "status": "ACTIVE",
  "last_updated": "2024-01-15T10:30:00Z"
}
```

**Status Codes**:
- `200 OK`: Success
- `401 Unauthorized`: Invalid or missing token
- `403 Forbidden`: User is blocked
- `404 Not Found`: Wallet not found

**Example**:
```bash
curl -H "Authorization: Bearer voen:1234567890" \
  http://localhost:8000/api/v1/wallet/balance
```

---

### GET /api/v1/wallet/transactions
Get transaction history for authenticated user.

**Authentication**: Required

**Query Parameters**:
- `limit` (optional, default: 50): Maximum number of transactions
- `offset` (optional, default: 0): Pagination offset

**Response**:
```json
[
  {
    "id": 1,
    "wallet_id": 1,
    "amount": "50.00",
    "type": "DEPOSIT",
    "external_ref": "MTN123456789",
    "description": "MilliÖN deposit from terminal TERMINAL001",
    "created_at": "2024-01-15T10:30:00Z"
  },
  {
    "id": 2,
    "wallet_id": 1,
    "amount": "-10.00",
    "type": "SUB_FEE",
    "external_ref": null,
    "description": "Monthly subscription fee - January 2024",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

**Example**:
```bash
curl -H "Authorization: Bearer voen:1234567890" \
  "http://localhost:8000/api/v1/wallet/transactions?limit=20&offset=0"
```

---

### POST /api/v1/wallet/callbacks/million
MilliÖN payment terminal webhook endpoint.

**Authentication**: Webhook token in `X-Webhook-Token` header

**Content Types**: `application/json` or `application/xml`

**JSON Request**:
```json
{
  "transaction_id": "MTN123456789",
  "amount": 50.00,
  "user_identifier": "1234567890",
  "timestamp": "2024-01-15T10:30:00Z",
  "terminal_id": "TERMINAL001",
  "status": "completed"
}
```

**XML Request**:
```xml
<payment>
  <transaction_id>MTN123456789</transaction_id>
  <amount>50.00</amount>
  <user_identifier>1234567890</user_identifier>
  <timestamp>2024-01-15T10:30:00Z</timestamp>
  <terminal_id>TERMINAL001</terminal_id>
  <status>completed</status>
</payment>
```

**Response**:
```json
{
  "success": true,
  "message": "Deposit processed successfully",
  "transaction_id": 15,
  "new_balance": "95.50",
  "amount_deposited": "50.00"
}
```

**Status Codes**:
- `200 OK`: Deposit processed successfully
- `400 Bad Request`: Invalid payment data or payment not completed
- `401 Unauthorized`: Invalid webhook token
- `404 Not Found`: User not found
- `415 Unsupported Media Type`: Invalid content type

**Example (JSON)**:
```bash
curl -X POST \
  -H "X-Webhook-Token: your-webhook-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "MTN123456789",
    "amount": 50.00,
    "user_identifier": "1234567890",
    "status": "completed"
  }' \
  http://localhost:8000/api/v1/wallet/callbacks/million
```

**Example (XML)**:
```bash
curl -X POST \
  -H "X-Webhook-Token: your-webhook-secret" \
  -H "Content-Type: application/xml" \
  -d '<payment>
    <transaction_id>MTN123456789</transaction_id>
    <amount>50.00</amount>
    <user_identifier>1234567890</user_identifier>
    <status>completed</status>
  </payment>' \
  http://localhost:8000/api/v1/wallet/callbacks/million
```

---

## Task Endpoints

### GET /api/v1/tasks/status
Poll task status for authenticated user.

**Authentication**: Required

**Query Parameters**:
- `task_type` (optional): Filter by task type (`FILING`, `DEBT_CHECK`, `INBOX_SCAN`)
- `task_status` (optional): Filter by status (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`)
- `limit` (optional, default: 50): Maximum number of tasks
- `offset` (optional, default: 0): Pagination offset

**Response**:
```json
{
  "tasks": [
    {
      "id": 1,
      "type": "INBOX_SCAN",
      "status": "COMPLETED",
      "created_at": "2024-01-15T09:00:00Z",
      "updated_at": "2024-01-15T09:05:00Z",
      "completed_at": "2024-01-15T09:05:00Z",
      "result_payload": {
        "messages_fetched": 5,
        "risk_messages": 2,
        "timestamp": "2024-01-15T09:05:00Z"
      },
      "error_message": null
    },
    {
      "id": 2,
      "type": "FILING",
      "status": "PENDING",
      "created_at": "2024-01-15T10:00:00Z",
      "updated_at": "2024-01-15T10:00:00Z",
      "completed_at": null,
      "result_payload": null,
      "error_message": null
    }
  ],
  "total": 2,
  "page": 1,
  "page_size": 50
}
```

**Example**:
```bash
# Get all tasks
curl -H "Authorization: Bearer voen:1234567890" \
  http://localhost:8000/api/v1/tasks/status

# Get only pending inbox scans
curl -H "Authorization: Bearer voen:1234567890" \
  "http://localhost:8000/api/v1/tasks/status?task_type=INBOX_SCAN&task_status=PENDING"
```

---

### POST /api/v1/tasks
Create a new task.

**Authentication**: Required

**Request**:
```json
{
  "type": "INBOX_SCAN",
  "description": "Monthly inbox scan"
}
```

**Task Types**:
- `FILING`: Tax filing submission
- `DEBT_CHECK`: Check debt status
- `INBOX_SCAN`: Scan inbox for messages

**Response**:
```json
{
  "success": true,
  "message": "Task created successfully. Type: INBOX_SCAN",
  "task_id": 15,
  "task_status": "PENDING"
}
```

**Status Codes**:
- `201 Created`: Task created successfully
- `401 Unauthorized`: Invalid or missing token
- `403 Forbidden`: User is blocked

**Example**:
```bash
curl -X POST \
  -H "Authorization: Bearer voen:1234567890" \
  -H "Content-Type: application/json" \
  -d '{"type": "INBOX_SCAN"}' \
  http://localhost:8000/api/v1/tasks
```

---

### GET /api/v1/tasks/{task_id}
Get specific task details.

**Authentication**: Required

**Path Parameters**:
- `task_id`: Task ID

**Response**:
```json
{
  "id": 1,
  "type": "INBOX_SCAN",
  "status": "COMPLETED",
  "created_at": "2024-01-15T09:00:00Z",
  "updated_at": "2024-01-15T09:05:00Z",
  "completed_at": "2024-01-15T09:05:00Z",
  "result_payload": {
    "messages_fetched": 5,
    "risk_messages": 2
  },
  "error_message": null
}
```

**Status Codes**:
- `200 OK`: Success
- `404 Not Found`: Task not found or not owned by user

**Example**:
```bash
curl -H "Authorization: Bearer voen:1234567890" \
  http://localhost:8000/api/v1/tasks/1
```

---

## Message Endpoints

### GET /api/v1/messages/inbox
Get inbox messages from tax authority.

**Authentication**: Required

**Query Parameters**:
- `risk_only` (optional, default: false): Return only risk-flagged messages
- `limit` (optional, default: 50): Maximum number of messages
- `offset` (optional, default: 0): Pagination offset

**Response**:
```json
{
  "messages": [
    {
      "id": 1,
      "subject": "Xəbərdarlıq: Vergi bəyannaməsi",
      "body_text": "Hörmətli vergi ödəyicisi...",
      "is_risk_flagged": true,
      "received_at": "2024-01-14T15:30:00Z",
      "created_at": "2024-01-15T09:05:00Z"
    },
    {
      "id": 2,
      "subject": "Məlumat: Yeni qanun dəyişikliyi",
      "body_text": "Sizə bildiririk ki...",
      "is_risk_flagged": false,
      "received_at": "2024-01-13T10:00:00Z",
      "created_at": "2024-01-15T09:05:00Z"
    }
  ],
  "total": 2,
  "risk_count": 1,
  "page": 1,
  "page_size": 50
}
```

**Risk Keywords** (Azerbaijani):
- xəbərdarlıq / xeberdarliq (Warning)
- cərimə / cerime (Fine)
- borc (Debt)
- yoxlama (Audit)
- ödəniş / odenis (Payment)

**Example**:
```bash
# Get all messages
curl -H "Authorization: Bearer voen:1234567890" \
  http://localhost:8000/api/v1/messages/inbox

# Get only risk-flagged messages
curl -H "Authorization: Bearer voen:1234567890" \
  "http://localhost:8000/api/v1/messages/inbox?risk_only=true"
```

---

### GET /api/v1/messages/{message_id}
Get specific message details.

**Authentication**: Required

**Path Parameters**:
- `message_id`: Message ID

**Response**:
```json
{
  "id": 1,
  "subject": "Xəbərdarlıq: Vergi bəyannaməsi",
  "body_text": "Hörmətli vergi ödəyicisi, sizə bildiririk ki...",
  "is_risk_flagged": true,
  "received_at": "2024-01-14T15:30:00Z",
  "created_at": "2024-01-15T09:05:00Z"
}
```

**Status Codes**:
- `200 OK`: Success
- `404 Not Found`: Message not found or not owned by user

**Example**:
```bash
curl -H "Authorization: Bearer voen:1234567890" \
  http://localhost:8000/api/v1/messages/1
```

---

## Error Responses

All endpoints return errors in a consistent format:

```json
{
  "detail": "Error message here"
}
```

**Common Status Codes**:
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: User is blocked or lacks permission
- `404 Not Found`: Resource not found
- `415 Unsupported Media Type`: Invalid Content-Type
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Server error

---

## Billing

Monthly subscription billing is handled automatically by Celery Beat.

**Billing Schedule**: 1st of each month at midnight (Asia/Baku timezone)

**Subscription Fee**: 10 AZN/month

**Billing Process**:
1. If balance >= 10 AZN: Deduct fee, user remains/becomes ACTIVE
2. If balance < 10 AZN: User is BLOCKED

**Manual Billing Trigger** (Admin):
```python
from app.worker import monthly_billing
monthly_billing.delay()
```

**Billing Preview** (Admin):
```python
from app.worker import billing_preview
result = billing_preview.delay()
print(result.get())
```

---

## Interactive API Documentation

FastAPI provides interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These interfaces allow you to:
- View all endpoints
- Try out API calls
- See request/response schemas
- Test authentication

---

## Postman Collection

### Import Collection

Create a new collection in Postman with these examples:

1. **Set Environment Variables**:
   - `base_url`: `http://localhost:8000`
   - `voen`: `1234567890`
   - `webhook_token`: `your-webhook-secret`

2. **Set Authorization**:
   - Type: Bearer Token
   - Token: `voen:{{voen}}`

### Example Requests

#### Get Balance
```
GET {{base_url}}/api/v1/wallet/balance
Authorization: Bearer voen:{{voen}}
```

#### Create Task
```
POST {{base_url}}/api/v1/tasks
Authorization: Bearer voen:{{voen}}
Content-Type: application/json

{
  "type": "INBOX_SCAN"
}
```

#### Get Messages
```
GET {{base_url}}/api/v1/messages/inbox?risk_only=true
Authorization: Bearer voen:{{voen}}
```

---

## Rate Limiting

Currently, no rate limiting is implemented.

For production, consider adding rate limiting:
- Per user: 100 requests/minute
- Per IP: 1000 requests/minute
- Webhook endpoint: No limit (authenticated)

---

## Webhooks

### MilliÖN Payment Webhook

**URL**: `POST /api/v1/wallet/callbacks/million`

**Authentication**: `X-Webhook-Token` header

**Retry Policy**: MilliÖN should retry failed webhooks with exponential backoff

**Idempotency**: Duplicate transaction_id is detected and ignored

**Configuration**:
Set webhook secret in `.env`:
```
MILLION_WEBHOOK_SECRET=your-secret-token-here
```

---

## Testing

### Manual Testing

```bash
# 1. Start API server
uvicorn app.main:app --reload

# 2. Test health
curl http://localhost:8000/health

# 3. Test balance (replace VOEN)
curl -H "Authorization: Bearer voen:1234567890" \
  http://localhost:8000/api/v1/wallet/balance

# 4. Test webhook (requires test data)
curl -X POST \
  -H "X-Webhook-Token: test-token" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TEST123","amount":50,"user_identifier":"1234567890","status":"completed"}' \
  http://localhost:8000/api/v1/wallet/callbacks/million
```

### Automated Testing

Run the quickstart script:
```bash
python quickstart.py
```

---

## Production Considerations

### Authentication
- Replace VOEN-based tokens with proper JWT tokens
- Implement token expiry and refresh
- Add role-based access control (admin, user)

### Security
- Enable HTTPS only
- Implement rate limiting
- Add request validation
- Sanitize logs (no VOENs/phone numbers)
- Use proper webhook secrets

### Performance
- Add Redis caching for balance queries
- Implement connection pooling
- Add database query optimization
- Monitor slow queries

### Monitoring
- Add Sentry for error tracking
- Implement request logging
- Add metrics (Prometheus)
- Set up alerts for failures

### Deployment
- Use gunicorn/uvicorn with multiple workers
- Set up load balancing
- Configure auto-scaling
- Add health check endpoints for load balancer

---

## Support

For issues or questions:
- Check the logs: `tail -f logs/api.log`
- Check Celery worker: `celery -A app.worker inspect active`
- Check database: `psql -d dayday_tax`

---

**Last Updated**: 2024  
**API Version**: 1.0.0

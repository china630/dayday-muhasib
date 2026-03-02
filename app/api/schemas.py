"""
Pydantic Schemas for API Request/Response Models
================================================

These schemas define the structure of data sent to and received from API endpoints.
"""

from pydantic import BaseModel, Field, validator
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
from enum import Enum


class UserStatus(str, Enum):
    """User account status"""
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class TransactionType(str, Enum):
    """Transaction types"""
    DEPOSIT = "DEPOSIT"
    SUB_FEE = "SUB_FEE"


class TaskType(str, Enum):
    """Task types"""
    FILING = "FILING"
    DEBT_CHECK = "DEBT_CHECK"
    INBOX_SCAN = "INBOX_SCAN"


class TaskStatus(str, Enum):
    """Task status"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Wallet Schemas

class WalletBalanceResponse(BaseModel):
    """Wallet balance response"""
    user_id: int
    voen: str
    balance: Decimal = Field(..., description="Current wallet balance in AZN")
    status: UserStatus
    last_updated: datetime
    
    class Config:
        from_attributes = True


class MillionPaymentWebhook(BaseModel):
    """
    MilliÖN payment terminal webhook payload
    Accepts both JSON and XML formats
    """
    transaction_id: str = Field(..., description="External transaction reference from MilliÖN")
    amount: Decimal = Field(..., description="Payment amount in AZN", gt=0)
    user_identifier: str = Field(..., description="User VOEN or phone number")
    timestamp: Optional[datetime] = None
    terminal_id: Optional[str] = None
    status: str = Field(default="completed", description="Payment status")
    
    @validator("amount")
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be positive")
        return round(v, 2)


class TransactionResponse(BaseModel):
    """Transaction response"""
    id: int
    wallet_id: int
    amount: Decimal
    type: TransactionType
    external_ref: Optional[str]
    description: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class DepositResponse(BaseModel):
    """Response after deposit"""
    success: bool
    message: str
    transaction_id: int
    new_balance: Decimal
    amount_deposited: Decimal


# Task Schemas

class TaskStatusResponse(BaseModel):
    """Task status response"""
    id: int
    type: TaskType
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    result_payload: Optional[dict]
    error_message: Optional[str]
    
    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """List of tasks"""
    tasks: List[TaskStatusResponse]
    total: int
    page: int
    page_size: int


class CreateTaskRequest(BaseModel):
    """Request to create a new task"""
    type: TaskType
    description: Optional[str] = None


class CreateTaskResponse(BaseModel):
    """Response after creating a task"""
    success: bool
    message: str
    task_id: int
    task_status: TaskStatus


# Message Schemas

class MessageResponse(BaseModel):
    """Message from tax authority inbox"""
    id: int
    subject: str
    body_text: str
    is_risk_flagged: bool = Field(..., description="Whether message contains risk keywords")
    received_at: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """List of messages"""
    messages: List[MessageResponse]
    total: int
    risk_count: int = Field(..., description="Number of risk-flagged messages")
    page: int
    page_size: int


# User Schemas

class UserInfoResponse(BaseModel):
    """User information"""
    id: int
    voen: str
    status: UserStatus
    assigned_accountant_id: Optional[int]
    created_at: datetime
    
    class Config:
        from_attributes = True


# Billing Schemas

class BillingResponse(BaseModel):
    """Response from billing operation"""
    success: bool
    message: str
    users_processed: int
    users_charged: int
    users_blocked: int
    total_amount_charged: Decimal
    errors: List[str] = []


class SubscriptionInfo(BaseModel):
    """User subscription information"""
    user_id: int
    voen: str
    status: UserStatus
    current_balance: Decimal
    monthly_fee: Decimal = Field(default=Decimal("10.00"), description="Monthly subscription fee")
    next_billing_date: Optional[datetime] = None
    days_until_billing: Optional[int] = None


# Error Schemas

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class SuccessResponse(BaseModel):
    """Standard success response"""
    success: bool
    message: str
    data: Optional[dict] = None

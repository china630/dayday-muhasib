"""
Wallet API Router
=================

Endpoints for wallet management and payment processing.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from datetime import datetime
import logging
import xml.etree.ElementTree as ET

from app.db.session import get_db
from app.models import User, Wallet, Transaction, TransactionType, UserStatus
from app.api.schemas import (
    WalletBalanceResponse,
    MillionPaymentWebhook,
    DepositResponse,
    TransactionResponse,
    ErrorResponse
)
from app.api.deps import get_current_active_user, verify_webhook_token


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.get(
    "/balance",
    response_model=WalletBalanceResponse,
    summary="Get wallet balance",
    description="Returns the current wallet balance for the authenticated user"
)
async def get_wallet_balance(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get wallet balance for authenticated user.
    
    Returns:
        WalletBalanceResponse: User's wallet information including current balance
    """
    # Get user's wallet
    result = await db.execute(
        select(Wallet).where(Wallet.user_id == current_user.id)
    )
    wallet = result.scalar_one_or_none()
    
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found for user. Please contact support."
        )
    
    return WalletBalanceResponse(
        user_id=current_user.id,
        voen=current_user.voen,
        balance=wallet.balance,
        status=current_user.status,
        last_updated=wallet.updated_at
    )


@router.get(
    "/transactions",
    response_model=list[TransactionResponse],
    summary="Get transaction history",
    description="Returns transaction history for the authenticated user's wallet"
)
async def get_transactions(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get transaction history.
    
    Args:
        limit: Maximum number of transactions to return (default 50)
        offset: Number of transactions to skip (for pagination)
        current_user: Authenticated user
        db: Database session
    
    Returns:
        List[TransactionResponse]: List of transactions
    """
    # Get user's wallet
    result = await db.execute(
        select(Wallet).where(Wallet.user_id == current_user.id)
    )
    wallet = result.scalar_one_or_none()
    
    if not wallet:
        return []
    
    # Get transactions
    result = await db.execute(
        select(Transaction)
        .where(Transaction.wallet_id == wallet.id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    transactions = result.scalars().all()
    
    return [TransactionResponse.model_validate(t) for t in transactions]


@router.post(
    "/callbacks/million",
    response_model=DepositResponse,
    summary="MilliÖN payment webhook",
    description="Webhook endpoint to receive deposit notifications from MilliÖN payment terminals",
    status_code=status.HTTP_200_OK
)
async def million_payment_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _authenticated: bool = Depends(verify_webhook_token)
):
    """
    MilliÖN Payment Terminal Webhook Handler
    
    This endpoint receives payment notifications from MilliÖN terminals in Azerbaijan.
    It accepts both JSON and XML formats.
    
    JSON Example:
    {
        "transaction_id": "MTN123456789",
        "amount": 50.00,
        "user_identifier": "1234567890",
        "timestamp": "2024-01-15T10:30:00Z",
        "terminal_id": "TERMINAL001",
        "status": "completed"
    }
    
    XML Example:
    <payment>
        <transaction_id>MTN123456789</transaction_id>
        <amount>50.00</amount>
        <user_identifier>1234567890</user_identifier>
        <timestamp>2024-01-15T10:30:00Z</timestamp>
        <terminal_id>TERMINAL001</terminal_id>
        <status>completed</status>
    </payment>
    
    Args:
        request: FastAPI request object
        db: Database session
        _authenticated: Webhook authentication verification
    
    Returns:
        DepositResponse: Deposit confirmation with updated balance
    """
    try:
        # Determine content type
        content_type = request.headers.get("content-type", "").lower()
        
        # Parse request body
        if "json" in content_type or "application/json" in content_type:
            # Parse JSON
            body = await request.json()
            payment_data = MillionPaymentWebhook(**body)
        
        elif "xml" in content_type or "text/xml" in content_type or "application/xml" in content_type:
            # Parse XML
            body_bytes = await request.body()
            root = ET.fromstring(body_bytes.decode('utf-8'))
            
            payment_data = MillionPaymentWebhook(
                transaction_id=root.find("transaction_id").text,
                amount=Decimal(root.find("amount").text),
                user_identifier=root.find("user_identifier").text,
                timestamp=root.find("timestamp").text if root.find("timestamp") is not None else None,
                terminal_id=root.find("terminal_id").text if root.find("terminal_id") is not None else None,
                status=root.find("status").text if root.find("status") is not None else "completed"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Content-Type must be application/json or application/xml"
            )
        
        logger.info(
            f"Received payment webhook: transaction_id={payment_data.transaction_id}, "
            f"amount={payment_data.amount}, user={payment_data.user_identifier}"
        )
        
        # Verify payment status
        if payment_data.status.lower() not in ["completed", "success", "successful"]:
            logger.warning(f"Payment not completed: {payment_data.status}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment status is not completed: {payment_data.status}"
            )
        
        # Find user by VOEN (user_identifier)
        result = await db.execute(
            select(User).where(User.voen == payment_data.user_identifier)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User not found for VOEN: {payment_data.user_identifier}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found for identifier: {payment_data.user_identifier}"
            )
        
        # Get user's wallet
        result = await db.execute(
            select(Wallet).where(Wallet.user_id == user.id)
        )
        wallet = result.scalar_one_or_none()
        
        if not wallet:
            # Create wallet if doesn't exist
            wallet = Wallet(user_id=user.id, balance=Decimal("0.00"))
            db.add(wallet)
            await db.flush()
            logger.info(f"Created new wallet for user {user.id}")
        
        # Check for duplicate transaction
        result = await db.execute(
            select(Transaction).where(
                Transaction.external_ref == payment_data.transaction_id
            )
        )
        existing_transaction = result.scalar_one_or_none()
        
        if existing_transaction:
            logger.warning(f"Duplicate transaction detected: {payment_data.transaction_id}")
            return DepositResponse(
                success=True,
                message="Transaction already processed (duplicate)",
                transaction_id=existing_transaction.id,
                new_balance=wallet.balance,
                amount_deposited=existing_transaction.amount
            )
        
        # Create transaction record
        transaction = Transaction(
            wallet_id=wallet.id,
            amount=payment_data.amount,
            type=TransactionType.DEPOSIT,
            external_ref=payment_data.transaction_id,
            description=f"MilliÖN deposit from terminal {payment_data.terminal_id or 'unknown'}"
        )
        db.add(transaction)
        
        # Update wallet balance
        old_balance = wallet.balance
        wallet.balance += payment_data.amount
        
        # If user was blocked due to insufficient funds, reactivate them
        if user.status == UserStatus.BLOCKED and wallet.balance >= Decimal("10.00"):
            user.status = UserStatus.ACTIVE
            logger.info(f"User {user.id} reactivated after deposit")
        
        # Commit transaction
        await db.commit()
        await db.refresh(wallet)
        await db.refresh(transaction)
        
        logger.info(
            f"Deposit successful: user={user.id}, amount={payment_data.amount}, "
            f"old_balance={old_balance}, new_balance={wallet.balance}"
        )
        
        return DepositResponse(
            success=True,
            message="Deposit processed successfully",
            transaction_id=transaction.id,
            new_balance=wallet.balance,
            amount_deposited=payment_data.amount
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error processing payment webhook: {e}", exc_info=True)
        await db.rollback()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process payment: {str(e)}"
        )

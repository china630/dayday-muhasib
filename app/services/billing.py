"""
Billing Service
===============

Handles monthly subscription billing for DayDay Tax users.

Monthly Subscription Model:
---------------------------
- Fee: 10 AZN per month
- Billing Day: 1st of each month
- Auto-deduction from wallet
- If balance < 10 AZN, user is blocked until payment

Architecture:
-------------
This service is called by a Celery Beat scheduled task that runs monthly.
It processes all active users and deducts the subscription fee from their wallets.
"""

import logging
from typing import Dict, List, Any
from decimal import Decimal
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Wallet, Transaction, TransactionType, UserStatus
from app.core.config import settings


logger = logging.getLogger(__name__)


class BillingService:
    """Service for handling subscription billing operations"""
    
    SUBSCRIPTION_FEE = Decimal(str(settings.MONTHLY_SUBSCRIPTION_FEE))
    
    def __init__(self, db: AsyncSession):
        """
        Initialize billing service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    async def process_monthly_billing(self) -> Dict[str, Any]:
        """
        Process monthly subscription billing for all users.
        
        This method:
        1. Gets all users (both ACTIVE and BLOCKED)
        2. For each user:
           - Checks wallet balance
           - If balance >= 10 AZN: Deducts fee and keeps/makes user ACTIVE
           - If balance < 10 AZN: Blocks user and logs error
        3. Returns summary of billing results
        
        Returns:
            Dict with billing summary:
            {
                'users_processed': int,
                'users_charged': int,
                'users_blocked': int,
                'users_reactivated': int,
                'total_amount_charged': Decimal,
                'errors': List[str]
            }
        """
        logger.info("Starting monthly billing process...")
        
        results = {
            'users_processed': 0,
            'users_charged': 0,
            'users_blocked': 0,
            'users_reactivated': 0,
            'total_amount_charged': Decimal('0.00'),
            'errors': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Get all users (both ACTIVE and BLOCKED)
            result = await self.db.execute(select(User))
            users = result.scalars().all()
            
            logger.info(f"Found {len(users)} users to process")
            
            for user in users:
                results['users_processed'] += 1
                
                try:
                    await self._process_user_billing(user, results)
                except Exception as e:
                    error_msg = f"Error processing user {user.id} (VOEN: {user.voen}): {str(e)}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            # Commit all changes
            await self.db.commit()
            
            logger.info(
                f"Monthly billing completed: "
                f"processed={results['users_processed']}, "
                f"charged={results['users_charged']}, "
                f"blocked={results['users_blocked']}, "
                f"total_charged={results['total_amount_charged']} AZN"
            )
            
            return results
        
        except Exception as e:
            logger.error(f"Fatal error in monthly billing: {e}", exc_info=True)
            await self.db.rollback()
            results['errors'].append(f"Fatal error: {str(e)}")
            return results
    
    async def _process_user_billing(self, user: User, results: Dict[str, Any]) -> None:
        """
        Process billing for a single user.
        
        Args:
            user: User to process
            results: Results dictionary to update
        """
        # Get user's wallet
        result = await self.db.execute(
            select(Wallet).where(Wallet.user_id == user.id)
        )
        wallet = result.scalar_one_or_none()
        
        if not wallet:
            # Create wallet if doesn't exist
            wallet = Wallet(user_id=user.id, balance=Decimal("0.00"))
            self.db.add(wallet)
            await self.db.flush()
            logger.info(f"Created wallet for user {user.id}")
        
        # Check if user has sufficient balance
        if wallet.balance >= self.SUBSCRIPTION_FEE:
            # Deduct subscription fee
            await self._charge_subscription(user, wallet, results)
        else:
            # Insufficient funds - block user
            await self._block_user_insufficient_funds(user, wallet, results)
    
    async def _charge_subscription(
        self,
        user: User,
        wallet: Wallet,
        results: Dict[str, Any]
    ) -> None:
        """
        Charge subscription fee to user's wallet.
        
        Args:
            user: User to charge
            wallet: User's wallet
            results: Results dictionary to update
        """
        old_balance = wallet.balance
        wallet.balance -= self.SUBSCRIPTION_FEE
        
        # Create transaction record
        transaction = Transaction(
            wallet_id=wallet.id,
            amount=-self.SUBSCRIPTION_FEE,  # Negative for deduction
            type=TransactionType.SUB_FEE,
            description=f"Monthly subscription fee - {datetime.now().strftime('%B %Y')}"
        )
        self.db.add(transaction)
        
        # If user was blocked, reactivate them
        was_blocked = user.status == UserStatus.BLOCKED
        if was_blocked:
            user.status = UserStatus.ACTIVE
            results['users_reactivated'] += 1
            logger.info(f"User {user.id} reactivated after payment")
        
        # Ensure active users stay active
        if user.status != UserStatus.ACTIVE:
            user.status = UserStatus.ACTIVE
        
        results['users_charged'] += 1
        results['total_amount_charged'] += self.SUBSCRIPTION_FEE
        
        logger.info(
            f"Charged user {user.id}: "
            f"old_balance={old_balance} AZN, "
            f"new_balance={wallet.balance} AZN, "
            f"fee={self.SUBSCRIPTION_FEE} AZN"
        )
    
    async def _block_user_insufficient_funds(
        self,
        user: User,
        wallet: Wallet,
        results: Dict[str, Any]
    ) -> None:
        """
        Block user due to insufficient funds.
        
        Args:
            user: User to block
            wallet: User's wallet
            results: Results dictionary to update
        """
        # Block user
        if user.status != UserStatus.BLOCKED:
            user.status = UserStatus.BLOCKED
            results['users_blocked'] += 1
            
            logger.warning(
                f"User {user.id} BLOCKED: "
                f"insufficient balance ({wallet.balance} AZN < {self.SUBSCRIPTION_FEE} AZN)"
            )
        else:
            logger.info(
                f"User {user.id} remains BLOCKED: "
                f"balance={wallet.balance} AZN"
            )
    
    async def get_user_subscription_info(self, user_id: int) -> Dict[str, Any]:
        """
        Get subscription information for a specific user.
        
        Args:
            user_id: User ID
        
        Returns:
            Dict with subscription info:
            {
                'user_id': int,
                'voen': str,
                'status': str,
                'current_balance': Decimal,
                'monthly_fee': Decimal,
                'can_pay': bool,
                'days_until_next_billing': int
            }
        """
        # Get user
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Get wallet
        result = await self.db.execute(
            select(Wallet).where(Wallet.user_id == user_id)
        )
        wallet = result.scalar_one_or_none()
        
        balance = wallet.balance if wallet else Decimal("0.00")
        
        # Calculate days until next billing (assumes billing on 1st of month)
        now = datetime.now()
        if now.day == 1:
            days_until = 0
        else:
            # Days until next 1st of month
            import calendar
            days_in_month = calendar.monthrange(now.year, now.month)[1]
            days_until = days_in_month - now.day + 1
        
        return {
            'user_id': user.id,
            'voen': user.voen,
            'status': user.status.value,
            'current_balance': balance,
            'monthly_fee': self.SUBSCRIPTION_FEE,
            'can_pay': balance >= self.SUBSCRIPTION_FEE,
            'days_until_next_billing': days_until,
            'requires_topup': balance < self.SUBSCRIPTION_FEE
        }
    
    async def preview_billing_impact(self) -> Dict[str, Any]:
        """
        Preview the impact of running monthly billing without actually charging.
        
        Useful for administrative purposes to see what would happen if billing runs now.
        
        Returns:
            Dict with preview results:
            {
                'total_users': int,
                'users_will_be_charged': int,
                'users_will_be_blocked': int,
                'users_currently_blocked': int,
                'total_revenue': Decimal,
                'users_by_balance': Dict[str, int]
            }
        """
        logger.info("Generating billing preview...")
        
        preview = {
            'total_users': 0,
            'users_will_be_charged': 0,
            'users_will_be_blocked': 0,
            'users_currently_blocked': 0,
            'users_will_be_reactivated': 0,
            'total_revenue': Decimal('0.00'),
            'users_by_balance': {
                'sufficient': 0,
                'insufficient': 0,
                'zero': 0
            }
        }
        
        # Get all users
        result = await self.db.execute(select(User))
        users = result.scalars().all()
        
        preview['total_users'] = len(users)
        
        for user in users:
            # Get wallet
            result = await self.db.execute(
                select(Wallet).where(Wallet.user_id == user.id)
            )
            wallet = result.scalar_one_or_none()
            balance = wallet.balance if wallet else Decimal("0.00")
            
            # Count current blocked users
            if user.status == UserStatus.BLOCKED:
                preview['users_currently_blocked'] += 1
            
            # Analyze balance
            if balance == 0:
                preview['users_by_balance']['zero'] += 1
            elif balance >= self.SUBSCRIPTION_FEE:
                preview['users_by_balance']['sufficient'] += 1
                preview['users_will_be_charged'] += 1
                preview['total_revenue'] += self.SUBSCRIPTION_FEE
                
                # Check if this would reactivate a blocked user
                if user.status == UserStatus.BLOCKED:
                    preview['users_will_be_reactivated'] += 1
            else:
                preview['users_by_balance']['insufficient'] += 1
                if user.status != UserStatus.BLOCKED:
                    preview['users_will_be_blocked'] += 1
        
        logger.info(
            f"Billing preview: "
            f"{preview['users_will_be_charged']} will be charged, "
            f"{preview['users_will_be_blocked']} will be blocked"
        )
        
        return preview

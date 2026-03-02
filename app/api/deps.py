"""
Authentication and Authorization Dependencies
==============================================

This module provides FastAPI dependencies for authenticating and authorizing users.

For now, we implement a simple token-based auth. In production, this should be
replaced with JWT tokens, OAuth2, or another secure authentication mechanism.
"""

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.db.session import get_db
from app.models import User, UserStatus
from app.core.config import settings


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from bearer token.
    
    For MVP: Token format is "voen:{VOEN}"
    In production: Use proper JWT tokens with signing and expiry
    
    Args:
        credentials: Bearer token from Authorization header
        db: Database session
    
    Returns:
        User: The authenticated user
    
    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
    
    # Simple MVP authentication: token is "voen:{VOEN}"
    # In production, replace with JWT validation
    if not token.startswith("voen:"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    voen = token.replace("voen:", "")
    
    if not voen or len(voen) != 10 or not voen.isdigit():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid VOEN in token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Fetch user from database
    result = await db.execute(
        select(User).where(User.voen == voen)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current user and verify they are active (not blocked).
    
    Args:
        current_user: The authenticated user
    
    Returns:
        User: The active user
    
    Raises:
        HTTPException: If user is blocked
    """
    if current_user.status == UserStatus.BLOCKED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is blocked. Please contact support or add funds to your wallet."
        )
    
    return current_user


async def verify_webhook_token(
    x_webhook_token: Optional[str] = Header(None),
) -> bool:
    """
    Verify webhook authentication token from MilliÖN payment terminal.
    
    This should match a secret token shared with the payment provider.
    For MVP, we check against a configured secret.
    
    Args:
        x_webhook_token: Token from X-Webhook-Token header
    
    Returns:
        bool: True if valid
    
    Raises:
        HTTPException: If token is invalid
    """
    expected_token = settings.MILLION_WEBHOOK_SECRET
    
    if not x_webhook_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook authentication token"
        )
    
    if x_webhook_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authentication token"
        )
    
    return True


# Optional: Admin authentication for internal endpoints
async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Verify current user has admin privileges.
    
    For MVP: No admin role yet, this is a placeholder.
    In production: Add admin role to User model.
    
    Args:
        current_user: The authenticated user
    
    Returns:
        User: The admin user
    
    Raises:
        HTTPException: If user is not admin
    """
    # Placeholder: In production, check user.is_admin or user.role == "admin"
    # For now, all users are "admins" in development
    
    # Example production code:
    # if not current_user.is_admin:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Admin privileges required"
    #     )
    
    return current_user

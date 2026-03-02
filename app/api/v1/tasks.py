"""
Tasks API Router
================

Endpoints for task management and message retrieval.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import logging

from app.db.session import get_db
from app.models import User, Task, Message, TaskType, TaskStatus
from app.api.schemas import (
    TaskStatusResponse,
    TaskListResponse,
    CreateTaskRequest,
    CreateTaskResponse,
    MessageResponse,
    MessageListResponse,
    ErrorResponse
)
from app.api.deps import get_current_active_user
from app.worker import process_batch


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Tasks"])


@router.get(
    "/tasks/status",
    response_model=TaskListResponse,
    summary="Get task status",
    description="Poll task status for the authenticated user's tax filings and other automated tasks"
)
async def get_task_status(
    task_type: Optional[TaskType] = Query(None, description="Filter by task type"),
    task_status: Optional[TaskStatus] = Query(None, description="Filter by task status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of tasks to return"),
    offset: int = Query(0, ge=0, description="Number of tasks to skip (for pagination)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get task status for authenticated user.
    
    This endpoint allows the mobile app to poll the status of requested operations:
    - FILING: Tax filing submissions
    - DEBT_CHECK: Debt status checks
    - INBOX_SCAN: Inbox message scanning
    
    Args:
        task_type: Filter by specific task type (optional)
        task_status: Filter by task status (optional)
        limit: Maximum number of tasks to return
        offset: Pagination offset
        current_user: Authenticated user
        db: Database session
    
    Returns:
        TaskListResponse: List of tasks with pagination info
    """
    # Build query
    query = select(Task).where(Task.user_id == current_user.id)
    
    # Apply filters
    if task_type:
        query = query.where(Task.type == task_type)
    
    if task_status:
        query = query.where(Task.status == task_status)
    
    # Order by creation date (newest first)
    query = query.order_by(Task.created_at.desc())
    
    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Apply pagination
    query = query.limit(limit).offset(offset)
    
    # Execute query
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    # Calculate page number
    page = (offset // limit) + 1 if limit > 0 else 1
    
    logger.info(
        f"User {current_user.id} queried tasks: total={total}, "
        f"returned={len(tasks)}, filters=(type={task_type}, status={task_status})"
    )
    
    return TaskListResponse(
        tasks=[TaskStatusResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        page_size=limit
    )


@router.post(
    "/tasks",
    response_model=CreateTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
    description="Create a new automated task (filing, debt check, or inbox scan)"
)
async def create_task(
    task_request: CreateTaskRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new task for the authenticated user.
    
    This will:
    1. Create a PENDING task in the database
    2. Trigger the Celery worker to process tasks for the user's accountant
    
    Args:
        task_request: Task creation request
        current_user: Authenticated user
        db: Database session
    
    Returns:
        CreateTaskResponse: Created task information
    """
    # Create task
    task = Task(
        user_id=current_user.id,
        type=task_request.type,
        status=TaskStatus.PENDING,
        error_message=task_request.description
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    logger.info(
        f"Created task {task.id} for user {current_user.id}: type={task_request.type}"
    )
    
    # Trigger batch processing if user has assigned accountant
    if current_user.assigned_accountant_id:
        try:
            # Trigger Celery task asynchronously
            process_batch.delay(current_user.assigned_accountant_id)
            logger.info(
                f"Triggered batch processing for accountant {current_user.assigned_accountant_id}"
            )
        except Exception as e:
            logger.error(f"Failed to trigger batch processing: {e}")
            # Don't fail the request if Celery trigger fails
    else:
        logger.warning(f"User {current_user.id} has no assigned accountant")
    
    return CreateTaskResponse(
        success=True,
        message=f"Task created successfully. Type: {task_request.type.value}",
        task_id=task.id,
        task_status=task.status
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Get specific task",
    description="Get detailed information about a specific task by ID"
)
async def get_task_by_id(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific task by ID.
    
    Args:
        task_id: Task ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        TaskStatusResponse: Task details
    """
    # Get task
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == current_user.id  # Ensure user owns the task
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    return TaskStatusResponse.model_validate(task)


@router.get(
    "/messages/inbox",
    response_model=MessageListResponse,
    summary="Get inbox messages",
    description="Returns messages from tax authority inbox, highlighting risk-flagged ones"
)
async def get_inbox_messages(
    risk_only: bool = Query(False, description="Return only risk-flagged messages"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip (for pagination)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get inbox messages for authenticated user.
    
    Messages are retrieved from the tax authority inbox by our scraper.
    Risk-flagged messages contain keywords like:
    - "Xəbərdarlıq" (Warning)
    - "Cərimə" (Fine)
    - "Borc" (Debt)
    
    Args:
        risk_only: If True, return only risk-flagged messages
        limit: Maximum number of messages to return
        offset: Pagination offset
        current_user: Authenticated user
        db: Database session
    
    Returns:
        MessageListResponse: List of messages with risk information
    """
    # Build query
    query = select(Message).where(Message.user_id == current_user.id)
    
    # Filter for risk-flagged only if requested
    if risk_only:
        query = query.where(Message.is_risk_flagged == True)
    
    # Order by received date (newest first)
    query = query.order_by(Message.received_at.desc())
    
    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get risk count
    risk_query = select(func.count()).select_from(
        select(Message).where(
            Message.user_id == current_user.id,
            Message.is_risk_flagged == True
        ).subquery()
    )
    risk_result = await db.execute(risk_query)
    risk_count = risk_result.scalar()
    
    # Apply pagination
    query = query.limit(limit).offset(offset)
    
    # Execute query
    result = await db.execute(query)
    messages = result.scalars().all()
    
    # Calculate page number
    page = (offset // limit) + 1 if limit > 0 else 1
    
    logger.info(
        f"User {current_user.id} queried messages: total={total}, "
        f"risk_count={risk_count}, returned={len(messages)}, risk_only={risk_only}"
    )
    
    return MessageListResponse(
        messages=[MessageResponse.model_validate(m) for m in messages],
        total=total,
        risk_count=risk_count,
        page=page,
        page_size=limit
    )


@router.get(
    "/messages/{message_id}",
    response_model=MessageResponse,
    summary="Get specific message",
    description="Get detailed information about a specific message by ID"
)
async def get_message_by_id(
    message_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific message by ID.
    
    Args:
        message_id: Message ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        MessageResponse: Message details
    """
    # Get message
    result = await db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.user_id == current_user.id  # Ensure user owns the message
        )
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    return MessageResponse.model_validate(message)


@router.post(
    "/messages/{message_id}/mark-read",
    summary="Mark message as read",
    description="Mark a message as read (placeholder for future implementation)"
)
async def mark_message_read(
    message_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a message as read.
    
    This is a placeholder for future implementation.
    In production, add a 'read' field to the Message model.
    """
    # Get message to verify ownership
    result = await db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.user_id == current_user.id
        )
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Future: message.is_read = True
    # await db.commit()
    
    return {"success": True, "message": "Message marked as read"}

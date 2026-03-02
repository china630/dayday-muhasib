from sqlalchemy import String, Boolean, Integer, Numeric, Text, DateTime, Enum as SQLEnum, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from decimal import Decimal
from typing import Optional
import enum

from app.db.session import Base


class UserStatus(str, enum.Enum):
    """User account status"""
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class TransactionType(str, enum.Enum):
    """Transaction types for wallet operations"""
    DEPOSIT = "DEPOSIT"
    SUB_FEE = "SUB_FEE"


class TaskType(str, enum.Enum):
    """Types of automated tasks"""
    FILING = "FILING"
    DEBT_CHECK = "DEBT_CHECK"
    INBOX_SCAN = "INBOX_SCAN"


class TaskStatus(str, enum.Enum):
    """Task processing status"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Accountant(Base):
    """
    Represents an Android Farm SIM/device that acts as an automated accountant.
    These are internal resources used to perform tasks on behalf of users.
    """
    __tablename__ = "accountants"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    voen: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_session_cookie: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    users: Mapped[list["User"]] = relationship("User", back_populates="accountant")
    
    def __repr__(self) -> str:
        return f"<Accountant(id={self.id}, voen={self.voen}, phone={self.phone_number})>"


class User(Base):
    """
    End-user who has delegated their tax operations to our service.
    Each user is assigned to an Accountant (Android Farm SIM).
    """
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assigned_accountant_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("accountants.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    voen: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus, native_enum=False),
        default=UserStatus.ACTIVE,
        nullable=False,
        index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    accountant: Mapped[Optional["Accountant"]] = relationship("Accountant", back_populates="users")
    wallet: Mapped[Optional["Wallet"]] = relationship("Wallet", back_populates="user", uselist=False)
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="user")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="user")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, voen={self.voen}, status={self.status.value})>"


class Wallet(Base):
    """
    User's wallet for tracking balance and transactions.
    Each user has exactly one wallet.
    """
    __tablename__ = "wallets"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    user: Mapped["User"] = relationship("User", back_populates="wallet")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="wallet")
    
    def __repr__(self) -> str:
        return f"<Wallet(id={self.id}, user_id={self.user_id}, balance={self.balance})>"


class Transaction(Base):
    """
    Records all wallet transactions (deposits, fee deductions, etc.)
    """
    __tablename__ = "transactions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    wallet_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType, native_enum=False),
        nullable=False,
        index=True
    )
    external_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")
    
    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, type={self.type.value}, amount={self.amount})>"


class Task(Base):
    """
    Represents automated tasks performed by the system (filing, debt checks, inbox scanning).
    """
    __tablename__ = "tasks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType, native_enum=False),
        nullable=False,
        index=True
    )
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, native_enum=False),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True
    )
    result_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    user: Mapped["User"] = relationship("User", back_populates="tasks")
    
    def __repr__(self) -> str:
        return f"<Task(id={self.id}, type={self.type.value}, status={self.status.value})>"


class Message(Base):
    """
    Messages received from the tax authority inbox for users.
    Includes risk flagging for important alerts.
    """
    __tablename__ = "messages"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_risk_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    user: Mapped["User"] = relationship("User", back_populates="messages")
    
    def __repr__(self) -> str:
        return f"<Message(id={self.id}, user_id={self.user_id}, subject={self.subject[:50]})>"

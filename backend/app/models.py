"""Database tables. Every column holding health data is Fernet-encrypted (the *_enc columns)."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data_enc: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # questions -> report -> ready -> analyzed  (emergency can happen at any step)
    status: Mapped[str] = mapped_column(String(20), default="questions")
    title: Mapped[str] = mapped_column(String(120), default="")
    data_enc: Mapped[str] = mapped_column(Text)
    result_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ReportFile(Base):
    __tablename__ = "report_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    stored_name: Mapped[str] = mapped_column(String(100))  # encrypted bytes on disk
    text_enc: Mapped[str] = mapped_column(Text, default="")
    labs_enc: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str] = mapped_column(String(120), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PriceCache(Base):
    __tablename__ = "price_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    data: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
